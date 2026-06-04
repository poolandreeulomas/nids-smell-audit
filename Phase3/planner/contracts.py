"""Minimal contracts for the Phase 3A Planner runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.planner.v1"
MAX_PLANNER_STRATEGIES = 3


def _clone_json_like(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def build_planner_strategy(
    *,
    strategy_id: str,
    hypothesis_id: str,
    strategic_objective: str,
    key_checks: list[str],
    success_criteria: list[str],
    router_constraints: list[str],
) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "hypothesis_id": hypothesis_id,
        "strategic_objective": strategic_objective,
        "key_checks": list(key_checks),
        "success_criteria": list(success_criteria),
        "router_constraints": list(router_constraints),
    }


def build_planner_round_output(
    *,
    batch_id: str,
    round_id: str,
    planner_strategies: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "round_id": round_id,
        "planner_strategies": _clone_json_like(planner_strategies),
    }