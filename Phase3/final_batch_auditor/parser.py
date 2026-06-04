"""Strict parser for Final Batch Auditor model output."""

from __future__ import annotations

import json
from typing import Any


TOP_LEVEL_FIELDS = {
    "batch_id",
    "trajectory_summary",
    "hypothesis_summary",
    "surviving_contradictions",
    "open_pressures",
    "failure_summary",
    "traceability_refs",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_final_batch_auditor_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("final batch auditor response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("final batch auditor response must be a JSON object")

    if set(payload.keys()) == {"debugging_audit_report"}:
        payload = payload["debugging_audit_report"]

    if not isinstance(payload, dict):
        raise ValueError("debugging_audit_report must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "final batch auditor response must contain exactly batch_id, trajectory_summary, "
            "hypothesis_summary, surviving_contradictions, open_pressures, failure_summary, and traceability_refs"
        )

    return payload
