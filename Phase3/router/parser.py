"""Strict parser for Router model output."""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json


TOP_LEVEL_FIELDS = {
    "batch_id",
    "round_id",
    "hypothesis_id",
    "planner_strategy_id",
    "worker_tasks",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_router_response(response_text: str) -> dict[str, Any]:
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
            raise ValueError("router response is not valid JSON")

    if not isinstance(payload, dict):
        raise ValueError("router response must be a JSON object")

    if set(payload.keys()) == {"router_output"}:
        payload = payload["router_output"]
    elif set(payload.keys()) == {"routing_output"}:
        payload = payload["routing_output"]

    if not isinstance(payload, dict):
        raise ValueError("router_output must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "router response must contain exactly batch_id, round_id, hypothesis_id, planner_strategy_id, worker_tasks"
        )

    return payload