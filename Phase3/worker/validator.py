"""Validation helpers for the Phase 3A Worker runtime."""

from __future__ import annotations

import re
from typing import Any

from investigation_analysis.substrate_loader import collect_valid_evidence_ids
from worker.contracts import DEFAULT_MAX_RETRIES, DEFAULT_MAX_WORKER_STEPS, VALID_WORKER_STATUSES


_WORKER_TASK_FIELDS = {
    "task_id",
    "hypothesis_id",
    "task_scope",
    "allowed_actions",
    "local_context_refs",
    "stop_conditions",
}
_WORKER_RUNTIME_REF_FIELDS = {
    "tool_handles",
    "dataset_handles",
    "budget_rules",
}
_DATASET_HANDLE_FIELDS = {
    "dataset_path",
    "semantic_substrate",
}
_LOCAL_CONTEXT_RECORD_FIELDS = {
    "context_ref",
    "feature_names",
    "feature_groups",
    "locality",
    "source_items",
}
_ACTION_FIELDS = {
    "action_class",
    "context_ref",
    "feature_name",
    "related_feature_name",
}
_WORKER_RESULT_FIELDS = {
    "task_id",
    "hypothesis_id",
    "status",
    "findings",
    "evidence_refs",
    "contradictions",
    "limitations",
}
_FORBIDDEN_SCOPE_PATTERNS = {
    "planning_language": re.compile(r"\bplan(?:ning|ned|s)?\b|\bstrategy\b|\breplan(?:ning|ned|s)?\b", re.IGNORECASE),
    "ranking_language": re.compile(r"\brank(?:ed|ing)?\b|\bprioriti[sz](?:e|ed|ing)?\b|\bselection\b", re.IGNORECASE),
    "aggregation_language": re.compile(r"\baggregate(?:d|ion|ing)?\b|\bmerge(?:d|ing)?\b|\bcross-worker\b", re.IGNORECASE),
}


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _report(
    *,
    ok: bool,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings or [],
    }
    if stats is not None:
        payload["stats"] = stats
    return payload


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_string_list(value: object, *, allow_empty: bool = True) -> bool:
    if not isinstance(value, list):
        return False
    if not allow_empty and not value:
        return False
    return all(_is_non_empty_string(item) for item in value)


def validate_worker_task(
    worker_task: dict[str, Any],
    *,
    known_action_classes: set[str],
) -> dict[str, Any]:
    raw = worker_task if isinstance(worker_task, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(worker_task, dict):
        errors.append(_error("worker_task", "worker_task must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _WORKER_TASK_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "worker_task",
                f"worker_task contains unsupported fields: {unsupported_fields}.",
            )
        )

    for key in ("task_id", "hypothesis_id", "task_scope"):
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(key, f"{key} must be a non-empty string."))

    task_scope = raw.get("task_scope")
    if isinstance(task_scope, str):
        for pattern_name, pattern in _FORBIDDEN_SCOPE_PATTERNS.items():
            if pattern.search(task_scope):
                warnings.append(
                    _error("task_scope", f"Semantic language flag detected ({pattern_name})."))

    allowed_actions = raw.get("allowed_actions")
    if not _is_string_list(allowed_actions, allow_empty=False):
        errors.append(_error("allowed_actions",
                      "allowed_actions must be a non-empty list of strings."))
        allowed_actions = []
    else:
        seen_actions: set[str] = set()
        for action_class in allowed_actions:
            if action_class in seen_actions:
                errors.append(_error("allowed_actions",
                              f"Duplicate allowed action '{action_class}'."))
                continue
            seen_actions.add(action_class)
            if action_class not in known_action_classes:
                errors.append(_error("allowed_actions",
                              f"Unknown allowed action '{action_class}'."))

    local_context_refs = raw.get("local_context_refs")
    if not _is_string_list(local_context_refs, allow_empty=False):
        errors.append(_error("local_context_refs",
                      "local_context_refs must be a non-empty list of strings."))
        local_context_refs = []

    stop_conditions = raw.get("stop_conditions")
    if not _is_string_list(stop_conditions, allow_empty=False):
        errors.append(_error("stop_conditions",
                      "stop_conditions must be a non-empty list of strings."))
        stop_conditions = []

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "allowed_action_count": len(allowed_actions),
            "local_context_ref_count": len(local_context_refs),
            "stop_condition_count": len(stop_conditions),
        },
    )


