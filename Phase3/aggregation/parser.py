"""Strict parser for Aggregation model output."""

from __future__ import annotations

import json
from typing import Any


TOP_LEVEL_FIELDS = {
    "batch_id",
    "round_id",
    "hypothesis_id",
    "merged_findings",
    "evidence_refs",
    "preserved_contradictions",
    "open_gaps",
    "update_focus",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_aggregation_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("aggregation response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("aggregation response must be a JSON object")

    if set(payload.keys()) == {"aggregation_handoff"}:
        payload = payload["aggregation_handoff"]

    if not isinstance(payload, dict):
        raise ValueError("aggregation_handoff must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "aggregation response must contain exactly batch_id, round_id, hypothesis_id, merged_findings, evidence_refs, preserved_contradictions, open_gaps, update_focus"
        )

    return payload