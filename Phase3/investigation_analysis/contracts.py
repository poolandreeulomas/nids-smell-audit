"""Minimal contracts for the Phase 3A Investigation Analysis runtime."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "phase3a.investigation_analysis.v1"


def _string_list(values: list[str] | None = None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def build_artifact_framing_ref(
    *,
    framing_id: str,
    label: str,
    description: str,
) -> dict[str, str]:
    return {
        "framing_id": framing_id,
        "label": label,
        "description": description,
    }


def build_hypothesis(
    *,
    hypothesis_id: str,
    summary: str,
    evidence_refs: list[str] | None = None,
    open_questions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis_id,
        "summary": summary,
        "evidence_refs": _string_list(evidence_refs),
        "open_questions": _string_list(open_questions),
    }


def build_hypothesis_set(
    *,
    analysis_id: str,
    batch_id: str,
    hypotheses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "analysis_id": analysis_id,
        "batch_id": batch_id,
        "hypotheses": [dict(item) for item in (hypotheses or [])],
    }