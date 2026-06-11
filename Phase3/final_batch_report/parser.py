"""Trivial parser for Final Partition Audit Report model output.

No section parsing.
No markdown validation.
No heading extraction.
The report output is markdown â captured as-is.
"""

from __future__ import annotations

from typing import Any


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