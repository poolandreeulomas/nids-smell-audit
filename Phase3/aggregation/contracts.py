"""Contracts and defaults for the Phase 3A Aggregation runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.aggregation.v1"
MAX_UPDATE_FOCUS_CHARS = 160


def _clone_json_like(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def build_worker_result_set(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    worker_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "batch_id": str(batch_id or "unknown_batch").strip() or "unknown_batch",
        "round_id": str(round_id or "unknown_round").strip() or "unknown_round",
        "hypothesis_id": str(hypothesis_id or "unknown_hypothesis").strip() or "unknown_hypothesis",
        "worker_results": _clone_json_like(worker_results),
    }


def build_aggregation_handoff(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    merged_findings: list[str],
    evidence_refs: list[str],
    preserved_contradictions: list[str],
    open_gaps: list[str],
    update_focus: str,
) -> dict[str, Any]:
    return {
        "batch_id": str(batch_id or "unknown_batch").strip() or "unknown_batch",
        "round_id": str(round_id or "unknown_round").strip() or "unknown_round",
        "hypothesis_id": str(hypothesis_id or "unknown_hypothesis").strip() or "unknown_hypothesis",
        "merged_findings": list(merged_findings),
        "evidence_refs": list(evidence_refs),
        "preserved_contradictions": list(preserved_contradictions),
        "open_gaps": list(open_gaps),
        "update_focus": str(update_focus or "").strip(),
    }