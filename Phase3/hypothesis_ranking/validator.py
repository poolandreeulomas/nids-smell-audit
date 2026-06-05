"""Validation helpers for the Phase 3A Hypothesis Ranking runtime."""

from __future__ import annotations

import re
from typing import Any

from hypothesis_ranking.contracts import MAX_SELECTION_BUDGET


_FORBIDDEN_LANGUAGE_PATTERNS = {
    "planning_language": re.compile(
        r"\bplan(?:ning|ned|s)?\b|\bstrategy\b|\bwork package\b|\btask package\b",
        re.IGNORECASE,
    ),
    "routing_language": re.compile(
        r"\broute(?:d|s|ing)?\b|\brouter\b|\bworker\b|\bexecutor\b",
        re.IGNORECASE,
    ),
    "execution_language": re.compile(
        r"\bexecute(?:d|s|ing)?\b|\brun(?:ning)?\b the (?:tool|check|worker)\b|\buse the tool\b",
        re.IGNORECASE,
    ),
    "next_step_language": re.compile(
        r"\bnext step\b|\bfirst investigate\b|\bshould investigate next\b|\bstart with\b",
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


def validate_ranking_state_min(ranking_state_min: dict[str, Any]) -> dict[str, Any]:
    raw = ranking_state_min if isinstance(ranking_state_min, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(ranking_state_min, dict):
        errors.append(_error("ranking_state_min",
                      "ranking_state_min must be an object."))

    if not _is_non_empty_string(raw.get("round_id")):
        errors.append(
            _error("round_id", "round_id must be a non-empty string."))

    selection_budget = raw.get("selection_budget")
    if not isinstance(selection_budget, int):
        errors.append(_error("selection_budget",
                      "selection_budget must be an integer."))
        selection_budget = 0
    elif selection_budget <= 0 or selection_budget > MAX_SELECTION_BUDGET:
        errors.append(
            _error(
                "selection_budget",
                f"selection_budget must be between 1 and {MAX_SELECTION_BUDGET}.",
            )
        )

    hypothesis_state_refs = raw.get("hypothesis_state_refs")
    if not isinstance(hypothesis_state_refs, list) or not hypothesis_state_refs:
        errors.append(_error("hypothesis_state_refs",
                      "hypothesis_state_refs must be a non-empty list."))
        hypothesis_state_refs = []

    for index, state_ref in enumerate(hypothesis_state_refs):
        field_prefix = f"hypothesis_state_refs[{index}]"
        if not isinstance(state_ref, dict):
            errors.append(
                _error(field_prefix, "Each hypothesis_state_ref must be an object."))
            continue
        if not _is_non_empty_string(state_ref.get("hypothesis_id")):
            errors.append(
                _error(f"{field_prefix}.hypothesis_id",
                       "hypothesis_id must be a non-empty string.")
            )
        if not _is_string_list(state_ref.get("state_notes")):
            errors.append(
                _error(f"{field_prefix}.state_notes", "state_notes must be a list of strings."))

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
            "selection_budget": selection_budget,
            "hypothesis_state_ref_count": len(hypothesis_state_refs),
            "round_constraint_count": len(round_constraints),
        },
    )


def validate_ranking_decision(
    ranking_decision: dict[str, Any],
    *,
    candidate_hypothesis_ids: set[str],
    expected_batch_id: str,
    expected_round_id: str,
    selection_budget: int,
) -> dict[str, Any]:
    raw = ranking_decision if isinstance(ranking_decision, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not isinstance(ranking_decision, dict):
        errors.append(_error("ranking_decision",
                      "ranking_decision must be an object."))

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

    selected_hypothesis_ids = raw.get("selected_hypothesis_ids")
    if not _is_string_list(selected_hypothesis_ids, allow_empty=False):
        errors.append(
            _error(
                "selected_hypothesis_ids",
                "selected_hypothesis_ids must be a non-empty list of strings.",
            )
        )
        selected_hypothesis_ids = []

    deferred_hypothesis_ids = raw.get("deferred_hypothesis_ids")
    if not _is_string_list(deferred_hypothesis_ids):
        errors.append(
            _error(
                "deferred_hypothesis_ids",
                "deferred_hypothesis_ids must be a list of strings.",
            )
        )
        deferred_hypothesis_ids = []

    if len(selected_hypothesis_ids) > selection_budget:
        errors.append(
            _error(
                "selected_hypothesis_ids",
                f"selected_hypothesis_ids may contain at most {selection_budget} entries.",
            )
        )

    seen_selected: set[str] = set()
    for hypothesis_id in selected_hypothesis_ids:
        if hypothesis_id in seen_selected:
            errors.append(
                _error(
                    "selected_hypothesis_ids",
                    f"Duplicate selected hypothesis id '{hypothesis_id}'.",
                )
            )
        seen_selected.add(hypothesis_id)
        if hypothesis_id not in candidate_hypothesis_ids:
            errors.append(
                _error(
                    "selected_hypothesis_ids",
                    f"Unknown selected hypothesis id '{hypothesis_id}'.",
                )
            )

    seen_deferred: set[str] = set()
    for hypothesis_id in deferred_hypothesis_ids:
        if hypothesis_id in seen_deferred:
            errors.append(
                _error(
                    "deferred_hypothesis_ids",
                    f"Duplicate deferred hypothesis id '{hypothesis_id}'.",
                )
            )
        seen_deferred.add(hypothesis_id)
        if hypothesis_id not in candidate_hypothesis_ids:
            errors.append(
                _error(
                    "deferred_hypothesis_ids",
                    f"Unknown deferred hypothesis id '{hypothesis_id}'.",
                )
            )

    overlap = set(selected_hypothesis_ids).intersection(
        deferred_hypothesis_ids)
    if overlap:
        errors.append(
            _error(
                "deferred_hypothesis_ids",
                f"Selected hypotheses may not also be deferred: {', '.join(sorted(overlap))}.",
            )
        )

    accounted_for = set(selected_hypothesis_ids).union(deferred_hypothesis_ids)
    missing_candidate_ids = sorted(
        candidate_hypothesis_ids.difference(accounted_for))
    if missing_candidate_ids:
        errors.append(
            _error(
                "deferred_hypothesis_ids",
                "Every non-selected candidate must be preserved in deferred_hypothesis_ids: "
                + ", ".join(missing_candidate_ids)
                + ".",
            )
        )

    selection_rationales = raw.get("selection_rationales")
    if not isinstance(selection_rationales, list):
        errors.append(_error("selection_rationales",
                      "selection_rationales must be a list."))
        selection_rationales = []

    seen_rationale_ids: set[str] = set()
    for index, rationale in enumerate(selection_rationales):
        field_prefix = f"selection_rationales[{index}]"
        if not isinstance(rationale, dict):
            errors.append(
                _error(field_prefix, "Each selection rationale must be an object."))
            continue
        hypothesis_id = rationale.get("hypothesis_id")
        reason = rationale.get("reason")
        if not _is_non_empty_string(hypothesis_id):
            errors.append(_error(
                f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
            continue
        normalized_hypothesis_id = str(hypothesis_id).strip()
        if normalized_hypothesis_id in seen_rationale_ids:
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    f"Duplicate rationale for hypothesis '{normalized_hypothesis_id}'.",
                )
            )
        seen_rationale_ids.add(normalized_hypothesis_id)
        if normalized_hypothesis_id not in set(selected_hypothesis_ids):
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    "Selection rationales must be present only for selected hypotheses.",
                )
            )
        if not _is_non_empty_string(reason):
            errors.append(_error(f"{field_prefix}.reason",
                          "reason must be a non-empty string."))
            continue
        normalized_reason = str(reason).strip()
        if len(normalized_reason) > 240:
            errors.append(_error(f"{field_prefix}.reason",
                          "reason must stay under 240 characters."))
        forbidden_language_hits.extend(_collect_forbidden_language(
            f"{field_prefix}.reason", normalized_reason))

    for selected_hypothesis_id in selected_hypothesis_ids:
        if selected_hypothesis_id not in seen_rationale_ids:
            errors.append(
                _error(
                    "selection_rationales",
                    f"Missing rationale for selected hypothesis '{selected_hypothesis_id}'.",
                )
            )

    for hit in forbidden_language_hits:
        warnings.append(
            _error(
                hit["field"],
                f"Semantic language flag detected ({hit['code']}).",
            )
        )

    stats = {
        "candidate_count": len(candidate_hypothesis_ids),
        "selected_count": len(selected_hypothesis_ids),
        "deferred_count": len(deferred_hypothesis_ids),
        "selection_budget": selection_budget,
    }
    invariants = {
        "selected_within_budget": len(selected_hypothesis_ids) <= selection_budget,
        "all_candidates_accounted_for": not missing_candidate_ids,
        "selected_ids_known": all(hypothesis_id in candidate_hypothesis_ids for hypothesis_id in selected_hypothesis_ids),
        "deferred_ids_known": all(hypothesis_id in candidate_hypothesis_ids for hypothesis_id in deferred_hypothesis_ids),
    }

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats=stats,
        invariants=invariants,
        forbidden_language_hits=forbidden_language_hits,
    )
