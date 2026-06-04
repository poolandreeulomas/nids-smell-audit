import json
from pathlib import Path

from planner.context_resolver import build_planner_round_context, build_selected_hypothesis_context
from planner.runner import run_planner
from interface.cli import NidsAgentCli, PlannerRunContext


def _build_ranking_decision_min() -> dict[str, object]:
    return {
        "batch_id": "batch-001",
        "round_id": "round-001",
        "selected_hypothesis_ids": ["hyp-1", "hyp-3"],
    }


def _build_selected_hypothesis_context() -> dict[str, object]:
    return build_selected_hypothesis_context(
        selected_hypotheses=[
            {
                "hypothesis_id": "hyp-1",
                "summary": "The broad dependency region may reflect a batch-wide regularity that still leaves room for a narrow local interpretation.",
                "evidence_refs": ["e1", "e2", "e3"],
                "open_questions": [
                    "Does the localized dst_port signal survive when the broad dependency-linked flow-size structure is pressured?"
                ],
                "current_status": "selected_for_round",
            },
            {
                "hypothesis_id": "hyp-3",
                "summary": "The contradiction between duplication-sensitive and local-separability evidence could reorganize the current interpretive space if clarified.",
                "evidence_refs": ["e3", "e4"],
                "open_questions": [
                    "Does contradiction-preserving evidence remain after broader locality pressure is considered?"
                ],
                "current_status": "selected_for_round",
            },
        ]
    )


def _build_planner_round_context() -> dict[str, object]:
    return build_planner_round_context(
        round_id="round-001",
        related_substrate_refs=["e1", "e2", "e3", "e4"],
        tool_capability_refs=["feature_summary", "feature_relation", "shortcut_analysis"],
        round_constraints=["strategic_only", "no_exact_tool_calls", "preserve_selected_scope"],
    )


def _build_valid_response_payload() -> dict[str, object]:
    return {
        "batch_id": "batch-001",
        "round_id": "round-001",
        "planner_strategies": [
            {
                "strategy_id": "strategy-hyp-1",
                "hypothesis_id": "hyp-1",
                "strategic_objective": "Clarify whether the broad dependency interpretation remains useful once narrower local alternatives are pressured directly.",
                "key_checks": [
                    "Pressure the broad dependency interpretation against the narrower local alternative.",
                    "Check whether the broad region remains informative beyond one local slice.",
                ],
                "success_criteria": [
                    "Obtain evidence that clearly strengthens or weakens the broad dependency interpretation relative to the local alternative.",
                    "Reduce uncertainty about whether the broad region remains meaningful outside the localized signal.",
                ],
                "router_constraints": [
                    "Preserve the distinction between broad and local evidence scopes.",
                    "Keep follow-up work bounded to verification-oriented probes rather than exhaustive coverage.",
                ],
            },
            {
                "strategy_id": "strategy-hyp-3",
                "hypothesis_id": "hyp-3",
                "strategic_objective": "Clarify whether the contradiction reflects a stable conflict between representations or only a narrower local ambiguity.",
                "key_checks": [
                    "Pressure the contradiction from both broad-scope and narrow-scope perspectives.",
                    "Check whether weakening evidence is more informative than additional supporting evidence.",
                ],
                "success_criteria": [
                    "Obtain evidence that narrows the contradiction without collapsing uncertainty prematurely.",
                    "Differentiate whether the contradiction survives broader context or remains local only.",
                ],
                "router_constraints": [
                    "Keep contradiction-preserving evidence explicit during follow-up work.",
                    "Avoid collapsing broad and local interpretations into one undifferentiated check.",
                ],
            },
        ],
    }


def test_phase3a_components_menu_routes_planner():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "4"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "planner"
    assert "Planner  <available>" in cli._last_rendered


def test_load_planner_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = run_planner(
        _build_ranking_decision_min(),
        _build_selected_hypothesis_context(),
        _build_planner_round_context(),
        llm_callable=lambda prompt_text: json.dumps(_build_valid_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_planner_run_context(Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, PlannerRunContext)
    assert loaded.component_run["round_id"] == "round-001"
    assert loaded.parsed_output["planner_strategies"][0]["hypothesis_id"] == "hyp-1"
    assert loaded.strategy_index["strategy_count"] == 2


def test_render_planner_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = PlannerRunContext(
        artifact_paths={
            "component_run_path": "planner_run_001/component_run.json",
            "ranking_decision_min_path": "planner_run_001/ranking_decision_min.json",
            "parsed_output_path": "planner_run_001/parsed_output.json",
            "validation_report_path": "planner_run_001/validation_report.json",
            "runtime_metrics_path": "planner_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "round_id": "round-001",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
        },
        ranking_decision_min={
            "selected_hypothesis_ids": ["hyp-1", "hyp-3"],
        },
        selected_hypothesis_context={},
        planner_round_context={},
        projected_selected_context={},
        projected_planner_round_context={},
        prompt_text="prompt",
        raw_response_text="response",
        parsed_output={
            "planner_strategies": [
                {"strategy_id": "strategy-hyp-1"},
                {"strategy_id": "strategy-hyp-3"},
            ]
        },
        strategy_index={"strategy_count": 2},
        validation_report={},
        runtime_metrics={"duration_ms": 15.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_planner_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "round-001" in cli._last_rendered
    assert "parsed_output.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered