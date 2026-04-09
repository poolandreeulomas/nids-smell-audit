"""Metrics helpers for MVP run evaluation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from state.schema import AgentState
from state.store import state_to_dict

VALID_ACTION_STATUSES = {"OK"}
ATTEMPTED_ACTION_STATUSES = {"OK", "TOOL_ERROR", "REPEATED_FEATURE_BLOCKED"}


def _extract_feature_name(step: dict[str, Any]) -> str | None:
    action_input = step.get("action_input") or {}
    feature_name = action_input.get("feature_name")
    return feature_name if isinstance(feature_name, str) and feature_name else None


def _normalize_thought(thought: str | None) -> str:
    if not thought:
        return ""
    return " ".join(thought.lower().split())


def _iter_history(state_or_dict: AgentState | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(state_or_dict, AgentState):
        return state_or_dict.history
    return list(state_or_dict.get("history", []))


def compute_run_metrics(state_or_dict: AgentState | dict[str, Any]) -> dict[str, Any]:
    """Compute MVP metrics from state or persisted run log payload."""
    history = _iter_history(state_or_dict)
    total_steps = len(history)
    if total_steps == 0:
        return {
            "total_steps": 0,
            "valid_action_rate": 0.0,
            "parse_error_rate": 0.0,
            "tool_error_rate": 0.0,
            "unique_features_explored": 0,
            "repeated_feature_rate": 0.0,
            "action_justification_rate": 0.0,
            "status_counts": {},
        }

    status_counts = Counter(step.get("execution_status", "UNKNOWN")
                            for step in history)
    valid_action_steps = [
        step for step in history if step.get("execution_status") in VALID_ACTION_STATUSES
    ]
    attempted_action_steps = [
        step
        for step in history
        if step.get("execution_status") in ATTEMPTED_ACTION_STATUSES
    ]
    parse_error_steps = [
        step for step in history if step.get("execution_status") == "PARSE_ERROR"
    ]
    tool_error_steps = [
        step for step in history if step.get("execution_status") == "TOOL_ERROR"
    ]

    seen_features: set[str] = set()
    repeated_feature_count = 0
    unique_features: set[str] = set()

    feature_tools: dict[str, set[str]] = {}
    previous_thoughts: list[str] = []
    justified_count = 0

    for step in history:
        status = step.get("execution_status")
        feature_name = _extract_feature_name(step)
        thought = _normalize_thought(step.get("thought"))
        action = step.get("action")

        if status not in ATTEMPTED_ACTION_STATUSES or not feature_name:
            if thought:
                previous_thoughts.append(thought)
            continue

        unique_features.add(feature_name)
        if status == "REPEATED_FEATURE_BLOCKED" or feature_name in seen_features:
            repeated_feature_count += 1
        seen_features.add(feature_name)

        tools_used_before = feature_tools.get(feature_name, set())
        fully_explored_before = len(tools_used_before) >= 2
        thought_is_new = bool(
            thought) and thought not in previous_thoughts[-3:]
        if (not fully_explored_before) and thought_is_new:
            justified_count += 1

        if action:
            feature_tools.setdefault(feature_name, set()).add(action)
        if thought:
            previous_thoughts.append(thought)

    valid_action_count = len(valid_action_steps)
    attempted_action_count = len(attempted_action_steps)
    return {
        "total_steps": total_steps,
        "valid_action_rate": valid_action_count / total_steps,
        "parse_error_rate": len(parse_error_steps) / total_steps,
        "tool_error_rate": len(tool_error_steps) / total_steps,
        "unique_features_explored": len(unique_features),
        "repeated_feature_rate": (
            repeated_feature_count / attempted_action_count if attempted_action_count else 0.0
        ),
        "action_justification_rate": (
            justified_count / valid_action_count if valid_action_count else 0.0
        ),
        "attempted_action_rate": attempted_action_count / total_steps,
        "status_counts": dict(status_counts),
    }


def extract_final_feature_list(run_payload: dict[str, Any]) -> list[str]:
    """Extract final feature list for run comparison."""
    promising = run_payload.get("promising_features", [])
    if promising:
        return list(promising)
    analyzed = run_payload.get("analyzed_features", {})
    return list(analyzed.keys())


def compute_overlap_score(features_a: list[str], features_b: list[str]) -> float:
    """Compute simple overlap score for two feature lists."""
    set_a = set(features_a)
    set_b = set(features_b)
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def state_metrics_payload(state: AgentState) -> dict[str, Any]:
    """Convenience wrapper to compute metrics from AgentState."""
    return compute_run_metrics(state_to_dict(state))
