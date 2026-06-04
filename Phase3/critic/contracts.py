"""Contracts and defaults for the Phase 3A Critic runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.critic.v1"
MAX_MODULE_FEEDBACK_ITEMS = 4
MAX_OBSERVED_ISSUE_CHARS = 220
MAX_SUGGESTION_CHARS = 180
VALID_MODULE_NAMES = {
    "semantic_extraction",
    "investigation_analysis",
    "hypothesis_ranking",
    "planner",
    "router",
    "worker",
    "aggregation",
    "state_manager",
    "critic",
    "tools",
}


def _clone_json_like(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def build_critic_feedback_payload(
    *,
    batch_id: str,
    round_id: str,
    module_feedback: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "batch_id": str(batch_id or "unknown_batch").strip() or "unknown_batch",
        "round_id": str(round_id or "unknown_round").strip() or "unknown_round",
        "module_feedback": _clone_json_like(module_feedback),
    }
