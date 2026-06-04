"""Strict parser for Critic model output."""

from __future__ import annotations

import json
from typing import Any


TOP_LEVEL_FIELDS = {
    "batch_id",
    "round_id",
    "module_feedback",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_critic_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("critic response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("critic response must be a JSON object")

    if set(payload.keys()) == {"critic_feedback_payload"}:
        payload = payload["critic_feedback_payload"]

    if not isinstance(payload, dict):
        raise ValueError("critic_feedback_payload must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "critic response must contain exactly batch_id, round_id, and module_feedback"
        )

    return payload
