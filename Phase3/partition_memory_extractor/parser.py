"""Strict structural parser for Partition Memory model output.

Performs structural validation only — no value ranges, no minimum counts,
no mandatory content rules beyond what the schema explicitly requires.
"""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json

REQUIRED_TOP_LEVEL_FIELDS = {
    "partition_id",
    "recommendation",
    "overall_assessment",
    "artifact_families",
    "major_findings",
    "open_risks",
    "coverage_signals",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_partition_memory(response_text: str) -> dict[str, Any]:
    """Parse and structurally validate a Partition Memory from LLM output.

    Args:
        response_text: Raw LLM response text.

    Returns:
        Parsed Partition Memory dict.

    Raises:
        ValueError: If the response is not valid JSON or structural
        validation fails.
    """
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
            raise ValueError("partition memory response is not valid JSON")

    if not isinstance(payload, dict):
        raise ValueError("partition memory response must be a JSON object")

    # Allow single-wrapper key
    if set(payload.keys()) == {"partition_memory"}:
        payload = payload["partition_memory"]

    if not isinstance(payload, dict):
        raise ValueError("partition_memory must be a JSON object")

    # Structural: required top-level keys must be present (type-check only)
    actual_keys = set(payload.keys())
    missing = REQUIRED_TOP_LEVEL_FIELDS - actual_keys
    if missing:
        raise ValueError(
            f"partition memory missing required fields: {sorted(missing)}"
        )

    # Type-check overall_assessment (must be dict with risk_level, confidence_level)
    assessment = payload.get("overall_assessment")
    if not isinstance(assessment, dict):
        raise ValueError("overall_assessment must be a JSON object")
    if "risk_level" not in assessment:
        raise ValueError("overall_assessment must contain 'risk_level'")
    if "confidence_level" not in assessment:
        raise ValueError("overall_assessment must contain 'confidence_level'")

    # Check that list fields are lists
    for list_field in ("artifact_families", "major_findings", "open_risks", "coverage_signals"):
        value = payload.get(list_field)
        if not isinstance(value, list):
            raise ValueError(f"{list_field} must be a JSON array")

    return payload