"""Strict parser for Critic model output."""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json

from critic.contracts import VALID_TARGET_MODULES


TOP_LEVEL_FIELDS = {"batch_id", "round_id", "critic_observations"}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _normalized_text(value: Any, default: str) -> str:
    return str(value or default).strip() or default


def parse_critic_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError:
        print("[JSON_RECOVERY] attempting repair")
        text = _strip_code_fences(response_text)
        try:
            repaired_text = repair_json(text)
            payload = json.loads(repaired_text)
            print("[JSON_RECOVERY] repair successful")
        except Exception:
            print("[JSON_RECOVERY] repair failed")
            raise ValueError("critic response is not valid JSON")

    if not isinstance(payload, dict):
        raise ValueError("critic response must be a JSON object")

    if TOP_LEVEL_FIELDS.issubset(set(payload.keys())):
        return payload

    inner = payload.get("critic_observations")
    if isinstance(inner, dict) and TOP_LEVEL_FIELDS.issubset(set(inner.keys())):
        return inner

    raise ValueError(
        "critic response must contain exactly batch_id, round_id, and critic_observations"
    )
