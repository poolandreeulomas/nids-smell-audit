"""Projection helpers from the canonical inter-hypothesis artifact to State Manager input."""

from __future__ import annotations

from typing import Any


def _string_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        stripped = _string_value(value)
        if stripped:
            normalized.append(stripped)
    return list(dict.fromkeys(normalized))


def build_state_manager_projection(
    canonical_round_artifact: dict[str, Any],
    *,
    hypothesis_id: str,
) -> dict[str, Any]:
    raw = canonical_round_artifact if isinstance(
        canonical_round_artifact, dict) else {}
    batch_id = _string_value(raw.get("batch_id"))
    round_id = _string_value(raw.get("round_id"))
    for record in list(raw.get("source_hypothesis_records", []) or []):
        if not isinstance(record, dict):
            continue
        if _string_value(record.get("hypothesis_id")) != _string_value(hypothesis_id):
            continue
        return {
            "batch_id": batch_id,
            "round_id": round_id,
            "hypothesis_id": hypothesis_id,
            "merged_findings": _string_list(record.get("merged_findings")),
            "evidence_refs": _string_list(record.get("evidence_refs")),
            "preserved_contradictions": _string_list(record.get("preserved_contradictions")),
            "open_gaps": _string_list(record.get("open_gaps")),
            "update_focus": _string_value(record.get("update_focus")),
        }
    raise KeyError(
        f"No source_hypothesis_record found for hypothesis_id={hypothesis_id}")


def build_state_manager_projections(
    canonical_round_artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = canonical_round_artifact if isinstance(
        canonical_round_artifact, dict) else {}
    projections: list[dict[str, Any]] = []
    for record in list(raw.get("source_hypothesis_records", []) or []):
        if not isinstance(record, dict):
            continue
        hypothesis_id = _string_value(record.get("hypothesis_id"))
        if not hypothesis_id:
            continue
        projections.append(
            build_state_manager_projection(
                raw,
                hypothesis_id=hypothesis_id,
            )
        )
    return projections
