from pathlib import Path

from interface import cli as cli_module
from interface.cli import (
    AggregationRunContext,
    NidsAgentCli,
    Phase3AHypothesisLineageContext,
    Phase3ARuntimeRoundContext,
    Phase3ARuntimeRunContext,
    RouterRunContext,
    SessionConfig,
    WorkerRunContext,
)
from phase3_runtime.ledger import (
    BatchLedger,
    FinalizationRecord,
    HypothesisExecutionRecord,
    RoundManifest,
)
from phase3_runtime.runtime_artifacts import (
    build_phase3a_runtime_artifact_paths,
    save_phase3a_runtime_artifacts,
)
from utils.run_logging import write_json


BATCH_ID = "runtime-cli-batch-001"


def _build_saved_phase3a_runtime_bundle(tmp_path: Path) -> dict[str, object]:
    ledger = BatchLedger(
        batch_id=BATCH_ID,
        dataset_path="C:/data/runtime_dataset.csv",
        model_name="gpt-4.1-mini",
        max_rounds=3,
        critic_enabled=False,
        status="completed",
        created_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:02:00+00:00",
        semantic_extraction_run_path="semantic/component_run.json",
        initial_investigation_analysis_run_path="analysis/component_run.json",
        initial_state_path="runtime/initial_state.json",
        initial_state_version=1,
        round_manifests=[
            RoundManifest(
                round_id="round-001",
                round_index=1,
                analysis_mode="initial",
                analysis_run_path="analysis/component_run.json",
                frozen_snapshot_path="round_manifests/round-001_snapshot.json",
                global_aggregation_path="round_manifests/round-001_global_aggregation.json",
                ranking_run_path="ranking/component_run.json",
                planner_run_path="planner/component_run.json",
                selected_hypothesis_ids=["hyp-runtime-1"],
                deferred_hypothesis_ids=[],
                start_state_version=1,
                end_state_version=2,
                status="completed",
                terminal_reason="max_rounds_reached",
                hypothesis_runs=[
                    HypothesisExecutionRecord(
                        hypothesis_id="hyp-runtime-1",
                        planner_strategy_id="strategy-runtime-1",
                        router_run_path="router/component_run.json",
                        task_ids=["task-runtime-1"],
                        worker_run_paths=[
                            "worker/task-runtime-1/component_run.json"],
                        aggregation_run_path="aggregation/component_run.json",
                        state_manager_run_path="state_manager/component_run.json",
                        start_state_version=1,
                        end_state_version=2,
                        status="completed",
                    )
                ],
            )
        ],
        finalization=FinalizationRecord(
            terminal_reason="max_rounds_reached",
            final_state_manager_run_path="state_manager/component_run.json",
            final_batch_auditor_run_path="final_batch_auditor/component_run.json",
            final_state_version=2,
            final_status="completed",
        ),
    )

    artifact_paths = build_phase3a_runtime_artifact_paths(
        batch_id=ledger.batch_id,
        log_dir=tmp_path,
    )
    initial_state = {
        "batch_id": BATCH_ID,
        "state_version": 1,
        "interpretive_hypotheses": [
            {
                "hypothesis_id": "hyp-runtime-1",
                "status": "active",
            }
        ],
    }
    write_json(artifact_paths["initial_state_path"], initial_state)

    component_run = {
        "component": "phase3a_runtime",
        "batch_id": BATCH_ID,
        "status": "completed",
        "final_status": "completed",
        "terminal_reason": "max_rounds_reached",
        "validation_ok": True,
        "final_state_version": 2,
        "round_count": 1,
        "model_name": "gpt-4.1-mini",
        "execution_mode": "full_batch",
        "critic_enabled": False,
        "caller_mode": "cli",
    }
    initial_runtime_context = {
        "batch_id": BATCH_ID,
        "dataset_path": ledger.dataset_path,
        "model_name": "gpt-4.1-mini",
        "execution_mode": "full_batch",
        "max_rounds": 3,
        "critic_enabled": False,
        "component_model_names": {
            "planner": "gpt-5-mini",
            "worker": "gpt-4.1-mini",
            "aggregation": "gpt-5.4",
        },
    }
    finalization_summary = ledger.finalization.to_dict()
    runtime_metrics = {
        "batch_id": BATCH_ID,
        "round_count": 1,
        "final_state_version": 2,
        "status": "completed",
    }
    replay_metadata = {
        "fresh_execution": True,
    }

    persisted = save_phase3a_runtime_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        batch_ledger=ledger,
        initial_runtime_context=initial_runtime_context,
        finalization_summary=finalization_summary,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    return {
        "artifact_paths": persisted,
        "component_run": component_run,
        "batch_ledger": ledger,
        "initial_runtime_context": initial_runtime_context,
        "initial_state": initial_state,
        "finalization_summary": finalization_summary,
        "runtime_metrics": runtime_metrics,
        "replay_metadata": replay_metadata,
    }


def test_phase3a_components_menu_routes_phase3a_runtime():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "12"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "phase3a_runtime"
    assert "Phase 3A Batch Runtime" in cli._last_rendered
    assert "<available>" not in cli._last_rendered


