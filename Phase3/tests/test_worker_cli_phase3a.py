import json
from pathlib import Path

import pandas as pd

from interface.cli import InvestigationAnalysisRunContext, NidsAgentCli, RouterRunContext, WorkerRunContext
from worker.runner import run_worker


def _write_dataset(tmp_path: Path) -> Path:
    dataset_path = tmp_path / "worker_cli_fixture.csv"
    pd.DataFrame(
        {
            "src_bytes": [10, 12, 100, 105],
            "dst_bytes": [11, 13, 101, 106],
            "dst_port": [80, 80, 443, 443],
            "Label": ["BENIGN", "BENIGN", "ATTACK", "ATTACK"],
        }
    ).to_csv(dataset_path, index=False)
    return dataset_path


def _build_worker_task() -> dict[str, object]:
    return {
        "task_id": "task-hyp-1-1",
        "hypothesis_id": "hyp-1",
        "task_scope": "Probe whether the broad dependency signal remains stronger than the narrow local port signal.",
        "allowed_actions": ["relation_verification", "shortcut_verification"],
        "local_context_refs": ["e1", "e3"],
        "stop_conditions": [
            "Stop when one local strengthening or weakening signal changes the comparison.",
            "Stop when the worker budget is exhausted.",
        ],
    }


def _build_worker_runtime_refs(dataset_path: Path) -> dict[str, object]:
    return {
        "tool_handles": {},
        "dataset_handles": {
            "dataset_path": str(dataset_path),
            "semantic_substrate": {
                "compressed_regions": [
                    {
                        "region_id": "region-1",
                        "summary": "Broad dependency structure links src_bytes and dst_bytes.",
                        "feature_scope": {
                            "features": ["src_bytes", "dst_bytes"],
                            "feature_groups": ["flow_size"],
                            "locality": {
                                "scope_type": "partition_global",
                                "scope_value": "batch-001",
                                "localized": False,
                                "notes": ["Broad dependency evidence."],
                            },
                        },
                        "evidence_refs": ["e1"],
                    }
                ],
                "preserved_weak_signals": [
                    {
                        "weak_signal_id": "weak-1",
                        "descriptor": "Localized dst_port separability remains narrow.",
                        "feature_scope": {
                            "features": ["dst_port"],
                            "feature_groups": ["port_behavior"],
                            "locality": {
                                "scope_type": "feature_group",
                                "scope_value": "port_behavior",
                                "localized": True,
                                "notes": ["Narrow local port signal."],
                            },
                        },
                        "evidence_refs": ["e3"],
                    }
                ],
                "contradictions": [],
                "unresolved_tensions": [],
            },
        },
        "budget_rules": {
            "max_steps": 4,
            "max_retries": 1,
        },
    }


def _build_saved_worker_bundle(tmp_path: Path) -> dict[str, object]:
    dataset_path = _write_dataset(tmp_path)
    responses = iter(
        [
            json.dumps(
                {
                    "decision": "action",
                    "action": {
                        "action_class": "relation_verification",
                        "context_ref": "e1",
                        "feature_name": "src_bytes",
                        "related_feature_name": "dst_bytes",
                    },
                }
            ),
            json.dumps(
                {
                    "decision": "finish",
                    "worker_result": {
                        "task_id": "task-hyp-1-1",
                        "hypothesis_id": "hyp-1",
                        "status": "completed",
                        "findings": [
                            "The broad dependency pair remained strong in the local slice."
                        ],
                        "evidence_refs": ["task-hyp-1-1_step_01"],
                        "contradictions": [],
                        "limitations": [],
                    },
                }
            ),
        ]
    )
    return run_worker(
        _build_worker_task(),
        _build_worker_runtime_refs(dataset_path),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker"),
    )


def test_phase3a_components_menu_routes_worker():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "6"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "worker"
    assert "Worker" in cli._last_rendered


def test_load_worker_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = _build_saved_worker_bundle(tmp_path)

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_worker_run_context(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, WorkerRunContext)
    assert loaded.component_run["round_id"] == "round-001"
    assert loaded.parsed_steps[-1]["parsed_step"]["decision"] == "finish"
    assert len(loaded.prompt_snapshots) == 2
    assert len(loaded.raw_model_responses) == 2


