"""Context normalization and prompt-ready reduction helpers for Router."""

from __future__ import annotations

from typing import Any

from router.contracts import (
    DEFAULT_MAX_ROUTER_TASKS,
    DEFAULT_MAX_WORKER_RETRIES,
    DEFAULT_MAX_WORKER_STEPS,
)


def _string_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def build_router_context_min(
    *,
    related_substrate_refs: list[str] | None = None,
    tool_capability_refs: list[str] | None = None,
    execution_budget: dict[str, Any] | None = None,
    guardrails: list[str] | None = None,
) -> dict[str, Any]:
    raw_budget = execution_budget if isinstance(execution_budget, dict) else {}
    max_worker_steps = raw_budget.get("max_worker_steps")
    if not isinstance(max_worker_steps, int) or max_worker_steps <= 0:
        max_worker_steps = DEFAULT_MAX_WORKER_STEPS

    max_tasks = raw_budget.get("max_tasks")
    if not isinstance(max_tasks, int) or max_tasks <= 0:
        max_tasks = DEFAULT_MAX_ROUTER_TASKS

    max_retries = raw_budget.get("max_retries")
    if not isinstance(max_retries, int) or max_retries < 0:
        max_retries = DEFAULT_MAX_WORKER_RETRIES

    return {
        "related_substrate_refs": _string_list(related_substrate_refs),
        "tool_capability_refs": _string_list(tool_capability_refs),
        "execution_budget": {
            "max_worker_steps": max_worker_steps,
            "max_tasks": max_tasks,
            "max_retries": max_retries,
        },
        "guardrails": _string_list(guardrails),
    }


def collect_known_action_classes(
    tool_capability_refs: list[str],
    tool_capability_catalog: dict[str, dict[str, Any]],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for tool_ref in tool_capability_refs:
        record = tool_capability_catalog.get(tool_ref, {}) if isinstance(
            tool_capability_catalog, dict) else {}
        action_class = _string_value(record.get("epistemic_role"))
        if not action_class or action_class in seen:
            continue
        seen.add(action_class)
        ordered.append(action_class)
    return ordered


def project_planner_strategy(planner_strategy: dict[str, Any]) -> dict[str, Any]:
    raw = planner_strategy if isinstance(planner_strategy, dict) else {}
    key_checks = _string_list(raw.get("key_checks"))
    success_criteria = _string_list(raw.get("success_criteria"))
    router_constraints = _string_list(raw.get("router_constraints"))

    return {
        "strategy_id": _string_value(raw.get("strategy_id")),
        "hypothesis_id": _string_value(raw.get("hypothesis_id")),
        "strategic_objective": _string_value(raw.get("strategic_objective")),
        "key_checks": key_checks,
        "success_criteria": success_criteria,
        "router_constraints": router_constraints,
        "key_check_count": len(key_checks),
        "success_criteria_count": len(success_criteria),
        "router_constraint_count": len(router_constraints),
    }


def project_router_context_min(
    router_context_min: dict[str, Any],
    *,
    tool_capability_catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw = router_context_min if isinstance(router_context_min, dict) else {}
    tool_refs = _string_list(raw.get("tool_capability_refs"))
    tool_catalog = tool_capability_catalog or {}
    execution_budget = raw.get("execution_budget") if isinstance(
        raw.get("execution_budget"), dict) else {}

    # Reduce the routing context deliberately: avoid leaking exact tool names
    # or internal shapes into the Router prompt. The Router only needs the
    # `tool_capability_refs` and the `available_action_classes` to choose
    # canonical action classes for worker tasks.
    return {
        "related_substrate_refs": _string_list(raw.get("related_substrate_refs")),
        "tool_capability_refs": tool_refs,
        # Intentionally omit detailed `tool_capabilities` (tool_name,
        # epistemic_role, result_shape) to reduce vocabulary leakage in
        # prompts. Expose only the canonical action classes available.
        "available_action_classes": collect_known_action_classes(tool_refs, tool_catalog),
        "execution_budget": {
            "max_worker_steps": execution_budget.get("max_worker_steps") if isinstance(execution_budget.get("max_worker_steps"), int) else 0,
            "max_tasks": execution_budget.get("max_tasks") if isinstance(execution_budget.get("max_tasks"), int) else 0,
            "max_retries": execution_budget.get("max_retries") if isinstance(execution_budget.get("max_retries"), int) else 0,
        },
        "guardrails": _string_list(raw.get("guardrails")),
    }


def build_task_bundle_index(router_output: dict[str, Any]) -> dict[str, Any]:
    raw = router_output if isinstance(router_output, dict) else {}
    worker_tasks = raw.get("worker_tasks") if isinstance(
        raw.get("worker_tasks"), list) else []
    seen_action_classes: set[str] = set()
    task_summaries: list[dict[str, Any]] = []

    for worker_task in worker_tasks:
        if not isinstance(worker_task, dict):
            continue
        allowed_actions = _string_list(worker_task.get("allowed_actions"))
        local_context_refs = _string_list(
            worker_task.get("local_context_refs"))
        stop_conditions = _string_list(worker_task.get("stop_conditions"))
        for action_class in allowed_actions:
            seen_action_classes.add(action_class)
        task_summaries.append(
            {
                "task_id": _string_value(worker_task.get("task_id")),
                "hypothesis_id": _string_value(worker_task.get("hypothesis_id")),
                "task_scope": _string_value(worker_task.get("task_scope")),
                "allowed_action_count": len(allowed_actions),
                "local_context_ref_count": len(local_context_refs),
                "stop_condition_count": len(stop_conditions),
            }
        )

    return {
        "hypothesis_id": _string_value(raw.get("hypothesis_id")),
        "planner_strategy_id": _string_value(raw.get("planner_strategy_id")),
        "task_count": len(task_summaries),
        "action_class_count": len(seen_action_classes),
        "task_summaries": task_summaries,
    }