def test_load_phase3a_runtime_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = _build_saved_phase3a_runtime_bundle(tmp_path)

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_phase3a_runtime_run_context(
        Path(bundle["artifact_paths"]["component_run_path"]).parent
    )

    assert isinstance(loaded, Phase3ARuntimeRunContext)
    assert loaded.component_run["batch_id"] == BATCH_ID
    assert loaded.batch_ledger["round_manifests"][0]["round_id"] == "round-001"
    assert loaded.finalization_summary["terminal_reason"] == "max_rounds_reached"


def test_load_phase3a_runtime_run_context_recovers_missing_round_manifests(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    runtime_run_dir = Path("phase3a_runtime_run_recovered")
    analysis_run_dir = Path("analysis_run_recovered")
    router_run_dir = Path("router_run_recovered")
    ranking_run_dir = Path("ranking_run_recovered")
    planner_run_dir = Path("planner_run_recovered")
    worker_run_dir = Path("worker_run_recovered")
    aggregation_run_dir = Path("aggregation_run_recovered")
    state_manager_run_dir = Path("state_manager_run_recovered")

    fake_bundle = {
        "artifact_paths": {
            "component_run_path": str(runtime_run_dir / "component_run.json"),
            "batch_ledger_path": str(runtime_run_dir / "batch_ledger.json"),
            "initial_state_path": str(runtime_run_dir / "initial_state.json"),
            "runtime_summary_path": str(runtime_run_dir / "runtime_summary.json"),
        },
        "component_run": {
            "batch_id": BATCH_ID,
            "status": "failed",
            "final_status": "failed",
            "terminal_reason": "aggregation returned a non-authoritative bundle.",
            "validation_ok": False,
            "final_state_version": 1,
            "round_count": 0,
            "model_name": "gpt-4.1-mini",
            "execution_mode": "full_batch",
        },
        "batch_ledger": {
            "batch_id": BATCH_ID,
            "dataset_path": "C:/data/runtime_dataset.csv",
            "model_name": "gpt-4.1-mini",
            "max_rounds": 1,
            "critic_enabled": False,
            "status": "failed",
            "initial_investigation_analysis_run_path": str(analysis_run_dir / "component_run.json"),
            "initial_state_path": "initial_state.json",
            "initial_state_version": 1,
            "round_manifests": [],
            "finalization": {
                "terminal_reason": "aggregation returned a non-authoritative bundle.",
                "final_state_manager_run_path": "",
                "final_batch_auditor_run_path": "",
                "final_state_version": 1,
                "final_status": "failed",
            },
        },
        "initial_runtime_context": {
            "dataset_path": "dataset.csv",
            "component_model_names": {
                "planner": "gpt-5-mini",
                "worker": "gpt-4.1-mini",
                "aggregation": "gpt-5.4",
            },
        },
        "initial_state": {"state_version": 1},
        "finalization_summary": {
            "terminal_reason": "aggregation returned a non-authoritative bundle.",
            "final_state_manager_run_path": "",
            "final_batch_auditor_run_path": "",
            "final_state_version": 1,
            "final_status": "failed",
        },
        "runtime_metrics": {
            "batch_id": BATCH_ID,
            "round_count": 0,
            "final_state_version": 1,
            "status": "failed",
        },
        "runtime_summary": {
            "batch_id": BATCH_ID,
            "round_count": 0,
            "status": "failed",
            "failed_components": ["round-001"],
            "errors": [
                {"message": "aggregation returned a non-authoritative bundle."}
            ],
        },
        "run_manifest": {},
        "event_stream": [],
        "terminal_log_text": "",
        "replay_metadata": {"fresh_execution": True},
    }

    analysis_bundle = {
        "artifact_paths": {
            "component_run_path": str(analysis_run_dir / "component_run.json"),
        },
        "component_run": {
            "component": "investigation_analysis",
            "batch_id": BATCH_ID,
            "status": "completed",
            "validation_ok": True,
        },
        "parsed_output": {
            "analysis_id": "analysis-runtime-001",
            "batch_id": BATCH_ID,
            "hypotheses": [
                {
                    "hypothesis_id": "hyp-runtime-1",
                    "summary": "Feature-local dependency pressure persists.",
                }
            ],
        },
    }

    router_bundle = {
        "artifact_paths": {
            "component_run_path": str(router_run_dir / "component_run.json"),
        },
        "component_run": {
            "component": "router",
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "hypothesis_id": "hyp-runtime-1",
            "planner_strategy_id": "strategy-runtime-1",
            "status": "completed",
            "validation_ok": True,
        },
        "parsed_output": {
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "hypothesis_id": "hyp-runtime-1",
            "planner_strategy_id": "strategy-runtime-1",
            "worker_tasks": [
                {"task_id": "task-runtime-1", "task_scope": "inspect feature drift"},
                {"task_id": "task-runtime-2",
                    "task_scope": "inspect routing pressure"},
            ],
        },
        "validation_report": {"ok": True, "errors": [], "warnings": []},
    }

    ranking_bundle = {
        "artifact_paths": {
            "component_run_path": str(ranking_run_dir / "component_run.json"),
        },
        "component_run": {
            "component": "hypothesis_ranking",
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "status": "completed",
            "validation_ok": True,
        },
        "parsed_output": {
            "selected_hypothesis_ids": ["hyp-runtime-1"],
            "deferred_hypothesis_ids": [],
        },
        "validation_report": {"ok": True, "errors": [], "warnings": []},
    }

    planner_bundle = {
        "artifact_paths": {
            "component_run_path": str(planner_run_dir / "component_run.json"),
        },
        "component_run": {
            "component": "planner",
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "status": "completed",
            "validation_ok": True,
        },
        "parsed_output": {
            "planner_strategies": [
                {
                    "hypothesis_id": "hyp-runtime-1",
                    "strategy_id": "strategy-runtime-1",
                }
            ]
        },
        "validation_report": {"ok": True, "errors": [], "warnings": []},
    }

    worker_bundle = {
        "artifact_paths": {
            "component_run_path": str(worker_run_dir / "component_run.json"),
        },
        "component_run": {
            "component": "worker",
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "hypothesis_id": "hyp-runtime-1",
            "task_id": "task-runtime-1",
            "status": "completed",
            "validation_ok": True,
            "result_committed": True,
        },
        "validation_report": {"ok": True, "errors": [], "warnings": []},
    }

    aggregation_bundle = {
        "artifact_paths": {
            "component_run_path": str(aggregation_run_dir / "component_run.json"),
            "parsed_output_path": str(aggregation_run_dir / "parsed_output.json"),
        },
        "component_run": {
            "component": "aggregation",
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "hypothesis_id": "hyp-runtime-1",
            "status": "error",
            "validation_ok": False,
            "handoff_committed": False,
            "authoritative_status": False,
        },
        "aggregation_handoff": {
            "update_focus": "Increase focus on the feature-local dependency pattern.",
            "merged_findings": ["Finding A"],
            "preserved_contradictions": ["Contradiction A"],
            "open_gaps": ["Gap A"],
            "evidence_refs": ["evidence-1"],
        },
        "worker_result_set": {
            "worker_results": [
                {"task_id": "task-runtime-1"},
                {"task_id": "task-runtime-2"},
            ]
        },
        "parsed_output": {
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "hypothesis_id": "hyp-runtime-1",
            "worker_result_set": {
                "worker_results": [
                    {"task_id": "task-runtime-1"},
                    {"task_id": "task-runtime-2"},
                ]
            },
            "aggregation_handoff": {
                "update_focus": "Increase focus on the feature-local dependency pattern.",
                "merged_findings": ["Finding A"],
                "preserved_contradictions": ["Contradiction A"],
                "open_gaps": ["Gap A"],
                "evidence_refs": ["evidence-1"],
            },
        },
        "validation_report": {
            "ok": False,
            "errors": [
                {
                    "field": "update_focus",
                    "message": "update_focus must stay under 160 characters.",
                }
            ],
            "warnings": [],
        },
        "runtime_metrics": {"cross_hypothesis_finding_count": 0},
    }

    state_manager_bundle = {
        "artifact_paths": {
            "component_run_path": str(state_manager_run_dir / "component_run.json"),
            "updated_batch_state_path": str(state_manager_run_dir / "updated_batch_state.json"),
        },
        "component_run": {
            "component": "state_manager",
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "hypothesis_id": "hyp-runtime-1",
            "status": "error",
            "validation_ok": False,
            "state_committed": False,
        },
        "prior_state": {"state_version": 1},
        "updated_batch_state": {"state_version": 2},
        "state_delta_record": {"state_version": 2},
        "state_manager_context": {},
        "rendered_prompt": "state-manager prompt",
        "raw_response": "state-manager response",
        "validation_report": {
            "ok": False,
            "errors": [
                {
                    "field": "update_focus",
                    "message": "state_manager returned a non-authoritative bundle.",
                }
            ],
            "warnings": [],
        },
        "runtime_metrics": {"duration_ms": 1.0},
        "replay_metadata": {"deterministic": False},
    }

    monkeypatch.setattr(
        cli_module, "load_phase3a_runtime_bundle", lambda run_dir: fake_bundle)
    monkeypatch.setattr(
        cli_module, "load_investigation_analysis_bundle", lambda run_dir: analysis_bundle)
    monkeypatch.setattr(cli, "_load_optional_component_context", lambda component_run_path, loader: {
        "component_run_path": component_run_path,
        "loader_name": loader.__name__,
    } if component_run_path else None)
    monkeypatch.setattr(cli_module, "list_router_run_dirs",
                        lambda limit=None: [router_run_dir])
    monkeypatch.setattr(cli_module, "load_router_bundle",
                        lambda run_dir: router_bundle)
    monkeypatch.setattr(cli_module, "list_hypothesis_ranking_run_dirs",
                        lambda limit=None: [ranking_run_dir])
    monkeypatch.setattr(
        cli_module, "load_hypothesis_ranking_bundle", lambda run_dir: ranking_bundle)
    monkeypatch.setattr(cli_module, "list_planner_run_dirs",
                        lambda limit=None: [planner_run_dir])
    monkeypatch.setattr(cli_module, "load_planner_bundle",
                        lambda run_dir: planner_bundle)
    monkeypatch.setattr(cli_module, "list_worker_run_dirs",
                        lambda limit=None: [worker_run_dir])
    monkeypatch.setattr(cli_module, "load_worker_bundle",
                        lambda run_dir: worker_bundle)
    monkeypatch.setattr(cli_module, "list_aggregation_run_dirs",
                        lambda limit=None: [aggregation_run_dir])
    monkeypatch.setattr(cli_module, "load_aggregation_bundle",
                        lambda run_dir: aggregation_bundle)
    monkeypatch.setattr(cli_module, "list_state_manager_run_dirs",
                        lambda limit=None: [state_manager_run_dir])
    monkeypatch.setattr(cli_module, "load_state_manager_bundle",
                        lambda run_dir: state_manager_bundle)
    monkeypatch.setattr(cli_module, "list_critic_run_dirs",
                        lambda limit=None: [])
    monkeypatch.setattr(cli_module, "load_inter_hypothesis_bundle", lambda run_dir: {
        "component_run": {
            "component": "inter_hypothesis_aggregation",
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "status": "failed",
            "validation_ok": False,
            "authoritative_status": False,
        },
        "parsed_output": {
            "batch_id": BATCH_ID,
            "round_id": "round-001",
            "selected_hypothesis_ids": ["hyp-runtime-1"],
            "source_hypothesis_records": [
                {
                    "hypothesis_id": "hyp-runtime-1",
                    "merged_findings": ["merged-hyp-runtime-1"],
                    "evidence_refs": ["evidence-hyp-runtime-1"],
                    "preserved_contradictions": [],
                    "open_gaps": ["gap-hyp-runtime-1"],
                    "limitations": ["limitation-hyp-runtime-1"],
                    "update_focus": "focus-hyp-runtime-1",
                    "provenance": {"source_order": 0},
                }
            ],
        },
        "validation_report": {"ok": False},
        "rendered_prompt": "prompt",
        "raw_response": "response",
        "runtime_metrics": {"source_record_count": 1},
        "replay_metadata": {"deterministic": False},
    })

    loaded = cli._load_phase3a_runtime_run_context(runtime_run_dir)

    assert loaded.component_run["round_count"] == 1
    assert loaded.runtime_summary["round_count"] == 1
    assert loaded.runtime_metrics["round_count"] == 1
    assert len(loaded.batch_ledger["round_manifests"]) == 1

    round_manifest = loaded.batch_ledger["round_manifests"][0]
    assert round_manifest["round_id"] == "round-001"
    assert round_manifest["analysis_run_path"] == str(
        analysis_run_dir / "component_run.json")
    assert round_manifest["global_aggregation_path"].endswith(
        "parsed_output.json")
    assert round_manifest["hypothesis_runs"][0]["state_manager_run_path"] == str(
        state_manager_run_dir / "component_run.json")

    round_context = cli._build_phase3a_runtime_round_context(round_manifest)

    assert round_context.round_manifest["round_id"] == "round-001"
    assert round_context.frozen_snapshot["batch_id"] == BATCH_ID
    assert round_context.frozen_snapshot["initial_hypothesis_set_ref"]["analysis_id"] == "analysis-runtime-001"
    assert round_context.global_aggregation_summary["component_run"]["status"] == "failed"
    assert round_context.global_aggregation_summary["validation_report"]["ok"] is False
    assert round_context.global_aggregation_summary["parsed_output"]["selected_hypothesis_ids"] == [
        "hyp-runtime-1"]
    assert round_context.global_aggregation_summary["parsed_output"][
        "source_hypothesis_records"][0]["hypothesis_id"] == "hyp-runtime-1"
    assert round_context.analysis_run["component_run_path"] == str(
        analysis_run_dir / "component_run.json")
    assert round_context.analysis_run["component_run_path"] == str(
        analysis_run_dir / "component_run.json")
    expected = Phase3ARuntimeRunContext(
        artifact_paths={
            "component_run_path": "phase3a_runtime_run_good/component_run.json"},
        component_run={"batch_id": BATCH_ID, "status": "completed"},
        batch_ledger={"round_manifests": []},
        initial_runtime_context={},
        initial_state={},
        finalization_summary={},
        runtime_metrics={},
        replay_metadata=None,
    )

    monkeypatch.setattr(
        cli_module,
        "list_phase3a_runtime_run_dirs",
        lambda limit=None: [bad_dir, good_dir],
    )

    def _fake_load(run_dir: Path):
        if run_dir == bad_dir:
            raise FileNotFoundError("component_run.json missing")
        return expected

    monkeypatch.setattr(cli, "_load_phase3a_runtime_run_context", _fake_load)

    loaded = cli._get_latest_phase3a_runtime_run_context()

    assert loaded is expected


def test_render_phase3a_runtime_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = Phase3ARuntimeRunContext(
        artifact_paths={
            "component_run_path": "phase3a_runtime_run_001/component_run.json",
            "batch_ledger_path": "phase3a_runtime_run_001/batch_ledger.json",
            "initial_state_path": "phase3a_runtime_run_001/initial_state.json",
            "finalization_summary_path": "phase3a_runtime_run_001/finalization_summary.json",
            "runtime_metrics_path": "phase3a_runtime_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": BATCH_ID,
            "model_name": "gpt-4.1-mini",
            "status": "completed",
            "final_status": "completed",
            "terminal_reason": "max_rounds_reached",
            "round_count": 1,
            "final_state_version": 2,
        },
        batch_ledger={"batch_id": BATCH_ID,
                      "round_manifests": [{"round_id": "round-001"}]},
        initial_runtime_context={"dataset_path": "dataset.csv"},
        initial_state={"state_version": 1},
        finalization_summary={"terminal_reason": "max_rounds_reached"},
        runtime_metrics={"duration_ms": 11.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_phase3a_runtime_run_review(run_context)

    assert BATCH_ID in cli._last_rendered
    assert "Runtime Execution Tree" in cli._last_rendered
    assert "batch_ledger.json" in cli._last_rendered
    assert "finalization_summary.json" in cli._last_rendered
    assert "execution_mode" in cli._last_rendered
    assert "planning_model" in cli._last_rendered
    assert "Review Semantic Extraction" in cli._last_rendered
    assert "Review Hypothesis Generation" in cli._last_rendered
    assert "Browse Hypothesis Ranking Tree" in cli._last_rendered
    assert "Browse Router / Worker / Aggregation Tree" in cli._last_rendered
    assert "Review Statement / Final Batch Auditor" in cli._last_rendered
    assert "View Runtime Execution Log" in cli._last_rendered
    assert "View Structured Runtime Event Stream" in cli._last_rendered
    assert "Inspect Runtime Overview" in cli._last_rendered
    assert "Inspect Batch Ledger" in cli._last_rendered


def test_build_phase3a_runtime_round_context_resolves_round_artifacts(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    loader_hits: list[tuple[str, str]] = []
    loaded_bundles: list[str] = []

    def _fake_load_json_if_available(artifact_path: str) -> dict[str, object]:
        return {"snapshot_path": artifact_path}

    def _fake_load_inter_hypothesis_bundle(run_dir: Path) -> dict[str, object]:
        loaded_bundles.append(run_dir.name)
        return {
            "component_run": {
                "component": "inter_hypothesis_aggregation",
                "status": "failed",
                "validation_ok": False,
                "authoritative_status": False,
            },
            "parsed_output": {
                "batch_id": BATCH_ID,
                "round_id": "round-001",
                "selected_hypothesis_ids": ["hyp-runtime-1"],
                "source_hypothesis_records": [
                    {
                        "hypothesis_id": "hyp-runtime-1",
                        "merged_findings": ["merged-hyp-runtime-1"],
                        "evidence_refs": ["evidence-hyp-runtime-1"],
                        "preserved_contradictions": [],
                        "open_gaps": ["gap-hyp-runtime-1"],
                        "limitations": ["limitation-hyp-runtime-1"],
                        "update_focus": "focus-hyp-runtime-1",
                        "provenance": {"source_order": 0},
                    }
                ],
            },
            "validation_report": {"ok": False},
            "rendered_prompt": "prompt",
            "raw_response": "response",
            "runtime_metrics": {"source_record_count": 1},
            "replay_metadata": {"deterministic": False},
        }

    def _fake_load_optional_component_context(component_run_path: str, loader):
        loader_hits.append((component_run_path, loader.__name__))
        return {"component_run_path": component_run_path, "loader_name": loader.__name__}

    monkeypatch.setattr(cli, "_load_json_if_available",
                        _fake_load_json_if_available)
    monkeypatch.setattr(cli, "_load_optional_component_context",
                        _fake_load_optional_component_context)
    monkeypatch.setattr(cli_module, "load_inter_hypothesis_bundle",
                        _fake_load_inter_hypothesis_bundle)

    round_context = cli._build_phase3a_runtime_round_context(
        {
            "round_id": "round-001",
            "frozen_snapshot_path": "snapshot.json",
            "global_aggregation_path": "inter_hypothesis_aggregation/component_run.json",
            "analysis_run_path": "analysis/component_run.json",
            "ranking_run_path": "ranking/component_run.json",
            "planner_run_path": "planner/component_run.json",
            "critic_run_path": "critic/component_run.json",
        }
    )

    assert isinstance(round_context, Phase3ARuntimeRoundContext)
    assert round_context.frozen_snapshot["snapshot_path"] == "snapshot.json"
    assert round_context.global_aggregation_summary["component_run"][
        "component"] == "inter_hypothesis_aggregation"
    assert round_context.global_aggregation_summary["parsed_output"]["selected_hypothesis_ids"] == [
        "hyp-runtime-1"]
    assert round_context.analysis_run["component_run_path"] == "analysis/component_run.json"
    assert round_context.ranking_run["component_run_path"] == "ranking/component_run.json"
    assert round_context.planner_run["component_run_path"] == "planner/component_run.json"
    assert round_context.critic_run["component_run_path"] == "critic/component_run.json"
    assert loaded_bundles == ["inter_hypothesis_aggregation"]
    assert [name for _, name in loader_hits] == [
        "_load_investigation_analysis_run_context",
        "_load_hypothesis_ranking_run_context",
        "_load_planner_run_context",
        "_load_critic_run_context",
    ]


def test_build_phase3a_hypothesis_lineage_context_resolves_full_lineage(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    worker_hits: list[str] = []

    def _fake_load_optional_component_context(component_run_path: str, loader):
        if loader.__name__ == "_load_worker_run_context":
            worker_hits.append(component_run_path)
        return {"component_run_path": component_run_path, "loader_name": loader.__name__}

    monkeypatch.setattr(cli, "_load_optional_component_context",
                        _fake_load_optional_component_context)

    lineage_context = cli._build_phase3a_hypothesis_lineage_context(
        {
            "hypothesis_id": "hyp-runtime-1",
            "router_run_path": "router/component_run.json",
            "worker_run_paths": [
                "worker/task-runtime-1/component_run.json",
                "worker/task-runtime-2/component_run.json",
            ],
            "aggregation_run_path": "aggregation/component_run.json",
            "state_manager_run_path": "state_manager/component_run.json",
        }
    )

    assert isinstance(lineage_context, Phase3AHypothesisLineageContext)
    assert lineage_context.router_run["component_run_path"] == "router/component_run.json"
    assert [worker_run["component_run_path"] for worker_run in lineage_context.worker_runs] == [
        "worker/task-runtime-1/component_run.json",
        "worker/task-runtime-2/component_run.json",
    ]
    assert lineage_context.aggregation_run["component_run_path"] == "aggregation/component_run.json"
    assert lineage_context.state_manager_run["component_run_path"] == "state_manager/component_run.json"
    assert worker_hits == [
        "worker/task-runtime-1/component_run.json",
        "worker/task-runtime-2/component_run.json",
    ]


def test_build_phase3a_state_evolution_payload_summarizes_hypothesis_updates():
    cli = object.__new__(NidsAgentCli)
    run_context = Phase3ARuntimeRunContext(
        artifact_paths={
            "component_run_path": "phase3a_runtime_run_001/component_run.json"},
        component_run={"batch_id": BATCH_ID},
        batch_ledger={
            "round_manifests": [
                {
                    "round_id": "round-001",
                    "start_state_version": 1,
                    "end_state_version": 2,
                    "terminal_reason": "continue",
                    "hypothesis_runs": [
                        {
                            "hypothesis_id": "hyp-runtime-1",
                            "planner_strategy_id": "strategy-runtime-1",
                            "start_state_version": 1,
                            "end_state_version": 2,
                            "state_manager_run_path": "state_manager/component_run.json",
                        }
                    ],
                }
            ]
        },
        initial_runtime_context={"dataset_path": "dataset.csv"},
        initial_state={"state_version": 1},
        finalization_summary={"final_state_version": 2,
                              "terminal_reason": "max_rounds_reached"},
        runtime_metrics={"duration_ms": 11.0},
        replay_metadata=None,
    )

    payload = cli._build_phase3a_state_evolution_payload(run_context)

    assert payload["initial_state_version"] == 1
    assert payload["final_state_version"] == 2
    assert payload["rounds"][0]["round_id"] == "round-001"
    assert payload["rounds"][0]["hypothesis_state_updates"][0]["hypothesis_id"] == "hyp-runtime-1"


def test_render_phase3a_runtime_round_review_includes_default_hypothesis_preview(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    round_context = Phase3ARuntimeRoundContext(
        round_manifest={
            "round_id": "round-001",
            "analysis_mode": "initial",
            "status": "completed",
            "terminal_reason": "continue",
            "start_state_version": 1,
            "end_state_version": 2,
            "selected_hypothesis_ids": ["hyp-runtime-1"],
            "deferred_hypothesis_ids": [],
            "hypothesis_runs": [
                {
                    "hypothesis_id": "hyp-runtime-1",
                    "planner_strategy_id": "strategy-runtime-1",
                    "worker_run_paths": ["worker/task-1/component_run.json"],
                }
            ],
        },
        frozen_snapshot={"batch_id": BATCH_ID},
        global_aggregation_summary={},
        analysis_run=type("AnalysisStub", (), {"component_run": {
                          "batch_id": BATCH_ID, "created_at": "2026-01-01T00:00:30+00:00"}})(),
        ranking_run=None,
        planner_run=None,
        critic_run=None,
    )
    lineage_context = Phase3AHypothesisLineageContext(
        hypothesis_record={"hypothesis_id": "hyp-runtime-1",
                           "planner_strategy_id": "strategy-runtime-1"},
        router_run=RouterRunContext(
            artifact_paths={},
            component_run={},
            planner_strategy={
                "strategic_objective": "Pressure the dependency-locality tension with one bounded check."},
            router_context_min={},
            reduced_context={},
            prompt_text="",
            raw_response_text="",
            parsed_output={},
            task_bundle_index={},
            validation_report={},
            runtime_metrics={},
            replay_metadata=None,
        ),
        worker_runs=[],
        aggregation_run=AggregationRunContext(
            artifact_paths={},
            component_run={"status": "completed"},
            worker_result_set={},
            normalized_inputs={},
            overlap_diagnostics=[],
            prompt_text="",
            raw_response_text="",
            parsed_output={},
            aggregation_handoff={
                "update_focus": "Dependency signal versus localized shortcut evidence.",
                "preserved_contradictions": ["The local shortcut still pressures the dependency view."],
            },
            repair_attempts=[],
            validation_report={},
            runtime_metrics={},
            replay_metadata=None,
        ),
        state_manager_run=None,
    )

    monkeypatch.setattr(
        cli, "_build_phase3a_hypothesis_lineage_context", lambda record: lineage_context)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)

    cli._render_phase3a_runtime_round_review(round_context)

    assert "Default Hypothesis" in cli._last_rendered
    assert "Pressure the dependency-locality tension" in cli._last_rendered
    assert "aggregation=completed | contradictions=1" in cli._last_rendered
    assert "created_at" in cli._last_rendered
    assert "worker_runs" in cli._last_rendered
    assert "Review Inter-Hypothesis Aggregation" in cli._last_rendered


def test_render_phase3a_runtime_hypothesis_review_includes_default_worker_preview():
    cli = object.__new__(NidsAgentCli)
    worker_run = WorkerRunContext(
        artifact_paths={
            "component_run_path": "worker/task-1/component_run.json"},
        component_run={
            "task_id": "task-1",
            "status": "ok",
            "worker_status": "completed",
        },
        worker_task={
            "task_scope": "Check whether the dependency signal survives one localized pressure probe.",
            "allowed_actions": ["relation_verification", "distribution_verification"],
            "local_context_refs": ["e1", "e3"],
        },
        worker_runtime_refs={},
        prompt_snapshots=[
            {
                "step_index": 1,
                "step_mode": "final_synthesis",
                "attempt_index": 0,
                "prompt_text": "prompt-1",
                "repair_note": None,
            }
        ],
        raw_model_responses=[
            {
                "step_index": 1,
                "step_mode": "final_synthesis",
                "attempt_index": 0,
                "raw_response_text": "response-1",
            }
        ],
        parsed_steps=[
            {
                "step_index": 1,
                "step_mode": "final_synthesis",
                "attempt_index": 0,
                "parsed_step": {
                    "decision": "finish",
                    "reasoning": "Final bounded synthesis.",
                    "worker_result": {
                        "status": "completed",
                        "findings": ["finding-1"],
                        "contradictions": ["contradiction-1"],
                        "limitations": ["limitation-1"],
                    },
                },
                "validation": {"ok": True, "warnings": [], "errors": []},
            }
        ],
        tool_events=[],
        retry_events=[],
        failure_events=[],
        worker_result={
            "status": "completed",
            "findings": ["finding-1"],
            "contradictions": ["contradiction-1"],
            "limitations": ["limitation-1"],
        },
        worker_output={"worker_result": {"status": "completed"}},
        operational_trace={},
        validation_report={},
        runtime_metrics={},
        replay_metadata=None,
    )
    lineage_context = Phase3AHypothesisLineageContext(
        hypothesis_record={
            "hypothesis_id": "hyp-runtime-1",
            "planner_strategy_id": "strategy-runtime-1",
            "status": "completed",
            "task_ids": ["task-1"],
            "start_state_version": 1,
            "end_state_version": 2,
        },
        router_run=RouterRunContext(
            artifact_paths={},
            component_run={},
            planner_strategy={
                "strategic_objective": "Pressure the dependency-locality tension with one bounded check."},
            router_context_min={},
            reduced_context={},
            prompt_text="",
            raw_response_text="",
            parsed_output={},
            task_bundle_index={},
            validation_report={},
            runtime_metrics={},
            replay_metadata=None,
        ),
        worker_runs=[worker_run],
        aggregation_run=AggregationRunContext(
            artifact_paths={},
            component_run={"status": "completed"},
            worker_result_set={},
            normalized_inputs={},
            overlap_diagnostics=[],
            prompt_text="",
            raw_response_text="",
            parsed_output={},
            aggregation_handoff={
                "update_focus": "Dependency signal versus localized shortcut evidence.",
                "preserved_contradictions": ["The local shortcut still pressures the dependency view."],
            },
            repair_attempts=[],
            validation_report={},
            runtime_metrics={},
            replay_metadata=None,
        ),
        state_manager_run=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)

    cli._render_phase3a_runtime_hypothesis_review(lineage_context)

    assert "Default Worker Task" in cli._last_rendered
    assert "latest_step: 1 (final_synthesis) | decision=finish | flags=0" in cli._last_rendered
    assert "aggregation_status" in cli._last_rendered
    assert "synthesis" in cli._last_rendered


def test_view_phase3a_runtime_worker_runs_menu_renders_enriched_worker_lines():
    cli = object.__new__(NidsAgentCli)
    worker_run = WorkerRunContext(
        artifact_paths={
            "component_run_path": "worker/task-1/component_run.json"},
        component_run={
            "task_id": "task-1",
            "status": "ok",
            "worker_status": "completed",
        },
        worker_task={
            "task_scope": "Check whether the dependency signal survives one localized pressure probe.",
            "allowed_actions": ["relation_verification", "distribution_verification"],
            "local_context_refs": ["e1", "e3"],
        },
        worker_runtime_refs={},
        prompt_snapshots=[],
        raw_model_responses=[],
        parsed_steps=[],
        tool_events=[],
        retry_events=[],
        failure_events=[],
        worker_result={
            "status": "completed",
            "findings": ["finding-1"],
            "contradictions": ["contradiction-1"],
            "limitations": ["limitation-1"],
        },
        worker_output={"worker_result": {"status": "completed"}},
        operational_trace={},
        validation_report={},
        runtime_metrics={},
        replay_metadata=None,
    )
    lineage_context = Phase3AHypothesisLineageContext(
        hypothesis_record={"hypothesis_id": "hyp-runtime-1"},
        router_run=None,
        worker_runs=[worker_run],
        aggregation_run=None,
        state_manager_run=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "B"
    cli._quit = lambda: None
    cli._running = True

    cli._view_phase3a_runtime_worker_runs_menu(lineage_context)

    assert "Worker Tasks" in cli._last_rendered
    assert "scope=Check whether the dependency signal survives one localized pressure" in cli._last_rendered
    assert "findings=1 | contradictions=1 | limitations=1" in cli._last_rendered


def test_run_phase3a_runtime_flow_builds_reviewable_context(monkeypatch, tmp_path: Path):
    bundle = _build_saved_phase3a_runtime_bundle(tmp_path)
    captured_call: dict[str, object] = {}

    def _fake_run_phase3a_batch(dataset_path, **kwargs):
        captured_call["dataset_path"] = dataset_path
        captured_call.update(kwargs)
        return bundle

    monkeypatch.setattr(cli_module, "run_phase3a_batch",
                        _fake_run_phase3a_batch)

    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._get_selected_dataset_path = lambda: Path("dataset.csv")
    cli._prompt_yes_no = lambda prompt, default=False: False
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "B"
    cli._quit = lambda: None
    cli._show_error = lambda message: (
        _ for _ in ()).throw(AssertionError(message))

    route = cli._run_phase3a_runtime_flow()

    assert route == "phase3a_runtime"
    assert captured_call["dataset_path"] == Path("dataset.csv")
    assert captured_call["model_name"] == "gpt-4.1-mini"
    assert captured_call["max_rounds"] == 3
    assert captured_call["execution_mode"] == "full_batch"
    assert captured_call["enable_critic"] is True
    assert captured_call["caller_mode"] == "cli"
    assert captured_call["component_model_names"]["planner"] == "gpt-4.1-mini"
    assert set(captured_call["llm_callables"]) >= {
        "planner", "worker", "aggregation"}
    assert isinstance(cli._last_phase3a_runtime_run, Phase3ARuntimeRunContext)
    assert cli._selected_phase3a_runtime_run is cli._last_phase3a_runtime_run
    assert cli._last_phase3a_runtime_run.component_run["batch_id"] == BATCH_ID


def test_run_phase3a_runtime_flow_can_disable_neighborhood_analysis(monkeypatch, tmp_path: Path):
    bundle = _build_saved_phase3a_runtime_bundle(tmp_path)
    captured_call: dict[str, object] = {}
    original_env_value = cli_module.os.environ.get(
        "PHASE3A_ENABLE_NEIGHBORHOOD_CONSISTENCY_ANALYSIS"
    )

    def _fake_run_phase3a_batch(dataset_path, **kwargs):
        captured_call["dataset_path"] = dataset_path
        captured_call["env_value"] = cli_module.os.environ.get(
            "PHASE3A_ENABLE_NEIGHBORHOOD_CONSISTENCY_ANALYSIS"
        )
        captured_call.update(kwargs)
        return bundle

    monkeypatch.setattr(cli_module, "run_phase3a_batch",
                        _fake_run_phase3a_batch)

    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._get_selected_dataset_path = lambda: Path("dataset.csv")
    cli._prompt_yes_no = lambda prompt, default=False: True
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "B"
    cli._quit = lambda: None
    cli._show_error = lambda message: (
        _ for _ in ()).throw(AssertionError(message))

    route = cli._run_phase3a_runtime_flow()

    assert route == "phase3a_runtime"
    assert cli.session_config.enable_neighborhood_consistency_analysis is False
    assert captured_call["env_value"] == "0"
    assert cli_module.os.environ.get(
        "PHASE3A_ENABLE_NEIGHBORHOOD_CONSISTENCY_ANALYSIS"
    ) == original_env_value
