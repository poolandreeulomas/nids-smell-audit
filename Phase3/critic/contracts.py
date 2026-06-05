"""Contracts and defaults for the Phase 3A Critic runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.critic.v2"
MAX_CRITIC_OBSERVATIONS = 3
MAX_RATIONALE_CHARS = 250
MAX_PROMPT_SNIPPET_CHARS = 180
VALID_TARGET_MODULES = {
    "investigation_analysis",
    "hypothesis_ranking",
    "planner",
}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_OBSERVATION_TYPES = {
    "underexplored_hypothesis",
    "underexplored_region",
    "premature_convergence",
    "exploration_bias",
    "weak_signal_neglect",
    "diminishing_returns",
    "persistent_unresolved_tension",
    "investigation_imbalance",
    "high_uncertainty_high_potential",
    "investigation_focus",
    "productive_active_line",
}

# Compatibility aliases retained for historical loaders and review surfaces.
MAX_MODULE_FEEDBACK_ITEMS = MAX_CRITIC_OBSERVATIONS
MAX_OBSERVED_ISSUE_CHARS = MAX_RATIONALE_CHARS
MAX_SUGGESTION_CHARS = MAX_PROMPT_SNIPPET_CHARS
VALID_MODULE_NAMES = VALID_TARGET_MODULES | {
    "semantic_extraction",
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


def _normalized_text(value: Any, default: str) -> str:
    return str(value or default).strip() or default


def build_critic_observations_payload(
    *,
    batch_id: str,
    round_id: str,
    critic_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "batch_id": _normalized_text(batch_id, "unknown_batch"),
        "round_id": _normalized_text(round_id, "unknown_round"),
        "critic_observations": _clone_json_like(critic_observations),
    }
