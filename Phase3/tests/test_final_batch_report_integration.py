from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from phase3_runtime.contracts import SCHEMA_VERSION
from phase3_runtime.ledger import BatchLedger, FinalizationRecord
from state.schema import CanonicalBatchState, InterpretiveHypothesis


def _make_dummy_canonical_state(batch_id="test_batch"):
    return CanonicalBatchState(
        batch_id=batch_id,
        state_version=2,
        structural_substrate={"compressed_regions": []},
        interpretive_hypotheses=[
            InterpretiveHypothesis(
                hypothesis_id="hyp-1",
                summary="Suspect feature redundancy across flows.",
                status="active",
                evidence_refs=["ev-1"],
                merged_findings=["Feature f1 redundant with f2"],
                revision_count=1,
            )
        ],
        revision_log=[],
    )


def test_full_batch_invokes_final_batch_report_after_state_commit(tmp_path, monkeypatch):
    import phase3_runtime.orchestrator as orch

    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text("Label,f1,f2\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "test-batch-001"

    report_calls = []

    def mock_run_final_batch_report(final_state, partition_name, **kwargs):
        report_calls.append({
            "final_state": final_state,
            "partition_name": partition_name,
            "kwargs": kwargs,
        })
        run_dir = tmp_path / "final_report_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        report_file = run_dir / "report.md"
        report_file.write_text("# Final Audit Report\n\nAll findings confirmed.", encoding="utf-8")
        return {
            "report_markdown": "# Final Audit Report\n\nAll findings confirmed.",
            "runtime_metrics": {"status": "ok"},
            "artifact_paths": {
                "run_dir": run_dir,
                "report_path": report_file,
            },
        }

    monkeypatch.setattr(orch, "run_final_batch_report", mock_run_final_batch_report)

    # Mock the early phases
    dummy_state = _make_dummy_canonical_state(batch_id)

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

    # 1. Final report was invoked exactly once
    assert len(report_calls) == 1
    assert report_calls[0]["partition_name"] == dataset_path.name
    assert isinstance(report_calls[0]["final_state"], CanonicalBatchState)

    # 2. Output path recorded in artifact paths
    assert "final_report_path" in result["artifact_paths"]
    report_path = Path(result["artifact_paths"]["final_report_path"])
    assert report_path.is_file()
    assert "# Final Audit Report" in report_path.read_text(encoding="utf-8")
    assert result.get("final_batch_report_bundle") is not None


def test_partial_runtime_mode_does_not_invoke_final_batch_report(tmp_path, monkeypatch):
    import phase3_runtime.orchestrator as orch

    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text("Label,f1,f2\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "test-batch-002"

    report_calls = []
    monkeypatch.setattr(orch, "run_final_batch_report", lambda *a, **k: report_calls.append(a))

    dummy_state = _make_dummy_canonical_state(batch_id)
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

    result = orch.run_phase3a_batch(
        dataset_path=dataset_path,
        batch_id=batch_id,
        execution_mode="cognitive_only",
        log_dir=str(tmp_path / "logs"),
        caller_mode="test",
    )

    # Report should NOT be generated for partial cognitive run
    assert len(report_calls) == 0
    assert "final_report_path" not in result["artifact_paths"]


def test_report_generation_failure_preserves_batch_artifacts(tmp_path, monkeypatch):
    import phase3_runtime.orchestrator as orch

    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text("Label,f1,f2\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "test-batch-003"

    def failing_report(*a, **k):
        raise RuntimeError("LLM synthesis timeout")

    monkeypatch.setattr(orch, "run_final_batch_report", failing_report)

    dummy_state = _make_dummy_canonical_state(batch_id)
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

    # Batch itself completed successfully
    assert result["component_run"]["status"] == "completed"
    assert result["component_run"]["final_status"] == "completed"
    # Batch artifacts are preserved on disk
    run_manifest_path = Path(result["artifact_paths"]["run_manifest_path"])
    assert run_manifest_path.is_file()
    # Report path not present because generation failed
    assert "final_report_path" not in result["artifact_paths"]
    # Warning was captured
    warnings = result["component_run"]["warnings"]
    assert any(w.get("component") == "final_batch_report" and "LLM synthesis timeout" in w.get("error", "") for w in warnings)


def test_cli_post_run_flow_see_full_report(tmp_path, monkeypatch):
    from interface.cli import NidsAgentCli, Phase3ARuntimeRunContext

    cli = NidsAgentCli()

    report_file = tmp_path / "report.md"
    report_file.write_text("# My Automated Final Report\n\nExecutive finding: leak detected.", encoding="utf-8")

    run_context = Phase3ARuntimeRunContext(
        artifact_paths={"component_run_path": str(tmp_path / "cr.json"), "final_report_path": str(report_file)},
        component_run={"batch_id": "batch-1", "status": "completed", "final_status": "completed", "round_count": 3},
        batch_ledger={},
        initial_runtime_context={},
        initial_state={},
        finalization_summary={},
        runtime_metrics={},
        runtime_summary={"warnings": []},
    )

    rendered_screens = []
    def fake_render(content):
        rendered_screens.append(content)

    monkeypatch.setattr(cli, "_render", fake_render)

    # Simulate user choosing "1" (See full report), pressing Enter, then choosing "B" (Back)
    choices = iter(["1", "B"])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: next(choices))
    monkeypatch.setattr(cli, "_wait_for_enter", lambda *a, **k: None)

    ret = cli._full_batch_post_run_flow(run_context, {"artifact_paths": {"final_report_path": str(report_file)}})
    assert ret == "phase3a_runtime"

    # First screen rendered should contain "See full report"
    assert "See full report" in rendered_screens[0]
    # And "[1] See full report" is presented
    assert "[1] See full report" in rendered_screens[0]

    # Second screen rendered was the text view of the actual report content
    assert "# My Automated Final Report" in rendered_screens[1]
    assert "Executive finding: leak detected." in rendered_screens[1]


def test_cli_post_run_flow_when_report_missing_or_failed(tmp_path, monkeypatch):
    from interface.cli import NidsAgentCli, Phase3ARuntimeRunContext

    cli = NidsAgentCli()

    run_context = Phase3ARuntimeRunContext(
        artifact_paths={"component_run_path": str(tmp_path / "cr.json")},
        component_run={"batch_id": "batch-1", "status": "completed", "final_status": "completed", "round_count": 3},
        batch_ledger={},
        initial_runtime_context={},
        initial_state={},
        finalization_summary={},
        runtime_metrics={},
        runtime_summary={"warnings": [{"component": "final_batch_report", "error": "Disk quota exceeded"}]},
    )

    rendered_screens = []
    monkeypatch.setattr(cli, "_render", lambda c: rendered_screens.append(c))

    choices = iter(["B"])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: next(choices))

    ret = cli._full_batch_post_run_flow(run_context, {})
    assert ret == "phase3a_runtime"

    # Option "1" must NOT be offered when report is missing
    assert "See full report" not in rendered_screens[0]
    assert "Generation failed: Disk quota exceeded" in rendered_screens[0]
    assert "[2] View run summary" in rendered_screens[0]


def test_cli_post_run_flow_view_run_summary_and_return_to_main(tmp_path, monkeypatch):
    from interface.cli import NidsAgentCli, Phase3ARuntimeRunContext

    cli = NidsAgentCli()
    report_file = tmp_path / "report.md"
    report_file.write_text("# Report", encoding="utf-8")

    run_context = Phase3ARuntimeRunContext(
        artifact_paths={"component_run_path": str(tmp_path / "cr.json"), "final_report_path": str(report_file)},
        component_run={"batch_id": "batch-1", "status": "completed", "final_status": "completed", "round_count": 1},
        batch_ledger={},
        initial_runtime_context={},
        initial_state={},
        finalization_summary={},
        runtime_metrics={},
        runtime_summary={"warnings": []},
    )

    rendered_screens = []
    monkeypatch.setattr(cli, "_render", lambda c: rendered_screens.append(c))

    # User presses "2" (View run summary), then "B" (Back from review), then "0" (Return to main menu)
    choices = iter(["2", "B", "0"])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: next(choices))

    ret = cli._full_batch_post_run_flow(run_context, {"artifact_paths": {"final_report_path": str(report_file)}})
    assert ret == "main"


