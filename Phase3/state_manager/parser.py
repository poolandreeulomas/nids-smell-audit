"""Strict parser for State Manager model output."""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json


TOP_LEVEL_FIELDS = {
    "batch_id",
    "round_id",
    "hypothesis_id",
    "summary",
    "status",
    "evidence_refs",
    "preserved_contradictions",
    "open_gaps",
    "merged_findings",
    "update_focus",
    "applied_updates",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_state_manager_response(response_text: str) -> dict[str, Any]:
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
            raise ValueError("state manager response is not valid JSON")

    if not isinstance(payload, dict):
        raise ValueError("state manager response must be a JSON object")

    if set(payload.keys()) == {"state_delta_record"}:
        payload = payload["state_delta_record"]

    if not isinstance(payload, dict):
        raise ValueError("state_delta_record must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "state manager response must contain exactly batch_id, round_id, hypothesis_id, summary, status, evidence_refs, preserved_contradictions, open_gaps, merged_findings, update_focus, applied_updates"
        )

    return payload