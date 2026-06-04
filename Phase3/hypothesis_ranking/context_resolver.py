"""Context normalization and prompt-ready projection helpers for Hypothesis Ranking."""

from __future__ import annotations

from typing import Any

from hypothesis_ranking.contracts import MAX_SELECTION_BUDGET


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


def build_ranking_state_min(
    *,
    round_id: str,
    selection_budget: int = MAX_SELECTION_BUDGET,
    hypothesis_state_refs: list[dict[str, Any]] | None = None,
    round_constraints: list[str] | None = None,
) -> dict[str, Any]:
    normalized_state_refs: list[dict[str, Any]] = []
    for raw_state_ref in hypothesis_state_refs or []:
        if not isinstance(raw_state_ref, dict):
            continue
        hypothesis_id = _string_value(raw_state_ref.get("hypothesis_id"))
        if not hypothesis_id:
            continue
        normalized_state_refs.append(
            {
                "hypothesis_id": hypothesis_id,
                "state_notes": _string_list(raw_state_ref.get("state_notes")),
            }
        )

    normalized_budget = selection_budget if isinstance(selection_budget, int) else MAX_SELECTION_BUDGET
    if normalized_budget <= 0:
        normalized_budget = MAX_SELECTION_BUDGET

    return {
        "round_id": _string_value(round_id),
        "selection_budget": normalized_budget,
        "hypothesis_state_refs": normalized_state_refs,
        "round_constraints": _string_list(round_constraints),
    }


def project_candidate_hypothesis_context(investigation_hypothesis_set: dict[str, Any]) -> dict[str, Any]:
    raw = investigation_hypothesis_set if isinstance(investigation_hypothesis_set, dict) else {}
    raw_hypotheses = raw.get("hypotheses") if isinstance(raw.get("hypotheses"), list) else []
    hypotheses: list[dict[str, Any]] = []

    for raw_hypothesis in raw_hypotheses:
        if not isinstance(raw_hypothesis, dict):
            continue
        evidence_refs = _string_list(raw_hypothesis.get("evidence_refs"))
        open_questions = _string_list(raw_hypothesis.get("open_questions"))
        hypotheses.append(
            {
                "hypothesis_id": _string_value(raw_hypothesis.get("hypothesis_id")),
                "summary": _string_value(raw_hypothesis.get("summary")),
                "evidence_refs": evidence_refs,
                "open_questions": open_questions,
                "evidence_ref_count": len(evidence_refs),
                "open_question_count": len(open_questions),
            }
        )

    return {
        "analysis_id": _string_value(raw.get("analysis_id")),
        "batch_id": _string_value(raw.get("batch_id")),
        "hypothesis_count": len(hypotheses),
        "hypotheses": hypotheses,
    }


def project_ranking_state_min(ranking_state_min: dict[str, Any]) -> dict[str, Any]:
    raw = ranking_state_min if isinstance(ranking_state_min, dict) else {}
    raw_state_refs = raw.get("hypothesis_state_refs") if isinstance(raw.get("hypothesis_state_refs"), list) else []

    return {
        "round_id": _string_value(raw.get("round_id")),
        "selection_budget": raw.get("selection_budget") if isinstance(raw.get("selection_budget"), int) else 0,
        "hypothesis_state_refs": [
            {
                "hypothesis_id": _string_value(item.get("hypothesis_id")) if isinstance(item, dict) else "",
                "state_notes": _string_list(item.get("state_notes")) if isinstance(item, dict) else [],
            }
            for item in raw_state_refs
        ],
        "round_constraints": _string_list(raw.get("round_constraints")),
    }


def collect_candidate_hypothesis_ids(investigation_hypothesis_set: dict[str, Any]) -> set[str]:
    raw = investigation_hypothesis_set if isinstance(investigation_hypothesis_set, dict) else {}
    raw_hypotheses = raw.get("hypotheses") if isinstance(raw.get("hypotheses"), list) else []
    return {
        hypothesis_id
        for item in raw_hypotheses
        if isinstance(item, dict)
        for hypothesis_id in [_string_value(item.get("hypothesis_id"))]
        if hypothesis_id
    }


def build_selection_index(
    investigation_hypothesis_set: dict[str, Any],
    ranking_decision: dict[str, Any],
) -> dict[str, Any]:
    candidate_context = project_candidate_hypothesis_context(investigation_hypothesis_set)
    hypothesis_map = {
        item["hypothesis_id"]: item
        for item in candidate_context.get("hypotheses", [])
        if item.get("hypothesis_id")
    }
    selected_ids = [
        hypothesis_id
        for hypothesis_id in _string_list(ranking_decision.get("selected_hypothesis_ids"))
        if hypothesis_id in hypothesis_map
    ]
    deferred_ids = [
        hypothesis_id
        for hypothesis_id in _string_list(ranking_decision.get("deferred_hypothesis_ids"))
        if hypothesis_id in hypothesis_map
    ]
    rationale_map = {
        _string_value(item.get("hypothesis_id")): _string_value(item.get("reason"))
        for item in (ranking_decision.get("selection_rationales") if isinstance(ranking_decision.get("selection_rationales"), list) else [])
        if isinstance(item, dict) and _string_value(item.get("hypothesis_id"))
    }

    candidate_ids = set(hypothesis_map.keys())
    accounted_for = set(selected_ids).union(deferred_ids)

    return {
        "candidate_count": len(candidate_ids),
        "selected_count": len(selected_ids),
        "deferred_count": len(deferred_ids),
        "unaccounted_hypothesis_ids": sorted(candidate_ids.difference(accounted_for)),
        "selected_hypotheses": [
            {
                "hypothesis_id": hypothesis_id,
                "summary": hypothesis_map[hypothesis_id]["summary"],
                "reason": rationale_map.get(hypothesis_id, ""),
                "evidence_ref_count": hypothesis_map[hypothesis_id]["evidence_ref_count"],
                "open_question_count": hypothesis_map[hypothesis_id]["open_question_count"],
            }
            for hypothesis_id in selected_ids
        ],
        "deferred_hypotheses": [
            {
                "hypothesis_id": hypothesis_id,
                "summary": hypothesis_map[hypothesis_id]["summary"],
                "evidence_ref_count": hypothesis_map[hypothesis_id]["evidence_ref_count"],
                "open_question_count": hypothesis_map[hypothesis_id]["open_question_count"],
            }
            for hypothesis_id in deferred_ids
        ],
    }