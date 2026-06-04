"""Validation helpers for the Phase 3A Router runtime."""

from __future__ import annotations

import re
from typing import Any


_FORBIDDEN_LANGUAGE_PATTERNS = {
    "ranking_language": re.compile(
        r"\bprioriti[sz](?:e|ed|ing|ation)?\b|\brank(?:ed|ing)?\b|\bbudget reallocation\b|\bdefer(?:red|ring)?\b|\bselected set\b",
        re.IGNORECASE,
    ),
    "planning_language": re.compile(
        r"\bplan(?:ning|ned|s)?\b|\breplan(?:ning|ned|s)?\b|\bstrategy\b|\bverification minimum(?:s)?\b",
        re.IGNORECASE,
    ),
    "execution_scripting_language": re.compile(
        r"\bfirst use\b|\bthen use\b|\bcall\b\s+\w+|\bexact parameter(?:s|ization)?\b|\bstep by step\b",
        re.IGNORECASE,
    ),
}

_WORKER_TASK_FIELDS = {
    "task_id",
    "hypothesis_id",
    "task_scope",
    "allowed_actions",
    "local_context_refs",
    "stop_conditions",
}


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _report(
    *,
    ok: bool,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
    stats: dict[str, Any] | None = None,
    invariants: dict[str, Any] | None = None,
    forbidden_language_hits: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings or [],
    }
    if stats is not None:
        payload["stats"] = stats
    if invariants is not None:
        payload["invariants"] = invariants
    if forbidden_language_hits is not None:
        payload["forbidden_language_hits"] = forbidden_language_hits
    return payload


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_string_list(value: object, *, allow_empty: bool = True) -> bool:
    if not isinstance(value, list):
        return False
    if not allow_empty and not value:
        return False
    return all(_is_non_empty_string(item) for item in value)


def _collect_forbidden_language(field_name: str, value: object) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return []
    hits: list[dict[str, str]] = []
    for code, pattern in _FORBIDDEN_LANGUAGE_PATTERNS.items():
        if pattern.search(value):
            hits.append({"field": field_name, "code": code})
    return hits


def _collect_exact_tool_name_hits(
    field_name: str,
    value: object,
    *,
    known_tool_capability_refs: set[str],
) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return []
    normalized = value.lower()
    hits: list[dict[str, str]] = []
    for tool_name in sorted(known_tool_capability_refs):
        if tool_name.lower() in normalized:
            hits.append({"field": field_name, "code": f"exact_tool_reference:{tool_name}"})
    return hits


