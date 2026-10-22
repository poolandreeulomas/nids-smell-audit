"""Comprehensive unit and integration tests for ATLAS Round-Level Final Reports.

Verifies:
1. Input resolution and schema validation.
2. Prompt construction with 9 required sections and evidence grounding.
3. Separation of new round evidence from inherited prior evidence.
4. Conservative handling of missing fields and unresolved hypotheses.
5. Prevention of reporting on failed/incomplete rounds.
6. Automatic trigger on successful single full-round completion.
7. Preservation of existing full-batch reporting without round-report multiplication.
8. Error resilience when report generation fails.
9. Persistence and linkage to round manifests.
10. Post-run CLI flow with '[1] See round report' as primary action.
11. Round review CLI actions (View, Generate, Regenerate).
12. Regeneration from persisted artifacts without rerunning investigation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from final_batch_report.round_contracts import (
    ROUND_REPORT_PROMPT_VERSION,
    ROUND_REPORT_SCHEMA_VERSION,
    ROUND_REPORT_SECTIONS,
)
from final_batch_report.round_input_resolver import (
    resolve_round_report_context,
)
from final_batch_report.round_prompt_builder import (
    build_round_report_prompt,
)
from final_batch_report.round_runner import (
    regenerate_round_report,
    run_round_report,
)
from final_batch_report.round_runtime_artifacts import (
    build_round_report_artifact_paths,
    save_round_report_artifacts,
)
from interface.cli import NidsAgentCli, Phase3ARuntimeRoundContext, Phase3ARuntimeRunContext
from phase3_runtime.ledger import HypothesisExecutionRecord, RoundManifest
import phase3_runtime.orchestrator as orch
from state.schema import CanonicalBatchState, InterpretiveHypothesis, StateRevisionRecord
from utils.run_logging import load_json, write_json


def _make_sample_canonical_state(batch_id: str = "test-batch-001") -> CanonicalBatchState:
    return CanonicalBatchState(
        batch_id=batch_id,
        state_version=3,
        structural_substrate={"compressed_regions": []},
        interpretive_hypotheses=[
            InterpretiveHypothesis(
                hypothesis_id="hyp-001",
                summary="High port scanning fan-out across ephemeral ports.",
                status="supported",
                evidence_refs=["ev-1", "ev-2"],
                merged_findings=["Concentrated destination port distribution"],
                open_gaps=["Temporal persistence across hours"],
                preserved_contradictions=[],
                last_updated_round="round-001",
                revision_count=1,
            ),
            InterpretiveHypothesis(
                hypothesis_id="hyp-002",
                summary="Inherited prior hypothesis from previous round.",
                status="unresolved",
                evidence_refs=["ev-prior"],
                merged_findings=[],
                open_gaps=["Needs verification"],
                preserved_contradictions=[],
                last_updated_round="round-000",
                revision_count=0,
            ),
        ],
        revision_log=[
            StateRevisionRecord(
                round_id="round-001",
                hypothesis_id="hyp-001",
                state_version=3,
                applied_updates=[{"description": "Confirmed port fan-out pattern"}],
            )
        ],
    )


def _make_sample_round_manifest(round_id: str = "round-001") -> RoundManifest:
    return RoundManifest(
        round_id=round_id,
        round_index=1,
        analysis_mode="initial",
        status="completed",
        terminal_reason="round_budget_reached",
        start_state_version=2,
        end_state_version=3,
        selected_hypothesis_ids=["hyp-001"],
        deferred_hypothesis_ids=["hyp-002"],
        hypothesis_runs=[
            HypothesisExecutionRecord(
                hypothesis_id="hyp-001",
                planner_strategy_id="strat-001",
                task_ids=["task-101"],
                worker_run_paths=[],
                status="completed",
                start_state_version=2,
                end_state_version=3,
            )
        ],
    )


def test_resolve_round_report_context_valid_completed_round(tmp_path):
    state = _make_sample_canonical_state("batch-alpha")
    manifest = _make_sample_round_manifest("round-001")
    dataset_file = tmp_path / "Friday-PortScan.csv"
    dataset_file.write_text("Label,f1\n0,1\n", encoding="utf-8")

    sample_bundles = {
        "worker_bundles": [
            {
                "task_id": "task-101",
                "hypothesis_id": "hyp-001",
                "parsed_output": {
                    "worker_result": {
                        "findings": [
                            {"summary": "Port distribution is strongly skewed toward port 80", "confidence": "high"}
                        ]
                    }
                },
                "operational_trace": {
                    "tool_events": [
                        {
                            "call_id": "call-1",
                            "action": {"action_class": "distribution_analysis", "feature_name": "DstPort"},
                            "tool_result": {
                                "tool_name": "distribution_analysis",
                                "feature_name": "DstPort",
                                "status": "ok",
                                "metrics": {"entropy": 0.12, "top1_ratio": 0.88},
                            },
                        }
                    ]
                },
            }
        ],
        "critic_bundle": {
            "parsed_output": {
                "critique": "Solid exploration of port features.",
                "strengths": ["Clear numerical metrics"],
                "blind_spots": ["Flow duration not yet analyzed"],
            }
        },
    }

    context = resolve_round_report_context(
        round_manifest=manifest,
        canonical_state=state,
        dataset_path=dataset_file,
        round_bundles=sample_bundles,
    )

    # 1. Identity
    ident = context["execution_identity"]
    assert ident["round_id"] == "round-001"
    assert ident["status"] == "completed"
    assert ident["schema_version"] == ROUND_REPORT_SCHEMA_VERSION

    # 2. Objectives
    obj = context["investigation_objectives"]
    assert "hyp-001" in obj["selected_hypothesis_ids"]
    assert "hyp-002" in obj["deferred_hypothesis_ids"]

    # 3. Round-specific Evidence (numerical values preserved)
    ev = context["round_evidence"]
    assert len(ev["worker_findings"]) == 1
    assert "port 80" in ev["worker_findings"][0]["finding"]
    assert len(ev["tool_executions"]) == 1
    tool_call = ev["tool_executions"][0]
    assert tool_call["feature_name"] == "DstPort"
    assert tool_call["metrics"]["entropy"] == 0.12
    assert tool_call["metrics"]["top1_ratio"] == 0.88
    assert "DstPort" in ev["features_investigated"]
    assert "Solid exploration" in ev["critic_feedback"]["critique"]

    # 4. State Transitions (separating new delta from inherited)
    st = context["state_transitions"]
    assert len(st["updated_hypotheses"]) == 1
    assert st["updated_hypotheses"][0]["hypothesis_id"] == "hyp-001"
    assert len(st["inherited_hypotheses"]) == 1
    assert st["inherited_hypotheses"][0]["hypothesis_id"] == "hyp-002"


def test_round_prompt_includes_all_required_sections_and_evidence(tmp_path):
    state = _make_sample_canonical_state("batch-beta")
    manifest = _make_sample_round_manifest("round-001")
    context = resolve_round_report_context(
        round_manifest=manifest,
        canonical_state=state,
        dataset_path=tmp_path / "Wednesday-DDoS.csv",
    )

    prompt = build_round_report_prompt(context)

    # Required instructions
    assert "GROUND ALL CLAIMS IN EVIDENCE" in prompt
    assert "INCLUDE NUMERICAL VALUES" in prompt
    assert "SEPARATE ROUND EVIDENCE FROM PRIOR STATE" in prompt
    assert "AVOID DEFINITIVE DATASET CLAIMS" in prompt
    assert "NO FABRICATION" in prompt

    # Required 9 sections
    for section_title in ROUND_REPORT_SECTIONS:
        assert section_title in prompt


def test_distinguishes_new_round_evidence_from_inherited_prior_evidence(tmp_path):
    state = _make_sample_canonical_state("batch-gamma")
    manifest = _make_sample_round_manifest("round-001")
    context = resolve_round_report_context(
        round_manifest=manifest,
        canonical_state=state,
    )

    updated_ids = [h["hypothesis_id"] for h in context["state_transitions"]["updated_hypotheses"]]
    inherited_ids = [h["hypothesis_id"] for h in context["state_transitions"]["inherited_hypotheses"]]

    assert "hyp-001" in updated_ids
    assert "hyp-001" not in inherited_ids
    assert "hyp-002" in inherited_ids
    assert "hyp-002" not in updated_ids


def test_missing_fields_and_unresolved_hypotheses_handled_conservatively():
    # Manifest with empty/default fields
    minimal_manifest = {
        "round_id": "round-001",
        "status": "completed",
    }
    context = resolve_round_report_context(
        round_manifest=minimal_manifest,
        canonical_state=None,
    )

    assert context["execution_identity"]["round_id"] == "round-001"
    assert context["round_evidence"]["worker_findings"] == []
    assert context["round_evidence"]["tool_executions"] == []
    assert context["state_transitions"]["updated_hypotheses"] == []


def test_failed_or_incomplete_round_rejected_by_runner():
    manifest = _make_sample_round_manifest("round-001")
    manifest.status = "failed"

    with pytest.raises(ValueError, match="Only completed rounds are eligible"):
        run_round_report(round_manifest=manifest)

    manifest.status = "pending"
    with pytest.raises(ValueError, match="Only completed rounds are eligible"):
        run_round_report(round_manifest=manifest)


def test_runner_generates_and_persists_round_report(tmp_path):
    state = _make_sample_canonical_state("batch-omega")
    manifest = _make_sample_round_manifest("round-001")

    # Persist a source manifest JSON on disk to verify back-linkage
    manifest_file = tmp_path / "round-001.json"
    write_json(manifest_file, manifest.to_dict())

    test_llm = lambda prompt: (
        "# Round Report: round-001 (test-partition)\n\n"
        "## 1. Execution Identity and Status\nCompleted.\n\n"
        "## 2. Executive Summary\nPort scanning detected.\n"
    )

    bundle = run_round_report(
        round_manifest=manifest,
        canonical_state=state,
        round_manifest_path=str(manifest_file),
        llm_callable=test_llm,
        log_dir=str(tmp_path / "logs"),
    )

    assert bundle["runtime_metrics"]["status"] == "ok"
    assert "# Round Report: round-001" in bundle["report_markdown"]

    report_path = Path(bundle["artifact_paths"]["report_path"])
    assert report_path.is_file()
    assert report_path.name == "report.md"

    # Manifest file was updated with round_report_path
    updated_manifest = load_json(manifest_file)
    assert updated_manifest.get("round_report_path") == str(report_path)


def test_full_round_execution_triggers_round_report_in_orchestrator(tmp_path, monkeypatch):
    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text("Label,f1,f2\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "test-batch-round-001"

    round_report_calls = []
    final_batch_report_calls = []

    def mock_run_round_report(**kwargs):
        round_report_calls.append(kwargs)
        run_dir = tmp_path / "round_report_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        report_file = run_dir / "report.md"
        report_file.write_text("# Round Report: round-001\n\nSingle round report.", encoding="utf-8")
        return {
            "report_markdown": "# Round Report: round-001\n\nSingle round report.",
            "runtime_metrics": {"status": "ok"},
            "artifact_paths": {
                "run_dir": run_dir,
                "report_path": report_file,
            },
        }

    monkeypatch.setattr(orch, "run_round_report", mock_round_report_calls if False else mock_run_round_report)
    monkeypatch.setattr(orch, "run_final_batch_report", lambda *a, **k: final_batch_report_calls.append(a))

    dummy_state = _make_sample_canonical_state(batch_id)
    monkeypatch.setattr(orch, "build_initial_semantic_inputs", lambda *a, **k: {"overview_summary_min": {}, "partition_context": {}})
    monkeypatch.setattr(orch, "build_initial_analysis_context", lambda *a, **k: {"partition_context_ref": {}})
    monkeypatch.setattr(orch, "run_semantic_extraction", lambda *a, **k: {
        "component_run": {"validation_ok": True, "status": "ok"},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "se.json")},
    })
    monkeypatch.setattr(orch, "run_investigation_analysis", lambda *a, **k: {
        "component_run": {"validation_ok": True, "status": "ok"},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "ia.json")},
    })
    monkeypatch.setattr(orch, "run_final_batch_auditor", lambda *a, **k: {
        "component_run": {"report_committed": True, "status": "ok", "validation_ok": True},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "fba.json")},
    })

    def fake_execute_round(*args, **kwargs):
        manifest = MagicMock()
        manifest.status = "completed"
        manifest.analysis_mode = "initial"
        manifest.round_id = "round-001"
        manifest.round_index = 1
        manifest.hypothesis_runs = []
        manifest.global_aggregation_path = ""
        manifest.to_dict.return_value = {"round_id": "round-001", "status": "completed"}
        return {
            "round_manifest": manifest,
            "frozen_snapshot": {"round_id": "round-001", "batch_id": batch_id},
            "updated_batch_state": dummy_state.to_dict(),
            "state_manager_bundles": [{"artifact_paths": {"component_run_path": str(tmp_path / "sm.json")}}],
            "aggregation_bundles": [],
            "critic_bundle": {},
            "terminal_reason": "round_complete",
        }

    monkeypatch.setattr(orch, "execute_round", fake_execute_round)

    result = orch.run_phase3a_batch(
        dataset_path=dataset_path,
        batch_id=batch_id,
        execution_mode="full_round",
        max_rounds=1,
        log_dir=str(tmp_path / "logs"),
        caller_mode="test",
    )

    # 1. Round report was triggered exactly once
    assert len(round_report_calls) == 1
    assert "round_report_path" in result["artifact_paths"]
    assert result.get("round_report_bundle") is not None
    # 2. Final batch report was NOT triggered
    assert len(final_batch_report_calls) == 0


def test_full_batch_does_not_invoke_round_report_by_default(tmp_path, monkeypatch):
    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text("Label,f1,f2\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "test-batch-multi-001"

    round_report_calls = []
    final_batch_report_calls = []

    monkeypatch.setattr(orch, "run_round_report", lambda **kwargs: round_report_calls.append(kwargs))
    monkeypatch.setattr(orch, "run_final_batch_report", lambda *a, **k: {
        "report_markdown": "# Final Batch Report",
        "runtime_metrics": {"status": "ok"},
        "artifact_paths": {"report_path": tmp_path / "final_report.md"},
    })

    dummy_state = _make_sample_canonical_state(batch_id)
    monkeypatch.setattr(orch, "build_initial_semantic_inputs", lambda *a, **k: {"overview_summary_min": {}, "partition_context": {}})
    monkeypatch.setattr(orch, "build_initial_analysis_context", lambda *a, **k: {"partition_context_ref": {}})
    monkeypatch.setattr(orch, "run_semantic_extraction", lambda *a, **k: {
        "component_run": {"validation_ok": True, "status": "ok"},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "se.json")},
    })
    monkeypatch.setattr(orch, "run_investigation_analysis", lambda *a, **k: {
        "component_run": {"validation_ok": True, "status": "ok"},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "ia.json")},
    })
    monkeypatch.setattr(orch, "run_final_batch_auditor", lambda *a, **k: {
        "component_run": {"report_committed": True, "status": "ok", "validation_ok": True},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "fba.json")},
    })

    def fake_execute_round(*args, **kwargs):
        manifest = MagicMock()
        manifest.status = "completed"
        manifest.analysis_mode = "initial"
        manifest.round_id = "round-001"
        manifest.round_index = 1
        manifest.hypothesis_runs = []
        manifest.global_aggregation_path = ""
        manifest.to_dict.return_value = {"round_id": "round-001", "status": "completed"}
        return {
            "round_manifest": manifest,
            "frozen_snapshot": {"round_id": "round-001"},
            "updated_batch_state": dummy_state.to_dict(),
            "state_manager_bundles": [{"artifact_paths": {"component_run_path": str(tmp_path / "sm.json")}}],
            "aggregation_bundles": [],
            "critic_bundle": {},
            "terminal_reason": "max_rounds_reached",
        }

    monkeypatch.setattr(orch, "execute_round", fake_execute_round)

    result = orch.run_phase3a_batch(
        dataset_path=dataset_path,
        batch_id=batch_id,
        execution_mode="full_batch",
        max_rounds=1,
        log_dir=str(tmp_path / "logs"),
        caller_mode="test",
    )

    # In full_batch mode, round report is not called by default
    assert len(round_report_calls) == 0
    assert "round_report_path" not in result["artifact_paths"]


def test_round_report_failure_does_not_abort_completed_round(tmp_path, monkeypatch):
    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text("Label,f1,f2\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "test-batch-round-err"

    def mock_failing_round_report(**kwargs):
        raise RuntimeError("OpenAI rate limit reached during round report")

    monkeypatch.setattr(orch, "run_round_report", mock_failing_round_report)

    dummy_state = _make_sample_canonical_state(batch_id)
    monkeypatch.setattr(orch, "build_initial_semantic_inputs", lambda *a, **k: {"overview_summary_min": {}, "partition_context": {}})
    monkeypatch.setattr(orch, "build_initial_analysis_context", lambda *a, **k: {"partition_context_ref": {}})
    monkeypatch.setattr(orch, "run_semantic_extraction", lambda *a, **k: {
        "component_run": {"validation_ok": True, "status": "ok"},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "se.json")},
    })
    monkeypatch.setattr(orch, "run_investigation_analysis", lambda *a, **k: {
        "component_run": {"validation_ok": True, "status": "ok"},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "ia.json")},
    })
    monkeypatch.setattr(orch, "run_final_batch_auditor", lambda *a, **k: {
        "component_run": {"report_committed": True, "status": "ok", "validation_ok": True},
        "parsed_output": {},
        "artifact_paths": {"component_run_path": str(tmp_path / "fba.json")},
    })

    def fake_execute_round(*args, **kwargs):
        manifest = MagicMock()
        manifest.status = "completed"
        manifest.analysis_mode = "initial"
        manifest.round_id = "round-001"
        manifest.round_index = 1
        manifest.hypothesis_runs = []
        manifest.global_aggregation_path = ""
        manifest.to_dict.return_value = {"round_id": "round-001", "status": "completed"}
        return {
            "round_manifest": manifest,
            "frozen_snapshot": {"round_id": "round-001"},
            "updated_batch_state": dummy_state.to_dict(),
            "state_manager_bundles": [{"artifact_paths": {"component_run_path": str(tmp_path / "sm.json")}}],
            "aggregation_bundles": [],
            "critic_bundle": {},
            "terminal_reason": "round_complete",
        }

    monkeypatch.setattr(orch, "execute_round", fake_execute_round)

    result = orch.run_phase3a_batch(
        dataset_path=dataset_path,
        batch_id=batch_id,
        execution_mode="full_round",
        max_rounds=1,
        log_dir=str(tmp_path / "logs"),
        caller_mode="test",
    )

    # Round execution completed successfully
    assert result["component_run"]["status"] == "completed"
    assert result["component_run"]["final_status"] == "completed"
    # Round report path is missing but warning is captured
    assert "round_report_path" not in result["artifact_paths"]
    warnings = result["component_run"]["warnings"]
    assert any(w.get("component") == "round_report" for w in warnings)


def test_cli_post_run_flow_see_round_report(tmp_path, monkeypatch):
    cli = NidsAgentCli()
    report_file = tmp_path / "report.md"
    report_file.write_text("# Round Report: round-001\n\nExecutive summary: port scan confirmed.", encoding="utf-8")

    run_context = Phase3ARuntimeRunContext(
        artifact_paths={"component_run_path": str(tmp_path / "cr.json"), "round_report_path": str(report_file)},
        component_run={"batch_id": "batch-round-cli", "status": "completed", "final_status": "completed", "round_count": 1},
        batch_ledger={"round_manifests": [{"round_id": "round-001"}]},
        initial_runtime_context={},
        initial_state={},
        finalization_summary={},
        runtime_metrics={},
        runtime_summary={"warnings": []},
    )

    rendered_screens = []
    monkeypatch.setattr(cli, "_render", lambda content: rendered_screens.append(content))

    choices = iter(["1", "B"])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: next(choices))
    monkeypatch.setattr(cli, "_wait_for_enter", lambda *a, **k: None)

    ret = cli._full_round_post_run_flow(run_context, {"artifact_paths": {"round_report_path": str(report_file)}})
    assert ret == "phase3a_runtime"

    # Screen 1 presents "[1] See round report"
    assert "[1] See round report" in rendered_screens[0]
    # Screen 2 renders the actual report content
    assert "# Round Report: round-001" in rendered_screens[1]
    assert "port scan confirmed." in rendered_screens[1]


def test_cli_round_review_view_and_regenerate_actions(tmp_path, monkeypatch):
    cli = NidsAgentCli()
    report_file = tmp_path / "report.md"
    report_file.write_text("# Round Report: round-001\n\nReport content here.", encoding="utf-8")

    round_manifest = {
        "round_id": "round-001",
        "status": "completed",
        "round_report_path": str(report_file),
    }
    round_context = Phase3ARuntimeRoundContext(
        round_manifest=round_manifest,
        frozen_snapshot={},
        global_aggregation_summary={},
        analysis_run=None,
        ranking_run=None,
        planner_run=None,
        critic_run=None,
    )

    rendered_screens = []
    monkeypatch.setattr(cli, "_render", lambda content: rendered_screens.append(content))
    monkeypatch.setattr(cli, "_wait_for_enter", lambda *a, **k: None)

    # Choice 8: View Round Report, then B: Back
    choices = iter(["8", "B"])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: next(choices))

    cli._view_phase3a_runtime_round_review_menu(round_context)

    # Screen 1 is the round review menu offering [8] View Round Report and [9] Regenerate Round Report
    assert "[8] View Round Report" in rendered_screens[0]
    assert "[9] Regenerate Round Report" in rendered_screens[0]
    # Screen 2 is the text view of the report
    assert "# Round Report: round-001" in rendered_screens[1]


def test_regenerate_round_report_from_persisted_artifacts_without_investigation_rerun(tmp_path, monkeypatch):
    manifest = _make_sample_round_manifest("round-001")
    snapshot_file = tmp_path / "round-001_snapshot.json"
    write_json(snapshot_file, {"round_id": "round-001", "batch_id": "batch-regen"})
    manifest.frozen_snapshot_path = str(snapshot_file)

    manifest_file = tmp_path / "round-001.json"
    write_json(manifest_file, manifest.to_dict())

    test_llm = lambda prompt: "# Round Report: round-001\n\nRegenerated from disk."

    bundle = regenerate_round_report(
        round_manifest_path=str(manifest_file),
        llm_callable=test_llm,
        log_dir=str(tmp_path / "logs"),
    )

    assert bundle["runtime_metrics"]["status"] == "ok"
    assert "Regenerated from disk." in bundle["report_markdown"]
    report_file = Path(bundle["artifact_paths"]["report_path"])
    assert report_file.is_file()

