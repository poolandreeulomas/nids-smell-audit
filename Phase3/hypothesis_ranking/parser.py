"""Strict parser for Hypothesis Ranking model output."""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json


TOP_LEVEL_FIELDS = {
    "batch_id",
    "round_id",
    "selected_hypothesis_ids",
    "deferred_hypothesis_ids",
    "selection_rationales",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_hypothesis_ranking_response(response_text: str) -> dict[str, Any]:
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
            raise ValueError("hypothesis ranking response is not valid JSON")

    if not isinstance(payload, dict):
        raise ValueError("hypothesis ranking response must be a JSON object")

    if set(payload.keys()) == {"ranking_decision"}:
        payload = payload["ranking_decision"]
    elif set(payload.keys()) == {"hypothesis_ranking_output"}:
        payload = payload["hypothesis_ranking_output"]

    if not isinstance(payload, dict):
        raise ValueError("ranking_decision must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "hypothesis ranking response must contain exactly batch_id, round_id, selected_hypothesis_ids, deferred_hypothesis_ids, selection_rationales"
        )

    return payload