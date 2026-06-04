import json
from pathlib import Path

from hypothesis_ranking.context_resolver import build_ranking_state_min
from hypothesis_ranking.runner import run_hypothesis_ranking
from interface.cli import HypothesisRankingRunContext, NidsAgentCli


def _build_investigation_hypothesis_set() -> dict[str, object]:
    return {
        "analysis_id": "analysis-batch-001",
        "batch_id": "batch-001",
        "hypotheses": [
            {
                "hypothesis_id": "hyp-1",
                "summary": "The broad dependency region may reflect a batch-wide regularity that still leaves room for a narrow local interpretation.",
                "evidence_refs": ["e1", "e2", "e3"],
                "open_questions": [
                    "Does the localized dst_port signal survive when the broad dependency-linked flow-size structure is controlled?"
                ],
            },
            {
                "hypothesis_id": "hyp-2",
                "summary": "The dst_port signal may remain a distinct representation-sensitive framing with unresolved local scope.",
                "evidence_refs": ["e3", "e4"],
                "open_questions": [
                    "Would nearby representation-sensitive slices preserve this local signal or dissolve it?"
                ],
            },
            {
                "hypothesis_id": "hyp-3",
                "summary": "The contradiction between duplication-sensitive and local-separability evidence could reorganize the current interpretive space if clarified.",
                "evidence_refs": ["e3", "e4"],
                "open_questions": [
                    "Does contradiction-preserving evidence remain after broader locality pressure is considered?"
                ],
            },
        ],
    }


def _build_ranking_state() -> dict[str, object]:
    return build_ranking_state_min(
        round_id="round-001",
        selection_budget=3,
        hypothesis_state_refs=[
            {"hypothesis_id": "hyp-1", "state_notes": []},
            {"hypothesis_id": "hyp-2", "state_notes": []},
            {"hypothesis_id": "hyp-3", "state_notes": []},
        ],
        round_constraints=["selection_budget=3", "allocation_only", "preserve_deferred_hypotheses"],
    )


def _build_valid_response_payload() -> dict[str, object]:
    return {
        "batch_id": "batch-001",
        "round_id": "round-001",
        "selected_hypothesis_ids": ["hyp-1", "hyp-3"],
        "deferred_hypothesis_ids": ["hyp-2"],
        "selection_rationales": [
            {
                "hypothesis_id": "hyp-1",
                "reason": "Broad-plus-local tension could clarify a large part of the batch quickly.",
            },
            {
                "hypothesis_id": "hyp-3",
                "reason": "The contradiction could materially reshape which interpretation deserves later effort.",
            },
        ],
    }


def test_phase3a_components_menu_routes_hypothesis_ranking():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "3"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "hypothesis_ranking"
    assert "Hypothesis Ranking  <available>" in cli._last_rendered


def test_load_hypothesis_ranking_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = run_hypothesis_ranking(
        _build_investigation_hypothesis_set(),
        _build_ranking_state(),
        llm_callable=lambda prompt_text: json.dumps(_build_valid_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_hypothesis_ranking_run_context(
        Path(bundle["artifact_paths"]["component_run_path"]).parent
    )

    assert isinstance(loaded, HypothesisRankingRunContext)
    assert loaded.component_run["round_id"] == "round-001"
    assert loaded.parsed_output["selected_hypothesis_ids"] == ["hyp-1", "hyp-3"]
    assert loaded.selection_index["selected_count"] == 2


def test_render_hypothesis_ranking_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = HypothesisRankingRunContext(
        artifact_paths={
            "component_run_path": "hypothesis_ranking_run_001/component_run.json",
            "candidate_hypotheses_path": "hypothesis_ranking_run_001/candidate_hypotheses.json",
            "parsed_output_path": "hypothesis_ranking_run_001/parsed_output.json",
            "validation_report_path": "hypothesis_ranking_run_001/validation_report.json",
            "runtime_metrics_path": "hypothesis_ranking_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "analysis_id": "analysis-batch-001",
            "round_id": "round-001",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
        },
        candidate_hypotheses={},
        ranking_state_snapshot={},
        projected_candidate_context={},
        projected_ranking_state={},
        prompt_text="prompt",
        raw_response_text="response",
        parsed_output={
            "selected_hypothesis_ids": ["hyp-1", "hyp-3"],
            "deferred_hypothesis_ids": ["hyp-2"],
        },
        selection_index={"selected_count": 2, "deferred_count": 1},
        validation_report={},
        runtime_metrics={"duration_ms": 15.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_hypothesis_ranking_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "analysis-batch-001" in cli._last_rendered
    assert "round-001" in cli._last_rendered
    assert "parsed_output.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered