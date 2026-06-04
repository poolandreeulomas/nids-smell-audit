import json
from pathlib import Path

from interface.cli import NidsAgentCli, RouterRunContext
from planner.context_resolver import build_planner_round_context, build_selected_hypothesis_context
from planner.runner import run_planner
from router.context_reducer import build_router_context_min
from router.runner import run_router


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


def _build_planner_response_payload() -> dict[str, object]:
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


def _build_router_context_min() -> dict[str, object]:
    return build_router_context_min(
        related_substrate_refs=["e1", "e2", "e3"],
        tool_capability_refs=["feature_summary", "feature_relation", "shortcut_analysis"],
        execution_budget={"max_worker_steps": 8, "max_tasks": 4, "max_retries": 1},
        guardrails=["bounded_local_scope", "no_exact_tool_calls", "no_hidden_replanning"],
    )


def _build_router_response_payload() -> dict[str, object]:
    return {
        "batch_id": "batch-001",
        "round_id": "round-001",
        "hypothesis_id": "hyp-1",
        "planner_strategy_id": "strategy-hyp-1",
        "worker_tasks": [
            {
                "task_id": "task-hyp-1-1",
                "hypothesis_id": "hyp-1",
                "task_scope": "Probe whether the broad dependency interpretation survives direct local comparison pressure.",
                "allowed_actions": ["relation_verification", "shortcut_verification"],
                "local_context_refs": ["e1", "e3"],
                "stop_conditions": [
                    "Stop when one strengthening or weakening signal clearly changes the broad-versus-local comparison.",
                    "Stop when the worker step budget is exhausted without new contradictory evidence.",
                ],
            }
        ],
    }


def _build_saved_router_bundle(tmp_path: Path) -> dict[str, object]:
    planner_bundle = run_planner(
        _build_ranking_decision_min(),
        _build_selected_hypothesis_context(),
        _build_planner_round_context(),
        llm_callable=lambda prompt_text: json.dumps(_build_planner_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "planner"),
    )
    selected_strategy = planner_bundle["planner_round_output"]["planner_strategies"][0]
    return run_router(
        selected_strategy,
        _build_router_context_min(),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: json.dumps(_build_router_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "router"),
    )


def test_phase3a_components_menu_routes_router():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "5"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "router"
    assert "Router  <available>" in cli._last_rendered


def test_load_router_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = _build_saved_router_bundle(tmp_path)

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_router_run_context(Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, RouterRunContext)
    assert loaded.component_run["round_id"] == "round-001"
    assert loaded.parsed_output["worker_tasks"][0]["task_id"] == "task-hyp-1-1"
    assert loaded.task_bundle_index["task_count"] == 1


def test_render_router_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = RouterRunContext(
        artifact_paths={
            "component_run_path": "router_run_001/component_run.json",
            "planner_strategy_path": "router_run_001/planner_strategy.json",
            "parsed_output_path": "router_run_001/parsed_output.json",
            "validation_report_path": "router_run_001/validation_report.json",
            "runtime_metrics_path": "router_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "round_id": "round-001",
            "hypothesis_id": "hyp-1",
            "planner_strategy_id": "strategy-hyp-1",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
        },
        planner_strategy={"strategy_id": "strategy-hyp-1"},
        router_context_min={"tool_capability_refs": ["feature_summary", "feature_relation"]},
        reduced_context={},
        prompt_text="prompt",
        raw_response_text="response",
        parsed_output={"worker_tasks": [{"task_id": "task-hyp-1-1"}, {"task_id": "task-hyp-1-2"}]},
        task_bundle_index={"task_count": 2},
        validation_report={},
        runtime_metrics={"duration_ms": 15.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_router_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "strategy-hyp-1" in cli._last_rendered
    assert "planner_strategy.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered