"""Strict parser and validator for JUDGE responses."""

from __future__ import annotations

import json
from typing import Any


TOP_LEVEL_FIELDS = {
    "behavior_summary",
    "key_patterns",
    "weaknesses",
    "strengths",
    "recommendations",
}
CLAIM_FIELDS = {"statement", "evidence", "confidence"}
VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_EVIDENCE_REFERENCES = {
    "header",
    "header.run_count",
    "header.source_run_ids",
    "header.source_artifacts",
    "header.export_scope",
    "cohort_context",
    "cohort_context.objective_frequency",
    "cohort_context.dataset_frequency",
    "cohort_context.model_name_frequency",
    "cohort_context.model_version_frequency",
    "cohort_context.max_steps_frequency",
    "cohort_context.tool_set",
    "aggregate",
    "aggregate.run_count",
    "aggregate.total_steps",
    "aggregate.tool_frequency",
    "aggregate.step_type_frequency",
    "aggregate.redundant_step_frequency",
    "aggregate.signal_frequency",
    "run_cards",
    "run_cards.run_id",
    "run_cards.artifact_name",
    "run_cards.objective",
    "run_cards.dataset",
    "run_cards.dataset.path_basename",
    "run_cards.dataset.path_hash",
    "run_cards.model",
    "run_cards.model.name",
    "run_cards.model.version",
    "run_cards.limits",
    "run_cards.limits.max_steps",
    "run_cards.run_counts",
    "run_cards.run_counts.total_steps",
    "run_cards.run_counts.error_steps",
    "run_cards.run_counts.contradiction_count",
    "run_cards.run_counts.target_card_count",
    "run_cards.tool_frequency",
    "run_cards.step_type_frequency",
    "run_cards.signal_frequency",
    "run_cards.step_trace",
    "run_cards.step_trace.step_index",
    "run_cards.step_trace.target_key",
    "run_cards.step_trace.target_type",
    "run_cards.step_trace.features",
    "run_cards.step_trace.tool",
    "run_cards.step_trace.step_type",
    "run_cards.step_trace.status",
    "run_cards.step_trace.signal_labels",
    "run_cards.step_trace.metric_anchors",
    "run_cards.step_trace.key_result_short",
    "run_cards.step_trace.novelty_sources",
    "run_cards.step_trace.information_gain",
    "run_cards.step_trace.redundant_step",
    "run_cards.feature_cards",
    "run_cards.feature_cards.target_key",
    "run_cards.feature_cards.target_type",
    "run_cards.feature_cards.features",
    "run_cards.feature_cards.first_seen_step",
    "run_cards.feature_cards.last_seen_step",
    "run_cards.feature_cards.step_indices",
    "run_cards.feature_cards.observation_count",
    "run_cards.feature_cards.tool_frequency",
    "run_cards.feature_cards.status_frequency",
    "run_cards.feature_cards.signal_frequency",
    "run_cards.feature_cards.metric_anchors",
    "run_cards.feature_cards.support_variants",
    "run_cards.feature_cards.contradiction_step_indices",
    "run_cards.contradictions",
    "run_cards.contradictions.step_index",
    "run_cards.contradictions.from_hypothesis",
    "run_cards.contradictions.to_hypothesis",
    "run_cards.contradictions.has_evidence_refs",
    "run_cards.errors",
    "run_cards.errors.step_index",
    "run_cards.errors.error_code",
    "run_cards.errors.error_message",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _validate_evidence_reference(value: str) -> str:
    if "[" in value or "]" in value:
        raise ValueError("evidence references must be field-level only")
    if value not in VALID_EVIDENCE_REFERENCES:
        raise ValueError(f"invalid evidence reference: {value}")
    return value


def _validate_claim_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("claim items must be JSON objects")
    keys = set(item.keys())
    if keys != CLAIM_FIELDS:
        raise ValueError(
            "claim items must contain exactly statement, evidence, confidence")

    statement = item.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("claim statement must be a non-empty string")

    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("claim evidence must be a non-empty list")
    normalized_evidence = []
    for evidence_ref in evidence:
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise ValueError(
                "claim evidence entries must be non-empty strings")
        normalized_evidence.append(
            _validate_evidence_reference(evidence_ref.strip()))

    confidence = item.get("confidence")
    if not isinstance(confidence, str) or confidence.strip() not in VALID_CONFIDENCE:
        raise ValueError("claim confidence must be one of high, medium, low")

    return {
        "statement": statement.strip(),
        "evidence": normalized_evidence,
        "confidence": confidence.strip(),
    }


def parse_judge_response(response_text: str) -> dict[str, Any]:
    """Parse and validate the LLM response for the JUDGE layer."""
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("judge response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("judge response must be a JSON object")

    keys = set(payload.keys())
    if keys != TOP_LEVEL_FIELDS:
        raise ValueError(
            "judge response must contain exactly the required top-level fields")

    behavior_summary = payload.get("behavior_summary")
    if not isinstance(behavior_summary, str) or not behavior_summary.strip():
        raise ValueError("behavior_summary must be a non-empty string")

    normalized = {"behavior_summary": behavior_summary.strip()}
    for section_name in ("key_patterns", "weaknesses", "strengths", "recommendations"):
        section_value = payload.get(section_name)
        if not isinstance(section_value, list):
            raise ValueError(f"{section_name} must be a list")
        normalized[section_name] = [
            _validate_claim_item(item) for item in section_value]

    return normalized
