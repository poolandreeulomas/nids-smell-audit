"""Strict parser for Semantic Extraction model output."""

from __future__ import annotations

import json
from typing import Any


TOP_LEVEL_FIELDS = {
    "substrate_id",
    "batch_id",
    "compressed_regions",
    "preserved_weak_signals",
    "contradictions",
    "unresolved_tensions",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_semantic_extraction_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("semantic extraction response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("semantic extraction response must be a JSON object")

    if set(payload.keys()) == {"semantic_substrate"}:
        payload = payload["semantic_substrate"]

    if not isinstance(payload, dict):
        raise ValueError("semantic_substrate must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "semantic extraction response must contain exactly substrate_id, batch_id, compressed_regions, preserved_weak_signals, contradictions, unresolved_tensions"
        )

    return payload