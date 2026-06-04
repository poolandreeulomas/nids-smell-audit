"""Strict parser for Investigation Analysis model output."""

from __future__ import annotations

import json
from typing import Any


TOP_LEVEL_FIELDS = {
    "analysis_id",
    "batch_id",
    "hypotheses",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_investigation_analysis_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("investigation analysis response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("investigation analysis response must be a JSON object")

    if set(payload.keys()) == {"hypothesis_set"}:
        payload = payload["hypothesis_set"]
    elif set(payload.keys()) == {"investigation_analysis_output"}:
        payload = payload["investigation_analysis_output"]

    if not isinstance(payload, dict):
        raise ValueError("hypothesis_set must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "investigation analysis response must contain exactly analysis_id, batch_id, hypotheses"
        )

    return payload