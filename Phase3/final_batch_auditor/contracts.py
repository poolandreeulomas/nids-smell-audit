"""Contracts and defaults for the Phase 3A Final Batch Auditor runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.final_batch_auditor.v1"
MAX_SUMMARY_CHARS = 900
MAX_LIST_ITEMS = 6
MAX_LIST_ITEM_CHARS = 220
VALID_ROUND_COMPONENT_NAMES = {
    "state_manager",
    "aggregation",
    "critic",
}


def _clone_json_like(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def build_debugging_audit_report(
    *,
    batch_id: str,
    trajectory_summary: str,
    hypothesis_summary: str,
    surviving_contradictions: list[str],
    open_pressures: list[str],
    failure_summary: str,
    traceability_refs: list[str],
) -> dict[str, Any]:
    return {
        "batch_id": str(batch_id or "unknown_batch").strip() or "unknown_batch",
        "trajectory_summary": str(trajectory_summary or "").strip(),
        "hypothesis_summary": str(hypothesis_summary or "").strip(),
        "surviving_contradictions": _clone_json_like(surviving_contradictions),
        "open_pressures": _clone_json_like(open_pressures),
        "failure_summary": str(failure_summary or "").strip(),
        "traceability_refs": _clone_json_like(traceability_refs),
    }
