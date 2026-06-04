"""Contracts and defaults for the Phase 3A State Manager runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.state_manager.v1"
MAX_UPDATE_FOCUS_CHARS = 160
VALID_HYPOTHESIS_STATUSES = {
    "unresolved",
    "emerging",
    "active",
    "weakened",
    "dormant",
    "reopened",
    "merged",
    "partially_absorbed",
    "uncertain",
}


def _clone_json_like(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def build_state_update_result(
    *,
    batch_id: str,
    round_id: str,
    previous_state_version: int,
    new_state_version: int,
    applied_updates: list[dict[str, Any]],
    remaining_open_gaps: list[str],
) -> dict[str, Any]:
    return {
        "batch_id": str(batch_id or "unknown_batch").strip() or "unknown_batch",
        "round_id": str(round_id or "unknown_round").strip() or "unknown_round",
        "previous_state_version": int(previous_state_version),
        "new_state_version": int(new_state_version),
        "applied_updates": _clone_json_like(applied_updates),
        "remaining_open_gaps": list(remaining_open_gaps),
    }