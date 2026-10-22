"""Contracts and constants for Phase 3A Round-Level Final Reports.

Follows the schema and architectural conventions of Phase3/final_batch_report/.
"""

from __future__ import annotations

from typing import Any


ROUND_REPORT_SCHEMA_VERSION = "phase3.round_report.v1"
ROUND_REPORT_PROMPT_VERSION = "phase3.round_report.prompt.v1"

# 9 authoritative section titles required for the round report markdown
ROUND_REPORT_SECTIONS: tuple[str, ...] = (
    "Execution Identity and Status",
    "Executive Summary",
    "Investigation Objectives and Hypotheses",
    "Investigation Process and Tools Used",
    "Evidence and Statistical Results",
    "Findings and Their Interpretation",
    "State Changes and Critic Assessment",
    "Unresolved Questions and Contradictions",
    "Limitations and Evidence Provenance",
)
