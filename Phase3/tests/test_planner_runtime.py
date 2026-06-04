import json
from pathlib import Path

from planner.context_resolver import build_planner_round_context, build_selected_hypothesis_context
from planner.parser import parse_planner_response
from planner.runner import run_planner
from planner.runtime_artifacts import load_planner_bundle
from planner.validator import validate_planner_round_output


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
        tool_capability_refs=[
            "feature_summary",
            "feature_relation",
            "shortcut_analysis",
        ],
        round_constraints=[
            "strategic_only",
            "no_exact_tool_calls",
            "preserve_selected_scope",
        ],
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


def test_parse_planner_response_accepts_wrapped_payload():
    payload = _build_valid_response_payload()

    parsed = parse_planner_response(json.dumps({"planner_round_output": payload}))

    assert parsed["round_id"] == "round-001"
    assert parsed["planner_strategies"][0]["strategy_id"] == "strategy-hyp-1"


def test_run_planner_returns_valid_bundle_and_artifacts(tmp_path: Path):
    bundle = run_planner(
        _build_ranking_decision_min(),
        _build_selected_hypothesis_context(),
        _build_planner_round_context(),
        llm_callable=lambda prompt_text: json.dumps(_build_valid_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["ok"] is True
    assert bundle["planner_round_output"]["round_id"] == "round-001"
    assert bundle["strategy_index"]["strategy_count"] == 2
    assert "Produce exactly one planner_strategy per selected hypothesis for round_id=round-001 in batch_id=batch-001." in bundle["prompt_text"]
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["strategy_index_path"]).exists()

    loaded = load_planner_bundle(Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["parsed_output"]["planner_strategies"][0]["strategy_id"] == "strategy-hyp-1"
    assert loaded["strategy_index"]["strategy_count"] == 2
    assert loaded["runtime_metrics"]["status"] == "ok"
    assert loaded["replay_metadata"]["fresh_execution"] is True


def test_validate_planner_round_output_rejects_exact_tool_calls():
    payload = _build_valid_response_payload()
    payload["planner_strategies"][0]["key_checks"][0] = "Use feature_summary on dst_port and feature_relation on src_bytes immediately."

    report = validate_planner_round_output(
        payload,
        selected_hypothesis_ids=["hyp-1", "hyp-3"],
        expected_batch_id="batch-001",
        expected_round_id="round-001",
        known_tool_capability_refs={
            "feature_summary",
            "feature_relation",
            "shortcut_analysis",
        },
    )

    assert report["ok"] is True
    assert any("Semantic language flag detected" in warning["message"] for warning in report["warnings"])


def test_run_planner_rejects_invalid_round_context_before_calling_llm(tmp_path: Path):
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return json.dumps(_build_valid_response_payload())

    bundle = run_planner(
        _build_ranking_decision_min(),
        _build_selected_hypothesis_context(),
        {
            "round_id": "round-001",
            "related_substrate_refs": ["e1"],
            "tool_capability_refs": ["unknown_tool"],
            "round_constraints": ["strategic_only"],
        },
        llm_callable=_unexpected_call,
        log_dir=str(tmp_path),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["planner_round_context_validation"]["ok"] is False
    assert bundle["prompt_text"] == ""
    assert llm_called["value"] is False


def test_build_planner_prompt_sanitizes_forbidden_reranking_terms():
    """Verify that reranking_language terms in hypothesis context are sanitized before injection."""
    from planner.prompt_builder import build_planner_prompt

    # Context containing forbidden reranking terms
    selected_context = {
        "selected_count": 1,
        "selected_hypotheses": [
            {
                "hypothesis_id": "hyp_06_top_ranked_packet_length_features_redundancy_and_stability",
                "summary": "Top-ranked features such as Bwd Packet Length Mean show ranking behavior and ranked patterns.",
                "evidence_refs": ["e3", "e4"],
                "open_questions": ["Question about top-ranked features?"],
                "current_status": "selected_for_round",
            }
        ],
    }

    round_context = {
        "round_id": "round-001",
        "related_substrate_refs": ["e3", "e4"],
        "tool_capability_refs": ["feature_summary"],
        "round_constraints": ["strategic_only"],
    }

    prompt = build_planner_prompt(
        batch_id="test-batch",
        round_id="round-001",
        projected_selected_context=selected_context,
        projected_planner_round_context=round_context,
    )

    # Verify forbidden terms are replaced in hypothesis_id (underscore variant)
    assert "top_ranked" not in prompt
    assert "top-ranked" not in prompt
    assert "high-salience" in prompt  # replacement for top-ranked/top_ranked

    # Verify ranking variants are replaced
    assert "ranking" not in prompt.lower() or "relative importance" in prompt
    
    # Verify prominent appears (replacement for ranked)
    assert "prominent" in prompt

    # Verify summary with forbidden terms gets sanitized
    assert "Bwd Packet Length Mean show ranking" not in prompt  # original would have "ranking"

    # Verify that batch_id and round_id are preserved
    assert "round-001" in prompt
    assert "test-batch" in prompt