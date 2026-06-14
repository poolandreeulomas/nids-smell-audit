"""Trivial parser for Final Partition Audit Report model output.

Phase 3a: No section parsing. No markdown validation. No heading extraction.
          The report output is markdown — captured as-is.

Phase 3b: Parse JSON from LLM merge response into FinalDatasetReport.
"""

from __future__ import annotations

import json
import re
from typing import Any

from final_batch_report.contracts import FinalDatasetReport


# ── Phase 3a — Partition report parser ─────────────────────────────────────

def parse_report(raw_text: str) -> dict[str, Any]:
    """Capture the raw report markdown as-is.

    Args:
        raw_text: Raw LLM response text.

    Returns:
        Dict with single key `report_markdown`.
    """
    return {
        "report_markdown": str(raw_text or "").strip(),
    }


# ── Phase 3b — Dataset merger parser ──────────────────────────────────────

_JSON_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL
)


def _extract_json_from_response(raw_response: str) -> str:
    """Extract JSON string from raw LLM response, handling markdown fences.

    Steps:
    1. If the response contains a ```json or ``` code fence, extract content inside it.
    2. Otherwise, try to parse the entire response as JSON directly.
    """
    match = _JSON_FENCE_PATTERN.search(raw_response)
    if match:
        return match.group(1).strip()

    # No fences found — try treating the entire response as JSON
    stripped = raw_response.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    return stripped


def parse_merge_response(raw_response: str) -> FinalDatasetReport:
    """Parse the LLM's raw response into a FinalDatasetReport.

    Steps:
    1. Extract JSON from response (handles ```json fences).
    2. Parse JSON.
    3. Validate with Pydantic (FinalDatasetReport.model_validate(data)).
    4. Return FinalDatasetReport instance.

    Args:
        raw_response: Raw text response from the LLM.

    Returns:
        FinalDatasetReport instance validated by Pydantic.

    Raises:
        ValueError if JSON is invalid.
        pydantic.ValidationError if schema validation fails.
    """
    json_str = _extract_json_from_response(raw_response)
    if not json_str:
        raise ValueError("Empty response — no JSON content found")

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse JSON from LLM response: {exc}"
        ) from exc

    return FinalDatasetReport.model_validate(data)