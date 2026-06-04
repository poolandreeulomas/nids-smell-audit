"""Strict parser for Planner model output."""

from __future__ import annotations

import json
from typing import Any


TOP_LEVEL_FIELDS = {
    "batch_id",
    "round_id",
    "planner_strategies",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_planner_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("planner response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("planner response must be a JSON object")

    if set(payload.keys()) == {"planner_round_output"}:
        payload = payload["planner_round_output"]
    elif set(payload.keys()) == {"planner_output"}:
        payload = payload["planner_output"]

    if not isinstance(payload, dict):
        raise ValueError("planner_round_output must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "planner response must contain exactly batch_id, round_id, planner_strategies"
        )

    return payload