import json
from pathlib import Path

from router.context_reducer import build_router_context_min
from router.parser import parse_router_response
from router.runner import run_router
from router.runtime_artifacts import load_router_bundle
from router.validator import validate_router_output


def _build_planner_strategy() -> dict[str, object]:
    return {
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
    }


def _build_router_context_min() -> dict[str, object]:
    return build_router_context_min(
        related_substrate_refs=["e1", "e2", "e3"],
        tool_capability_refs=["feature_summary", "feature_relation", "shortcut_analysis"],
        execution_budget={
            "max_worker_steps": 8,
            "max_tasks": 4,
            "max_retries": 1,
        },
        guardrails=[
            "bounded_local_scope",
            "no_exact_tool_calls",
            "no_hidden_replanning",
        ],
    )


def _build_valid_response_payload() -> dict[str, object]:
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
            },
            {
                "task_id": "task-hyp-1-2",
                "hypothesis_id": "hyp-1",
                "task_scope": "Probe whether the broad region remains informative outside the narrow local slice.",
                "allowed_actions": ["structural_summary", "relation_verification"],
                "local_context_refs": ["e1", "e2"],
                "stop_conditions": [
                    "Stop when the broad region is either preserved or meaningfully weakened outside the narrow local slice.",
                    "Stop when local context coverage is exhausted or the worker budget is reached.",
                ],
            },
        ],
    }


def test_parse_router_response_accepts_wrapped_payload():
    payload = _build_valid_response_payload()

    parsed = parse_router_response(json.dumps({"router_output": payload}))

    assert parsed["round_id"] == "round-001"
    assert parsed["worker_tasks"][0]["task_id"] == "task-hyp-1-1"


def test_run_router_returns_valid_bundle_and_artifacts(tmp_path: Path):
    bundle = run_router(
        _build_planner_strategy(),
        _build_router_context_min(),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: json.dumps(_build_valid_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["ok"] is True
    assert bundle["router_output"]["planner_strategy_id"] == "strategy-hyp-1"
    assert bundle["task_bundle_index"]["task_count"] == 2
    assert "Convert the incoming planner strategy into at most 4 worker-compatible tasks." in bundle["prompt_text"]
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["task_bundle_index_path"]).exists()

    loaded = load_router_bundle(Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["parsed_output"]["worker_tasks"][0]["task_id"] == "task-hyp-1-1"
    assert loaded["task_bundle_index"]["task_count"] == 2
    assert loaded["runtime_metrics"]["status"] == "ok"
    assert loaded["replay_metadata"]["fresh_execution"] is True


def test_validate_router_output_rejects_exact_tool_names_in_task_scope():
    payload = _build_valid_response_payload()
    payload["worker_tasks"][0]["task_scope"] = "Use feature_summary and feature_relation on the first local slice immediately."

    report = validate_router_output(
        payload,
        expected_batch_id="batch-001",
        expected_round_id="round-001",
        expected_hypothesis_id="hyp-1",
        expected_planner_strategy_id="strategy-hyp-1",
        allowed_action_classes={"structural_summary", "relation_verification", "shortcut_verification"},
        known_context_refs={"e1", "e2", "e3"},
        max_tasks=4,
        known_tool_capability_refs={"feature_summary", "feature_relation", "shortcut_analysis"},
    )

    assert report["ok"] is True
    assert any("Semantic language flag detected" in warning["message"] for warning in report["warnings"])


def test_validate_router_output_rejects_extra_worker_task_fields():
    payload = _build_valid_response_payload()
    payload["worker_tasks"][0]["task_role"] = "broad_probe"

    report = validate_router_output(
        payload,
        expected_batch_id="batch-001",
        expected_round_id="round-001",
        expected_hypothesis_id="hyp-1",
        expected_planner_strategy_id="strategy-hyp-1",
        allowed_action_classes={"structural_summary", "relation_verification", "shortcut_verification"},
        known_context_refs={"e1", "e2", "e3"},
        max_tasks=4,
        known_tool_capability_refs={"feature_summary", "feature_relation", "shortcut_analysis"},
    )

    assert report["ok"] is False
    assert any("unsupported fields" in error["message"] for error in report["errors"])


def test_run_router_rejects_invalid_router_context_before_calling_llm(tmp_path: Path):
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return json.dumps(_build_valid_response_payload())

    bundle = run_router(
        _build_planner_strategy(),
        {
            "related_substrate_refs": ["e1"],
            "tool_capability_refs": ["unknown_tool"],
            "execution_budget": {"max_worker_steps": 8, "max_tasks": 4, "max_retries": 1},
            "guardrails": ["bounded_local_scope"],
        },
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=_unexpected_call,
        log_dir=str(tmp_path),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["router_context_validation"]["ok"] is False
    assert bundle["prompt_text"] == ""
    assert llm_called["value"] is False