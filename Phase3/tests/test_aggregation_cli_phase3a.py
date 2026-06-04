import json
from pathlib import Path

from aggregation.runner import run_aggregation
from interface.cli import AggregationRunContext, NidsAgentCli


def _build_worker_result_set() -> dict[str, object]:
    return {
        "batch_id": "batch-001",
        "round_id": "round-001",
        "hypothesis_id": "hyp-1",
        "worker_results": [
            {
                "task_id": "task-hyp-1-1",
                "hypothesis_id": "hyp-1",
                "status": "completed",
                "findings": ["The broad dependency pair remained strong in the local slice."],
                "evidence_refs": ["task-hyp-1-1_step_01"],
                "contradictions": ["The broad dependency signal still conflicts with the narrower local port signal."],
                "limitations": [],
            },
            {
                "task_id": "task-hyp-1-2",
                "hypothesis_id": "hyp-1",
                "status": "completed",
                "findings": ["The localized port shortcut stayed narrow and incomplete."],
                "evidence_refs": ["task-hyp-1-2_step_01"],
                "contradictions": [],
                "limitations": ["The local port evidence remains too narrow to resolve the wider mechanism."],
            },
        ],
    }


def _build_saved_aggregation_bundle(tmp_path: Path) -> dict[str, object]:
    responses = iter(
        [
            json.dumps(
                {
                    "aggregation_handoff": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "hypothesis_id": "hyp-1",
                        "merged_findings": [
                            "The wider dependency signal remains stronger than the narrow port-local shortcut."
                        ],
                        "evidence_refs": ["task-hyp-1-1_step_01", "task-hyp-1-2_step_01"],
                        "preserved_contradictions": [
                            "The broad dependency signal still conflicts with the narrower local port signal."
                        ],
                        "open_gaps": [
                            "The local port evidence remains too narrow to resolve the wider mechanism."
                        ],
                        "update_focus": "Dependency strength versus localized port evidence.",
                    }
                }
            )
        ]
    )
    return run_aggregation(
        _build_worker_result_set(),
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "aggregation"),
    )


def test_phase3a_components_menu_routes_aggregation():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "7"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "aggregation"
    assert "Aggregation  <available>" in cli._last_rendered


def test_load_aggregation_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = _build_saved_aggregation_bundle(tmp_path)

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_aggregation_run_context(Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, AggregationRunContext)
    assert loaded.component_run["round_id"] == "round-001"
    assert loaded.aggregation_handoff["hypothesis_id"] == "hyp-1"
    assert len(loaded.worker_result_set["worker_results"]) == 2


def test_render_aggregation_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = AggregationRunContext(
        artifact_paths={
            "component_run_path": "aggregation_run_001/component_run.json",
            "worker_result_set_path": "aggregation_run_001/worker_result_set.json",
            "aggregation_handoff_path": "aggregation_run_001/aggregation_handoff.json",
            "validation_report_path": "aggregation_run_001/validation_report.json",
            "runtime_metrics_path": "aggregation_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "round_id": "round-001",
            "hypothesis_id": "hyp-1",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
            "handoff_committed": True,
        },
        worker_result_set={"worker_results": [{"task_id": "task-hyp-1-1"}]},
        normalized_inputs={},
        overlap_diagnostics=[],
        prompt_text="prompt",
        raw_response_text="response",
        parsed_output={},
        aggregation_handoff={"update_focus": "Dependency strength versus localized port evidence."},
        repair_attempts=[],
        validation_report={},
        runtime_metrics={"duration_ms": 10.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_aggregation_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "hyp-1" in cli._last_rendered
    assert "worker_result_set.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered
    assert "repair_attempts" in cli._last_rendered