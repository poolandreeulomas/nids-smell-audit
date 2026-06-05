"""Validation helpers for the Phase 3A Planner runtime."""

from __future__ import annotations

import re
from typing import Any

from planner.contracts import MAX_PLANNER_STRATEGIES


_FORBIDDEN_LANGUAGE_PATTERNS = {
    "reranking_language": re.compile(
        r"\bprioriti[sz](?:e|ed|ing|ation)?\b|\brank(?:ed|ing)?\b|\bbudget\b|\breallocate\b|\bdefer(?:red|ring)?\b|\breplace\b|\bdrop\b|\bsaturat(?:e|ed|ion)\b",
        re.IGNORECASE,
    ),
    "operational_packaging_language": re.compile(
        r"\bdispatch(?:ed|es|ing)?\b|\bpackage into\b|\bassign to\b|\bworker\s*\d+\b|\bexecutor\s*\d+\b|\btask_id\b|\bworker_task\b",
        re.IGNORECASE,
    ),
    "execution_language": re.compile(
        r"\bexecute(?:d|s|ing)?\b|\brun(?:ning)?\b the (?:tool|check|analysis)\b|\bparameter(?:s|ize|ized|ization)?\b",
        re.IGNORECASE,
    ),
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


def _collect_tool_name_hits(
    field_name: str,
    value: object,
    *,
    known_tool_capability_refs: set[str] | None = None,
) -> list[dict[str, str]]:
    if not isinstance(value, str) or not known_tool_capability_refs:
        return []
    normalized = value.lower()
    hits: list[dict[str, str]] = []
    for tool_name in sorted(known_tool_capability_refs):
        if tool_name.lower() in normalized:
            hits.append(
                {"field": field_name, "code": f"exact_tool_reference:{tool_name}"})
    return hits


def validate_ranking_decision_min(ranking_decision_min: dict[str, Any]) -> dict[str, Any]:
    raw = ranking_decision_min if isinstance(
        ranking_decision_min, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(ranking_decision_min, dict):
        errors.append(_error("ranking_decision_min",
                      "ranking_decision_min must be an object."))

    if not _is_non_empty_string(raw.get("batch_id")):
        errors.append(
            _error("batch_id", "batch_id must be a non-empty string."))

    if not _is_non_empty_string(raw.get("round_id")):
        errors.append(
            _error("round_id", "round_id must be a non-empty string."))

    selected_hypothesis_ids = raw.get("selected_hypothesis_ids")
    if not _is_string_list(selected_hypothesis_ids, allow_empty=False):
        errors.append(
            _error(
                "selected_hypothesis_ids",
                "selected_hypothesis_ids must be a non-empty list of strings.",
            )
        )
        selected_hypothesis_ids = []

    seen: set[str] = set()
    for hypothesis_id in selected_hypothesis_ids:
        if hypothesis_id in seen:
            errors.append(
                _error(
                    "selected_hypothesis_ids",
                    f"Duplicate selected hypothesis id '{hypothesis_id}'.",
                )
            )
        seen.add(hypothesis_id)

    if len(selected_hypothesis_ids) > MAX_PLANNER_STRATEGIES:
        errors.append(
            _error(
                "selected_hypothesis_ids",
                f"selected_hypothesis_ids may contain at most {MAX_PLANNER_STRATEGIES} entries.",
            )
        )

    return _report(
        ok=not errors,
        errors=errors,
        stats={"selected_count": len(selected_hypothesis_ids)},
    )


def validate_selected_hypothesis_context(
    selected_hypothesis_context: dict[str, Any],
    *,
    expected_selected_hypothesis_ids: list[str],
) -> dict[str, Any]:
    raw = selected_hypothesis_context if isinstance(
        selected_hypothesis_context, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(selected_hypothesis_context, dict):
        errors.append(
            _error(
                "selected_hypothesis_context",
                "selected_hypothesis_context must be an object.",
            )
        )

    selected_hypotheses = raw.get("selected_hypotheses")
    if not isinstance(selected_hypotheses, list) or not selected_hypotheses:
        errors.append(
            _error(
                "selected_hypotheses",
                "selected_hypotheses must be a non-empty list.",
            )
        )
        selected_hypotheses = []

    seen_ids: set[str] = set()
    for index, hypothesis in enumerate(selected_hypotheses):
        field_prefix = f"selected_hypotheses[{index}]"
        if not isinstance(hypothesis, dict):
            errors.append(
                _error(field_prefix, "Each selected hypothesis must be an object."))
            continue
        hypothesis_id = hypothesis.get("hypothesis_id")
        if not _is_non_empty_string(hypothesis_id):
            errors.append(_error(
                f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
            continue
        normalized_hypothesis_id = str(hypothesis_id).strip()
        if normalized_hypothesis_id in seen_ids:
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    f"Duplicate selected hypothesis '{normalized_hypothesis_id}'.",
                )
            )
        seen_ids.add(normalized_hypothesis_id)
        if normalized_hypothesis_id not in set(expected_selected_hypothesis_ids):
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    f"Unknown selected hypothesis '{normalized_hypothesis_id}'.",
                )
            )
        if not _is_non_empty_string(hypothesis.get("summary")):
            errors.append(_error(f"{field_prefix}.summary",
                          "summary must be a non-empty string."))
        if not _is_string_list(hypothesis.get("evidence_refs"), allow_empty=False):
            errors.append(
                _error(
                    f"{field_prefix}.evidence_refs",
                    "evidence_refs must be a non-empty list of strings.",
                )
            )
        if not _is_string_list(hypothesis.get("open_questions"), allow_empty=False):
            errors.append(
                _error(
                    f"{field_prefix}.open_questions",
                    "open_questions must be a non-empty list of strings.",
                )
            )
        if not _is_non_empty_string(hypothesis.get("current_status")):
            errors.append(
                _error(
                    f"{field_prefix}.current_status",
                    "current_status must be a non-empty string.",
                )
            )

    missing_ids = sorted(
        set(expected_selected_hypothesis_ids).difference(seen_ids))
    if missing_ids:
        errors.append(
            _error(
                "selected_hypotheses",
                "selected_hypothesis_context is missing selected hypotheses: " +
                ", ".join(missing_ids) + ".",
            )
        )

    return _report(
        ok=not errors,
        errors=errors,
        stats={
            "selected_count": len(selected_hypotheses),
            "expected_selected_count": len(expected_selected_hypothesis_ids),
        },
        invariants={
            "selected_ids_match": not missing_ids and len(seen_ids) == len(expected_selected_hypothesis_ids),
        },
    )


def validate_planner_round_context(
    planner_round_context: dict[str, Any],
    *,
    expected_round_id: str,
    known_tool_capability_refs: set[str] | None = None,
) -> dict[str, Any]:
    raw = planner_round_context if isinstance(
        planner_round_context, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(planner_round_context, dict):
        errors.append(_error("planner_round_context",
                      "planner_round_context must be an object."))

    round_id = raw.get("round_id")
    if not _is_non_empty_string(round_id):
        errors.append(
            _error("round_id", "round_id must be a non-empty string."))
    elif str(round_id).strip() != expected_round_id:
        errors.append(
            _error("round_id", f"round_id must match '{expected_round_id}'."))

    related_substrate_refs = raw.get("related_substrate_refs")
    if not _is_string_list(related_substrate_refs):
        errors.append(
            _error(
                "related_substrate_refs",
                "related_substrate_refs must be a list of strings.",
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
            errors.append(
                _error(
                    "tool_capability_refs",
                    f"Duplicate tool_capability_ref '{tool_ref}'.",
                )
            )
            continue
        seen_tool_refs.add(tool_ref)
        if known_tool_capability_refs and tool_ref not in known_tool_capability_refs:
            errors.append(
                _error(
                    "tool_capability_refs",
                    f"Unknown tool_capability_ref '{tool_ref}'.",
                )
            )

    round_constraints = raw.get("round_constraints")
    if not _is_string_list(round_constraints):
        errors.append(_error("round_constraints",
                      "round_constraints must be a list of strings."))
        round_constraints = []

    critic_guidance = raw.get("critic_guidance")
    if critic_guidance is not None and not _is_string_list(critic_guidance):
        errors.append(_error("critic_guidance",
                      "critic_guidance must be a list of strings."))

    return _report(
        ok=not errors,
        errors=errors,
        stats={
            "related_substrate_ref_count": len(related_substrate_refs),
            "tool_capability_ref_count": len(tool_capability_refs),
            "round_constraint_count": len(round_constraints),
        },
    )


def validate_planner_round_output(
    planner_round_output: dict[str, Any],
    *,
    selected_hypothesis_ids: list[str],
    expected_batch_id: str,
    expected_round_id: str,
    known_tool_capability_refs: set[str] | None = None,
) -> dict[str, Any]:
    raw = planner_round_output if isinstance(
        planner_round_output, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not isinstance(planner_round_output, dict):
        errors.append(_error("planner_round_output",
                      "planner_round_output must be an object."))

    batch_id = raw.get("batch_id")
    if not _is_non_empty_string(batch_id):
        errors.append(
            _error("batch_id", "batch_id must be a non-empty string."))
    elif str(batch_id).strip() != expected_batch_id:
        errors.append(
            _error("batch_id", f"batch_id must match '{expected_batch_id}'."))

    round_id = raw.get("round_id")
    if not _is_non_empty_string(round_id):
        errors.append(
            _error("round_id", "round_id must be a non-empty string."))
    elif str(round_id).strip() != expected_round_id:
        errors.append(
            _error("round_id", f"round_id must match '{expected_round_id}'."))

    planner_strategies = raw.get("planner_strategies")
    if not isinstance(planner_strategies, list) or not planner_strategies:
        errors.append(_error("planner_strategies",
                      "planner_strategies must be a non-empty list."))
        planner_strategies = []

    selected_set = set(selected_hypothesis_ids)
    seen_strategy_ids: set[str] = set()
    seen_hypothesis_ids: set[str] = set()

    for index, strategy in enumerate(planner_strategies):
        field_prefix = f"planner_strategies[{index}]"
        if not isinstance(strategy, dict):
            errors.append(
                _error(field_prefix, "Each planner strategy must be an object."))
            continue

        strategy_id = strategy.get("strategy_id")
        if not _is_non_empty_string(strategy_id):
            errors.append(_error(
                f"{field_prefix}.strategy_id", "strategy_id must be a non-empty string."))
        else:
            normalized_strategy_id = str(strategy_id).strip()
            if normalized_strategy_id in seen_strategy_ids:
                errors.append(
                    _error(
                        f"{field_prefix}.strategy_id",
                        f"Duplicate strategy_id '{normalized_strategy_id}'.",
                    )
                )
            seen_strategy_ids.add(normalized_strategy_id)

        hypothesis_id = strategy.get("hypothesis_id")
        if not _is_non_empty_string(hypothesis_id):
            errors.append(_error(
                f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
            continue

        normalized_hypothesis_id = str(hypothesis_id).strip()
        if normalized_hypothesis_id in seen_hypothesis_ids:
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    f"Duplicate strategy for hypothesis '{normalized_hypothesis_id}'.",
                )
            )
        seen_hypothesis_ids.add(normalized_hypothesis_id)
        if normalized_hypothesis_id not in selected_set:
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    f"Unknown selected hypothesis '{normalized_hypothesis_id}'.",
                )
            )

        strategic_objective = strategy.get("strategic_objective")
        if not _is_non_empty_string(strategic_objective):
            errors.append(
                _error(
                    f"{field_prefix}.strategic_objective",
                    "strategic_objective must be a non-empty string.",
                )
            )
        else:
            normalized_objective = str(strategic_objective).strip()
            if len(normalized_objective) > 280:
                errors.append(
                    _error(
                        f"{field_prefix}.strategic_objective",
                        "strategic_objective must stay under 280 characters.",
                    )
                )
            forbidden_language_hits.extend(
                _collect_forbidden_language(
                    f"{field_prefix}.strategic_objective", normalized_objective)
            )
            forbidden_language_hits.extend(
                _collect_tool_name_hits(
                    f"{field_prefix}.strategic_objective",
                    normalized_objective,
                    known_tool_capability_refs=known_tool_capability_refs,
                )
            )

        for key in ("key_checks", "success_criteria", "router_constraints"):
            values = strategy.get(key)
            if not _is_string_list(values, allow_empty=False):
                errors.append(
                    _error(
                        f"{field_prefix}.{key}",
                        f"{key} must be a non-empty list of strings.",
                    )
                )
                continue
            if len(values) > 6:
                errors.append(
                    _error(
                        f"{field_prefix}.{key}",
                        f"{key} must contain at most 6 items.",
                    )
                )
            for item_index, value in enumerate(values):
                normalized_value = str(value).strip()
                if len(normalized_value) > 240:
                    errors.append(
                        _error(
                            f"{field_prefix}.{key}[{item_index}]",
                            f"{key} entries must stay under 240 characters.",
                        )
                    )
                forbidden_language_hits.extend(
                    _collect_forbidden_language(
                        f"{field_prefix}.{key}[{item_index}]", normalized_value)
                )
                forbidden_language_hits.extend(
                    _collect_tool_name_hits(
                        f"{field_prefix}.{key}[{item_index}]",
                        normalized_value,
                        known_tool_capability_refs=known_tool_capability_refs,
                    )
                )

    missing_strategy_ids = sorted(selected_set.difference(seen_hypothesis_ids))
    if missing_strategy_ids:
        errors.append(
            _error(
                "planner_strategies",
                "Missing planner strategies for selected hypotheses: " +
                ", ".join(missing_strategy_ids) + ".",
            )
        )

    if len(planner_strategies) != len(selected_hypothesis_ids):
        errors.append(
            _error(
                "planner_strategies",
                "planner_strategies must contain exactly one strategy per selected hypothesis.",
            )
        )

    for hit in forbidden_language_hits:
        warnings.append(
            _error(hit["field"], f"Semantic language flag detected ({hit['code']})."))

    stats = {
        "selected_count": len(selected_hypothesis_ids),
        "strategy_count": len(planner_strategies),
        "missing_strategy_count": len(missing_strategy_ids),
    }
    invariants = {
        "one_strategy_per_selected_hypothesis": len(planner_strategies) == len(selected_hypothesis_ids) and not missing_strategy_ids,
        "selected_ids_known": all(hypothesis_id in selected_set for hypothesis_id in seen_hypothesis_ids),
    }

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats=stats,
        invariants=invariants,
        forbidden_language_hits=forbidden_language_hits,
    )
