"""Minimal contracts for the Phase 3A Router runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.router.v1"
DEFAULT_MAX_WORKER_STEPS = 8
DEFAULT_MAX_ROUTER_TASKS = 4
DEFAULT_MAX_WORKER_RETRIES = 1


def _clone_json_like(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def build_worker_task(
    *,
    task_id: str,
    hypothesis_id: str,
    task_scope: str,
    allowed_actions: list[str],
    local_context_refs: list[str],
    stop_conditions: list[str],
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "hypothesis_id": hypothesis_id,
        "task_scope": task_scope,
        "allowed_actions": list(allowed_actions),
        "local_context_refs": list(local_context_refs),
        "stop_conditions": list(stop_conditions),
    }


def build_router_output(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    planner_strategy_id: str,
    worker_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "round_id": round_id,
        "hypothesis_id": hypothesis_id,
        "planner_strategy_id": planner_strategy_id,
        "worker_tasks": _clone_json_like(worker_tasks),
    }