def test_render_worker_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = WorkerRunContext(
        artifact_paths={
            "component_run_path": "worker_run_001/component_run.json",
            "worker_task_path": "worker_run_001/worker_task.json",
            "worker_result_path": "worker_run_001/worker_result.json",
            "validation_report_path": "worker_run_001/validation_report.json",
            "runtime_metrics_path": "worker_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "round_id": "round-001",
            "task_id": "task-hyp-1-1",
            "hypothesis_id": "hyp-1",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "worker_status": "completed",
            "validation_ok": True,
        },
        worker_task={"task_id": "task-hyp-1-1"},
        worker_runtime_refs={"dataset_handles": {
            "dataset_path": "dataset.csv"}},
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
                    "reasoning": "Bounded task completed.",
                    "worker_result": {"status": "completed", "findings": ["finding-1"]},
                },
                "validation": {"ok": True, "warnings": [], "errors": []},
            }
        ],
        tool_events=[{"tool_name": "feature_relation"}],
        retry_events=[],
        failure_events=[],
        worker_result={"status": "completed", "findings": ["finding-1"]},
        worker_output={"worker_result": {"status": "completed"}},
        operational_trace={},
        validation_report={},
        runtime_metrics={"duration_ms": 10.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_worker_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "task-hyp-1-1" in cli._last_rendered
    assert "worker_task.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered
    assert "Latest Step (Default)" in cli._last_rendered
    assert "Browse Step Timeline" in cli._last_rendered
    assert "Inspect Latest Step" in cli._last_rendered


def test_handle_worker_review_choice_opens_latest_step_review():
    cli = object.__new__(NidsAgentCli)
    captured: dict[str, object] = {}
    run_context = WorkerRunContext(
        artifact_paths={
            "component_run_path": "worker_run_001/component_run.json"},
        component_run={
            "task_id": "task-hyp-1-1",
            "status": "ok",
            "worker_status": "completed",
        },
        worker_task={"task_id": "task-hyp-1-1"},
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
                    "reasoning": "reasoning-1",
                    "worker_result": {"status": "completed"},
                },
                "validation": {"ok": True, "warnings": [], "errors": []},
            }
        ],
        tool_events=[],
        retry_events=[],
        failure_events=[],
        worker_result={"status": "completed"},
        worker_output={"worker_result": {"status": "completed"}},
        operational_trace={},
        validation_report={},
        runtime_metrics={},
        replay_metadata=None,
    )

    cli._view_worker_step_review_menu = lambda context, step_trace: captured.update(
        {
            "task_id": context.component_run["task_id"],
            "step_index": step_trace.step_index,
            "decision": step_trace.decision,
        }
    )
    cli._show_error = lambda message: (
        _ for _ in ()).throw(AssertionError(message))

    cli._handle_worker_review_choice("3", run_context)

    assert captured == {
        "task_id": "task-hyp-1-1",
        "step_index": 1,
        "decision": "finish",
    }


def test_build_worker_runtime_refs_passes_semantic_substrate_through_cli():
    cli = object.__new__(NidsAgentCli)
    router_run = RouterRunContext(
        artifact_paths={},
        component_run={},
        planner_strategy={},
        router_context_min={"execution_budget": {
            "max_worker_steps": 4, "max_retries": 1}},
        reduced_context={},
        prompt_text="",
        raw_response_text="",
        parsed_output={},
        task_bundle_index={},
        validation_report={},
        runtime_metrics={},
        replay_metadata=None,
    )
    semantic_substrate = _build_worker_runtime_refs(
        Path("dataset.csv"))["dataset_handles"]["semantic_substrate"]
    investigation_run = InvestigationAnalysisRunContext(
        artifact_paths={},
        component_run={"batch_id": "batch-001"},
        semantic_substrate_input=semantic_substrate,
        analysis_context_min={},
        analysis_iteration_context_min={},
        projected_substrate={},
        projected_analysis_context={},
        projected_iteration_context={},
        prompt_text="",
        raw_response_text="",
        parsed_output={},
        hypothesis_index={},
        validation_report={},
        runtime_metrics={},
        replay_metadata=None,
    )

    runtime_refs = cli._build_worker_runtime_refs(
        router_run,
        _build_worker_task(),
        investigation_run,
        Path("dataset.csv"),
    )

    assert runtime_refs["dataset_handles"]["dataset_path"] == "dataset.csv"
    assert runtime_refs["dataset_handles"]["semantic_substrate"] == semantic_substrate
    assert "local_context_records" not in runtime_refs["dataset_handles"]