def validate_router_context_min(
    router_context_min: dict[str, Any],
    *,
    known_tool_capability_refs: set[str],
) -> dict[str, Any]:
    raw = router_context_min if isinstance(router_context_min, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(router_context_min, dict):
        errors.append(_error("router_context_min", "router_context_min must be an object."))

    related_substrate_refs = raw.get("related_substrate_refs")
    if not _is_string_list(related_substrate_refs, allow_empty=False):
        errors.append(
            _error(
                "related_substrate_refs",
                "related_substrate_refs must be a non-empty list of strings.",
            )
        )
        related_substrate_refs = []

    tool_capability_refs = raw.get("tool_capability_refs")
    if not _is_string_list(tool_capability_refs, allow_empty=False):
        errors.append(
            _error(
                "tool_capability_refs",
                "tool_capability_refs must be a non-empty list of strings.",
            )
        )
        tool_capability_refs = []

    seen_tool_refs: set[str] = set()
    for tool_ref in tool_capability_refs:
        if tool_ref in seen_tool_refs:
            errors.append(_error("tool_capability_refs", f"Duplicate tool_capability_ref '{tool_ref}'."))
            continue
        seen_tool_refs.add(tool_ref)
        if tool_ref not in known_tool_capability_refs:
            errors.append(_error("tool_capability_refs", f"Unknown tool_capability_ref '{tool_ref}'."))

    execution_budget = raw.get("execution_budget")
    if not isinstance(execution_budget, dict):
        errors.append(_error("execution_budget", "execution_budget must be an object."))
        execution_budget = {}
    for key in ("max_worker_steps", "max_tasks", "max_retries"):
        value = execution_budget.get(key)
        if not isinstance(value, int):
            errors.append(_error(f"execution_budget.{key}", f"{key} must be an integer."))
            continue
        if key == "max_retries":
            if value < 0:
                errors.append(_error(f"execution_budget.{key}", f"{key} must be zero or greater."))
        elif value <= 0:
            errors.append(_error(f"execution_budget.{key}", f"{key} must be greater than zero."))

    guardrails = raw.get("guardrails")
    if not _is_string_list(guardrails, allow_empty=False):
        errors.append(_error("guardrails", "guardrails must be a non-empty list of strings."))
        guardrails = []

    return _report(
        ok=not errors,
        errors=errors,
        stats={
            "related_substrate_ref_count": len(related_substrate_refs),
            "tool_capability_ref_count": len(tool_capability_refs),
            "guardrail_count": len(guardrails),
        },
    )


def validate_router_output(
    router_output: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
    expected_hypothesis_id: str,
    expected_planner_strategy_id: str,
    allowed_action_classes: set[str],
    known_context_refs: set[str],
    max_tasks: int,
    known_tool_capability_refs: set[str],
) -> dict[str, Any]:
    raw = router_output if isinstance(router_output, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not isinstance(router_output, dict):
        errors.append(_error("router_output", "router_output must be an object."))

    for key, expected_value in (
        ("batch_id", expected_batch_id),
        ("round_id", expected_round_id),
        ("hypothesis_id", expected_hypothesis_id),
        ("planner_strategy_id", expected_planner_strategy_id),
    ):
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(key, f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(key, f"{key} must match '{expected_value}'."))

    worker_tasks = raw.get("worker_tasks")
    if not isinstance(worker_tasks, list) or not worker_tasks:
        errors.append(_error("worker_tasks", "worker_tasks must be a non-empty list."))
        worker_tasks = []

    if len(worker_tasks) > max_tasks:
        errors.append(_error("worker_tasks", f"worker_tasks may contain at most {max_tasks} tasks."))
    elif len(worker_tasks) == max_tasks:
        warnings.append(_error("worker_tasks", "worker_tasks reached the configured max_tasks budget."))

    seen_task_ids: set[str] = set()
    seen_context_ref_pairs: set[tuple[str, ...]] = set()
    used_action_classes: set[str] = set()

    for index, worker_task in enumerate(worker_tasks):
        field_prefix = f"worker_tasks[{index}]"
        if not isinstance(worker_task, dict):
            errors.append(_error(field_prefix, "Each worker_task must be an object."))
            continue

        extra_fields = sorted(set(worker_task.keys()) - _WORKER_TASK_FIELDS)
        if extra_fields:
            errors.append(
                _error(
                    field_prefix,
                    "worker_task contains unsupported fields: " + ", ".join(extra_fields) + ".",
                )
            )

        task_id = worker_task.get("task_id")
        if not _is_non_empty_string(task_id):
            errors.append(_error(f"{field_prefix}.task_id", "task_id must be a non-empty string."))
        else:
            normalized_task_id = str(task_id).strip()
            if normalized_task_id in seen_task_ids:
                errors.append(_error(f"{field_prefix}.task_id", f"Duplicate task_id '{normalized_task_id}'."))
            seen_task_ids.add(normalized_task_id)

        hypothesis_id = worker_task.get("hypothesis_id")
        if not _is_non_empty_string(hypothesis_id):
            errors.append(_error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
        elif str(hypothesis_id).strip() != expected_hypothesis_id:
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    f"hypothesis_id must match '{expected_hypothesis_id}'.",
                )
            )

        task_scope = worker_task.get("task_scope")
        if not _is_non_empty_string(task_scope):
            errors.append(_error(f"{field_prefix}.task_scope", "task_scope must be a non-empty string."))
        else:
            normalized_task_scope = str(task_scope).strip()
            if len(normalized_task_scope) > 280:
                errors.append(_error(f"{field_prefix}.task_scope", "task_scope must stay under 280 characters."))
            forbidden_language_hits.extend(_collect_forbidden_language(f"{field_prefix}.task_scope", normalized_task_scope))
            forbidden_language_hits.extend(
                _collect_exact_tool_name_hits(
                    f"{field_prefix}.task_scope",
                    normalized_task_scope,
                    known_tool_capability_refs=known_tool_capability_refs,
                )
            )

        allowed_actions = worker_task.get("allowed_actions")
        if not _is_string_list(allowed_actions, allow_empty=False):
            errors.append(
                _error(
                    f"{field_prefix}.allowed_actions",
                    "allowed_actions must be a non-empty list of strings.",
                )
            )
            allowed_actions = []

        seen_actions: set[str] = set()
        for action_index, action_class in enumerate(allowed_actions):
            if action_class in seen_actions:
                errors.append(
                    _error(
                        f"{field_prefix}.allowed_actions[{action_index}]",
                        f"Duplicate allowed_action '{action_class}'.",
                    )
                )
            seen_actions.add(action_class)
            used_action_classes.add(action_class)
            if action_class not in allowed_action_classes:
                errors.append(
                    _error(
                        f"{field_prefix}.allowed_actions[{action_index}]",
                        f"Unknown allowed_action '{action_class}'.",
                    )
                )

        local_context_refs = worker_task.get("local_context_refs")
        if not _is_string_list(local_context_refs, allow_empty=False):
            errors.append(
                _error(
                    f"{field_prefix}.local_context_refs",
                    "local_context_refs must be a non-empty list of strings.",
                )
            )
            local_context_refs = []

        normalized_context_refs = tuple(sorted(str(value).strip() for value in local_context_refs))
        if normalized_context_refs in seen_context_ref_pairs:
            warnings.append(
                _error(
                    f"{field_prefix}.local_context_refs",
                    "worker_task reuses an identical local_context_refs slice.",
                )
            )
        seen_context_ref_pairs.add(normalized_context_refs)

        for context_index, context_ref in enumerate(local_context_refs):
            if context_ref not in known_context_refs:
                errors.append(
                    _error(
                        f"{field_prefix}.local_context_refs[{context_index}]",
                        f"Unknown local_context_ref '{context_ref}'.",
                    )
                )

        stop_conditions = worker_task.get("stop_conditions")
        if not _is_string_list(stop_conditions, allow_empty=False):
            errors.append(
                _error(
                    f"{field_prefix}.stop_conditions",
                    "stop_conditions must be a non-empty list of strings.",
                )
            )
            stop_conditions = []

        for stop_index, stop_condition in enumerate(stop_conditions):
            normalized_stop_condition = str(stop_condition).strip()
            if len(normalized_stop_condition) > 220:
                errors.append(
                    _error(
                        f"{field_prefix}.stop_conditions[{stop_index}]",
                        "stop_conditions entries must stay under 220 characters.",
                    )
                )
            forbidden_language_hits.extend(
                _collect_forbidden_language(
                    f"{field_prefix}.stop_conditions[{stop_index}]",
                    normalized_stop_condition,
                )
            )
            forbidden_language_hits.extend(
                _collect_exact_tool_name_hits(
                    f"{field_prefix}.stop_conditions[{stop_index}]",
                    normalized_stop_condition,
                    known_tool_capability_refs=known_tool_capability_refs,
                )
            )

    if allowed_action_classes and not used_action_classes:
        warnings.append(_error("worker_tasks", "No allowed action classes were used by the routed bundle."))

    for hit in forbidden_language_hits:
        warnings.append(_error(hit["field"], f"Semantic language flag detected ({hit['code']})."))

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "task_count": len(worker_tasks),
            "allowed_action_class_count": len(used_action_classes),
            "context_ref_count": len(known_context_refs),
            "max_tasks": max_tasks,
        },
        invariants={
            "tasks_within_budget": len(worker_tasks) <= max_tasks,
            "all_tasks_match_hypothesis": all(
                isinstance(worker_task, dict)
                and str(worker_task.get("hypothesis_id", "")).strip() == expected_hypothesis_id
                for worker_task in worker_tasks
            ),
        },
        forbidden_language_hits=forbidden_language_hits,
    )