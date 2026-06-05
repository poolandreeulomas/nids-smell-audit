"""Bridges current Phase 3A context surfaces into Investigation Analysis inputs."""

from __future__ import annotations

from typing import Any

from semantic_extraction.evidence_projector import normalize_partition_context


def _normalize_string(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        stripped = _normalize_string(value)
        if stripped:
            normalized.append(stripped)
    return normalized


def build_analysis_context_min(
    partition_context: dict[str, Any],
    artifact_framing_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_partition_context = normalize_partition_context(
        partition_context)
    normalized_framings: list[dict[str, str]] = []

    for raw_framing in artifact_framing_refs or []:
        if not isinstance(raw_framing, dict):
            continue
        framing_id = _normalize_string(raw_framing.get("framing_id"))
        label = _normalize_string(raw_framing.get("label"))
        description = _normalize_string(raw_framing.get("description"))
        if framing_id and label and description:
            normalized_framings.append(
                {
                    "framing_id": framing_id,
                    "label": label,
                    "description": description,
                }
            )

    return {
        "partition_context_ref": normalized_partition_context,
        "artifact_framing_refs": normalized_framings,
    }


def build_analysis_iteration_context_min(
    initial_hypothesis_set_ref: dict[str, Any] | None = None,
    current_state_ref: dict[str, Any] | None = None,
    critic_guidance: list[str] | None = None,
) -> dict[str, Any]:
    raw_hypothesis_set = dict(initial_hypothesis_set_ref or {})
    raw_current_state = dict(current_state_ref or {})

    normalized_hypothesis_refs: list[dict[str, str]] = []
    raw_hypotheses = raw_hypothesis_set.get("hypothesis_refs")
    if not isinstance(raw_hypotheses, list):
        raw_hypotheses = raw_hypothesis_set.get("hypotheses")

    if isinstance(raw_hypotheses, list):
        for raw_hypothesis in raw_hypotheses:
            if not isinstance(raw_hypothesis, dict):
                continue
            hypothesis_id = _normalize_string(
                raw_hypothesis.get("hypothesis_id"))
            summary = _normalize_string(raw_hypothesis.get("summary"))
            if hypothesis_id and summary:
                normalized_hypothesis_refs.append(
                    {
                        "hypothesis_id": hypothesis_id,
                        "summary": summary,
                    }
                )

    analysis_id = _normalize_string(raw_hypothesis_set.get("analysis_id"))
    state_id = _normalize_string(raw_current_state.get("state_id"))
    state_notes = _normalize_string_list(raw_current_state.get("state_notes"))

    if not analysis_id and not state_id and not state_notes and not normalized_hypothesis_refs:
        if critic_guidance:
            return {"critic_guidance": [str(item).strip() for item in critic_guidance if isinstance(item, str) and str(item).strip()]}
        return {}

    normalized_critic_guidance = [str(item).strip() for item in critic_guidance or [
    ] if isinstance(item, str) and str(item).strip()]

    payload = {
        "initial_hypothesis_set_ref": {
            "analysis_id": analysis_id,
            "hypothesis_refs": normalized_hypothesis_refs,
        },
        "current_state_ref": {
            "state_id": state_id,
            "state_notes": state_notes,
        },
    }
    if normalized_critic_guidance:
        payload["critic_guidance"] = normalized_critic_guidance
    return payload