def test_cli_post_run_flow_unreadable_file_handling(tmp_path, monkeypatch):
    from interface.cli import NidsAgentCli, Phase3ARuntimeRunContext

    cli = NidsAgentCli()
    # Report path points to a file that gets deleted before reading
    report_file = tmp_path / "report.md"
    report_file.write_text("# Report", encoding="utf-8")

    run_context = Phase3ARuntimeRunContext(
        artifact_paths={"component_run_path": str(tmp_path / "cr.json"), "final_report_path": str(report_file)},
        component_run={"batch_id": "batch-1", "status": "completed", "final_status": "completed", "round_count": 1},
        batch_ledger={},
        initial_runtime_context={},
        initial_state={},
        finalization_summary={},
        runtime_metrics={},
        runtime_summary={"warnings": []},
    )

    errors_shown = []
    monkeypatch.setattr(cli, "_show_error", lambda msg: errors_shown.append(msg))
    monkeypatch.setattr(cli, "_render", lambda c: None)

    # Delete the report file to simulate missing file on read
    report_file.unlink()

    choices = iter(["1", "B"])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: next(choices))

    ret = cli._full_batch_post_run_flow(run_context, {"artifact_paths": {"final_report_path": str(report_file)}})
    assert ret == "phase3a_runtime"


def test_manual_cli_final_batch_report_flow_still_works(tmp_path, monkeypatch):
    from interface.cli import NidsAgentCli, StateManagerRunContext
    from final_batch_report.contracts import SCHEMA_VERSION

    cli = NidsAgentCli()
    dummy_state = _make_dummy_canonical_state("batch-manual")

    source_run = StateManagerRunContext(
        artifact_paths={"component_run_path": str(tmp_path / "sm.json")},
        component_run={"status": "ok"},
        prior_state={},
        aggregation_handoff={},
        state_manager_context={},
        prompt_text="",
        raw_response_text="",
        state_delta_record={},
        updated_batch_state=dummy_state.to_dict(),
        state_update_result={},
        validation_report={},
        runtime_metrics={},
    )
    monkeypatch.setattr(cli, "_prompt_final_batch_report_source", lambda: source_run)
    monkeypatch.setattr(cli, "_get_selected_dataset_label", lambda: "Friday-Morning")

    report_run_dir = tmp_path / "manual_report_run"
    report_run_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_run_dir / "report.md"
    report_file.write_text("# Manual Final Report", encoding="utf-8")

    def mock_run_final_batch_report(final_state, partition_name, **kwargs):
        assert partition_name == "Friday-Morning"
        assert isinstance(final_state, CanonicalBatchState)
        return {
            "report_markdown": "# Manual Final Report",
            "runtime_metrics": {"status": "ok"},
            "artifact_paths": {
                "run_dir": report_run_dir,
                "report_path": report_file,
            },
        }

    import interface.cli as cli_module
    monkeypatch.setattr(cli_module, "run_final_batch_report", mock_run_final_batch_report)

    # Exit the review loop immediately
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    monkeypatch.setattr(cli, "_render", lambda c: None)

    ret = cli._run_final_batch_report_flow()
    assert ret == "final_batch_report"
    assert cli._last_final_batch_report_run is not None
    assert cli._last_final_batch_report_run.report_markdown == "# Manual Final Report"