def validate_worker_runtime_refs(
    worker_runtime_refs: dict[str, Any],
    *,
    expected_local_context_refs: set[str],
) -> dict[str, Any]:
    raw = worker_runtime_refs if isinstance(worker_runtime_refs, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(worker_runtime_refs, dict):
        errors.append(_error("worker_runtime_refs",
                      "worker_runtime_refs must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _WORKER_RUNTIME_REF_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "worker_runtime_refs",
                f"worker_runtime_refs contains unsupported fields: {unsupported_fields}.",
            )
        )

    tool_handles = raw.get("tool_handles")
    if not isinstance(tool_handles, dict):
        errors.append(
            _error("tool_handles", "tool_handles must be an object."))

    dataset_handles = raw.get("dataset_handles")
    if not isinstance(dataset_handles, dict):
        errors.append(_error("dataset_handles",
                      "dataset_handles must be an object."))
        dataset_handles = {}
    else:
        unsupported_dataset_handle_fields = sorted(
            set(dataset_handles.keys()) - _DATASET_HANDLE_FIELDS)
        if unsupported_dataset_handle_fields:
            errors.append(
                _error(
                    "dataset_handles",
                    f"dataset_handles contains unsupported fields: {unsupported_dataset_handle_fields}.",
                )
            )

    dataset_path = dataset_handles.get("dataset_path")
    if not _is_non_empty_string(dataset_path):
        errors.append(_error("dataset_handles.dataset_path",
                      "dataset_path must be a non-empty string."))

    semantic_substrate = dataset_handles.get("semantic_substrate")
    if not isinstance(semantic_substrate, dict):
        errors.append(
            _error(
                "dataset_handles.semantic_substrate",
                "semantic_substrate must be an object sourced from Investigation Analysis.",
            )
        )
        semantic_substrate = {}

    available_context_refs = collect_valid_evidence_ids(semantic_substrate)
    missing_context_refs = sorted(
        expected_local_context_refs - available_context_refs)
    if missing_context_refs:
        errors.append(
            _error(
                "dataset_handles.semantic_substrate",
                f"semantic_substrate is missing local_context_refs: {missing_context_refs}.",
            )
        )

    budget_rules = raw.get("budget_rules")
    if not isinstance(budget_rules, dict):
        errors.append(
            _error("budget_rules", "budget_rules must be an object."))
        budget_rules = {}

    max_steps = budget_rules.get("max_steps")
    if not isinstance(max_steps, int) or max_steps <= 0 or max_steps > DEFAULT_MAX_WORKER_STEPS:
        errors.append(
            _error(
                "budget_rules.max_steps",
                f"max_steps must be an integer between 1 and {DEFAULT_MAX_WORKER_STEPS}.",
            )
        )

    max_retries = budget_rules.get("max_retries")
    if not isinstance(max_retries, int) or max_retries < 0 or max_retries > DEFAULT_MAX_RETRIES:
        errors.append(
            _error(
                "budget_rules.max_retries",
                f"max_retries must be an integer between 0 and {DEFAULT_MAX_RETRIES}.",
            )
        )

    return _report(
        ok=not errors,
        errors=errors,
        stats={
            "expected_local_context_count": len(expected_local_context_refs),
            "available_context_count": len(available_context_refs),
        },
    )


def validate_worker_step_decision(
    parsed_step: dict[str, Any],
    *,
    allowed_actions: set[str],
    known_context_refs: set[str],
    allowed_decisions: set[str] | None = None,
    require_reasoning: bool = False,
) -> dict[str, Any]:
    raw = parsed_step if isinstance(parsed_step, dict) else {}
    errors: list[dict[str, str]] = []

    decision = raw.get("decision")
    admitted_decisions = set(allowed_decisions or {
                             "continue", "action", "finish"})
    if decision not in admitted_decisions:
        errors.append(
            _error("decision", f"decision must be one of {sorted(admitted_decisions)}."))
        return _report(ok=False, errors=errors)

    if require_reasoning and not _is_non_empty_string(raw.get("reasoning")):
        errors.append(_error(
            "reasoning", "reasoning must be a non-empty string for this worker step."))

    if decision == "continue":
        if set(raw.keys()) != {"decision", "reasoning"}:
            errors.append(_error(
                "reasoning", "Continue decisions must contain exactly 'decision' and 'reasoning'."))
        return _report(ok=not errors, errors=errors)

    def _validate_action(action: dict[str, Any], field_prefix: str) -> None:
        unsupported_action_fields = sorted(set(action.keys()) - _ACTION_FIELDS)
        if unsupported_action_fields:
            errors.append(
                _error(
                    field_prefix,
                    f"action contains unsupported fields: {unsupported_action_fields}.",
                )
            )
        action_class = action.get("action_class")
        context_ref = action.get("context_ref")
        feature_name = action.get("feature_name")
        related_feature_name = action.get("related_feature_name")

        if not _is_non_empty_string(action_class):
            errors.append(_error(
                f"{field_prefix}.action_class", "action_class must be a non-empty string."))
        elif action_class not in allowed_actions:
            errors.append(_error(f"{field_prefix}.action_class",
                          f"action_class '{action_class}' is not allowed for this task."))

        if not _is_non_empty_string(context_ref):
            errors.append(_error(
                f"{field_prefix}.context_ref", "context_ref must be a non-empty string."))
        elif context_ref not in known_context_refs:
            errors.append(
                _error(f"{field_prefix}.context_ref", f"Unknown context_ref '{context_ref}'."))

        if action_class != "duplication_verification" and not _is_non_empty_string(feature_name):
            errors.append(_error(f"{field_prefix}.feature_name",
                          "feature_name must be a non-empty string for the selected action."))
        if related_feature_name is not None and not _is_non_empty_string(related_feature_name):
            errors.append(_error(f"{field_prefix}.related_feature_name",
                          "related_feature_name must be a non-empty string when provided."))

    if decision == "action":
        allowed_key_sets = [
            {"decision", "actions"},
            {"decision", "reasoning", "actions"},
        ]
        if set(raw.keys()) not in allowed_key_sets:
            errors.append(_error(
                "actions", "Action decisions must contain 'decision', optional 'reasoning', and 'actions'."))
        actions = raw.get("actions") if isinstance(
            raw.get("actions"), list) else []
        if not actions:
            errors.append(
                _error("actions", "Action decisions must include a non-empty 'actions' list."))
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                errors.append(
                    _error(f"actions[{index}]", "Each action must be an object."))
                continue
            _validate_action(action, f"actions[{index}]")

    if decision == "finish":
        allowed_key_sets = [
            {"decision", "worker_result"},
            {"decision", "reasoning", "worker_result"},
        ]
        if set(raw.keys()) not in allowed_key_sets:
            errors.append(_error(
                "worker_result", "Finish decisions must contain 'decision', optional 'reasoning', and 'worker_result'."))

    return _report(ok=not errors, errors=errors)


def validate_worker_result(
    worker_result: dict[str, Any],
    *,
    expected_task_id: str,
    expected_hypothesis_id: str,
    known_evidence_refs: set[str],
) -> dict[str, Any]:
    raw = worker_result if isinstance(worker_result, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(worker_result, dict):
        errors.append(
            _error("worker_result", "worker_result must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _WORKER_RESULT_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "worker_result",
                f"worker_result contains unsupported fields: {unsupported_fields}.",
            )
        )

    task_id = raw.get("task_id")
    if not _is_non_empty_string(task_id):
        errors.append(_error("task_id", "task_id must be a non-empty string."))
    elif task_id != expected_task_id:
        errors.append(
            _error("task_id", f"task_id must match '{expected_task_id}'."))

    hypothesis_id = raw.get("hypothesis_id")
    if not _is_non_empty_string(hypothesis_id):
        errors.append(
            _error("hypothesis_id", "hypothesis_id must be a non-empty string."))
    elif hypothesis_id != expected_hypothesis_id:
        errors.append(_error("hypothesis_id",
                      f"hypothesis_id must match '{expected_hypothesis_id}'."))

    status = raw.get("status")
    if status not in VALID_WORKER_STATUSES:
        errors.append(
            _error("status", f"status must be one of {sorted(VALID_WORKER_STATUSES)}."))

    findings = raw.get("findings")
    if not _is_string_list(findings):
        errors.append(
            _error("findings", "findings must be a list of strings."))
        findings = []

    evidence_refs = raw.get("evidence_refs")
    if not _is_string_list(evidence_refs):
        errors.append(
            _error("evidence_refs", "evidence_refs must be a list of strings."))
        evidence_refs = []
    else:
        for evidence_ref in evidence_refs:
            if evidence_ref not in known_evidence_refs:
                errors.append(
                    _error("evidence_refs", f"Unknown evidence_ref '{evidence_ref}'."))

    contradictions = raw.get("contradictions")
    if not _is_string_list(contradictions):
        errors.append(
            _error("contradictions", "contradictions must be a list of strings."))
        contradictions = []

    limitations = raw.get("limitations")
    if not _is_string_list(limitations):
        errors.append(
            _error("limitations", "limitations must be a list of strings."))
        limitations = []

    if status in {"completed", "partial"} and not findings:
        errors.append(_error(
            "findings", f"status '{status}' requires at least one grounded finding."))
    if status in {"completed", "partial"} and not evidence_refs:
        errors.append(_error(
            "evidence_refs", f"status '{status}' requires at least one evidence reference."))
    if status == "failed" and not limitations:
        errors.append(_error(
            "limitations", "failed worker_result must explain at least one limitation."))
    if status == "inconclusive" and not evidence_refs:
        warnings.append(_error(
            "evidence_refs", "inconclusive worker_result has no evidence references."))

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "finding_count": len(findings),
            "evidence_ref_count": len(evidence_refs),
            "contradiction_count": len(contradictions),
            "limitation_count": len(limitations),
        },
    )


def validate_worker_output(
    worker_output: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
) -> dict[str, Any]:
    raw = worker_output if isinstance(worker_output, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(worker_output, dict):
        errors.append(
            _error("worker_output", "worker_output must be an object."))

    batch_id = raw.get("batch_id")
    if not _is_non_empty_string(batch_id):
        errors.append(
            _error("batch_id", "batch_id must be a non-empty string."))
    elif batch_id != expected_batch_id:
        errors.append(
            _error("batch_id", f"batch_id must match '{expected_batch_id}'."))

    round_id = raw.get("round_id")
    if not _is_non_empty_string(round_id):
        errors.append(
            _error("round_id", "round_id must be a non-empty string."))
    elif round_id != expected_round_id:
        errors.append(
            _error("round_id", f"round_id must match '{expected_round_id}'."))

    if not isinstance(raw.get("worker_result"), dict):
        errors.append(
            _error("worker_result", "worker_output.worker_result must be an object."))

    return _report(ok=not errors, errors=errors)
