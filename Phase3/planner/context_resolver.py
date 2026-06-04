"""Context normalization and prompt-ready projection helpers for Planner."""

from __future__ import annotations

from typing import Any


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


def build_selected_hypothesis_context(
    *,
    selected_hypotheses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_hypotheses: list[dict[str, Any]] = []
    for raw_hypothesis in selected_hypotheses or []:
        if not isinstance(raw_hypothesis, dict):
            continue
        hypothesis_id = _string_value(raw_hypothesis.get("hypothesis_id"))
        if not hypothesis_id:
            continue
        normalized_hypotheses.append(
            {
                "hypothesis_id": hypothesis_id,
                "summary": _string_value(raw_hypothesis.get("summary")),
                "evidence_refs": _string_list(raw_hypothesis.get("evidence_refs")),
                "open_questions": _string_list(raw_hypothesis.get("open_questions")),
                "current_status": _string_value(raw_hypothesis.get("current_status")) or "selected_for_round",
            }
        )

    return {"selected_hypotheses": normalized_hypotheses}


def resolve_selected_hypothesis_context(
    *,
    ranking_decision_min: dict[str, Any],
    investigation_hypothesis_set: dict[str, Any],
    default_status: str = "selected_for_round",
) -> dict[str, Any]:
    hypothesis_map = {
        hypothesis_id: item
        for item in (
            investigation_hypothesis_set.get("hypotheses")
            if isinstance(investigation_hypothesis_set.get("hypotheses"), list)
            else []
        )
        if isinstance(item, dict)
        for hypothesis_id in [_string_value(item.get("hypothesis_id"))]
        if hypothesis_id
    }

    selected_hypotheses: list[dict[str, Any]] = []
    for hypothesis_id in collect_selected_hypothesis_ids(ranking_decision_min):
        source = hypothesis_map.get(hypothesis_id, {})
        selected_hypotheses.append(
            {
                "hypothesis_id": hypothesis_id,
                "summary": _string_value(source.get("summary")),
                "evidence_refs": _string_list(source.get("evidence_refs")),
                "open_questions": _string_list(source.get("open_questions")),
                "current_status": _string_value(source.get("current_status")) or default_status,
            }
        )

    return build_selected_hypothesis_context(selected_hypotheses=selected_hypotheses)


def build_planner_round_context(
    *,
    round_id: str,
    related_substrate_refs: list[str] | None = None,
    tool_capability_refs: list[str] | None = None,
    round_constraints: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "round_id": _string_value(round_id),
        "related_substrate_refs": _string_list(related_substrate_refs),
        "tool_capability_refs": _string_list(tool_capability_refs),
        "round_constraints": _string_list(round_constraints),
    }


def project_selected_hypothesis_context(selected_hypothesis_context: dict[str, Any]) -> dict[str, Any]:
    raw = selected_hypothesis_context if isinstance(selected_hypothesis_context, dict) else {}
    raw_hypotheses = (
        raw.get("selected_hypotheses") if isinstance(raw.get("selected_hypotheses"), list) else []
    )

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
                "current_status": _string_value(raw_hypothesis.get("current_status")),
                "evidence_ref_count": len(evidence_refs),
                "open_question_count": len(open_questions),
            }
        )

    return {
        "selected_count": len(hypotheses),
        "selected_hypotheses": hypotheses,
    }


def project_planner_round_context(
    planner_round_context: dict[str, Any],
    *,
    tool_capability_catalog: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw = planner_round_context if isinstance(planner_round_context, dict) else {}
    tool_refs = _string_list(raw.get("tool_capability_refs"))
    tool_catalog = tool_capability_catalog or {}

    return {
        "round_id": _string_value(raw.get("round_id")),
        "related_substrate_refs": _string_list(raw.get("related_substrate_refs")),
        "tool_capability_refs": tool_refs,
        "tool_capabilities": [
            {
                "tool_name": tool_ref,
                "epistemic_role": _string_value(tool_catalog.get(tool_ref, {}).get("epistemic_role")),
                "supported_scopes": _string_list(tool_catalog.get(tool_ref, {}).get("supported_scopes")),
                "boundedness_notes": _string_value(tool_catalog.get(tool_ref, {}).get("boundedness_notes")),
            }
            for tool_ref in tool_refs
        ],
        "tool_capability_count": len(tool_refs),
        "round_constraints": _string_list(raw.get("round_constraints")),
    }


def collect_selected_hypothesis_ids(ranking_decision_min: dict[str, Any]) -> list[str]:
    raw = ranking_decision_min if isinstance(ranking_decision_min, dict) else {}
    selected_ids = _string_list(raw.get("selected_hypothesis_ids"))
    seen: set[str] = set()
    ordered: list[str] = []
    for hypothesis_id in selected_ids:
        if hypothesis_id in seen:
            continue
        seen.add(hypothesis_id)
        ordered.append(hypothesis_id)
    return ordered


def collect_related_substrate_refs(selected_hypothesis_context: dict[str, Any]) -> list[str]:
    projected = project_selected_hypothesis_context(selected_hypothesis_context)
    seen: set[str] = set()
    ordered: list[str] = []
    for hypothesis in projected.get("selected_hypotheses", []):
        if not isinstance(hypothesis, dict):
            continue
        for evidence_ref in hypothesis.get("evidence_refs", []):
            if not isinstance(evidence_ref, str) or not evidence_ref or evidence_ref in seen:
                continue
            seen.add(evidence_ref)
            ordered.append(evidence_ref)
    return ordered


def build_strategy_index(
    selected_hypothesis_context: dict[str, Any],
    planner_round_output: dict[str, Any],
) -> dict[str, Any]:
    projected_selected_context = project_selected_hypothesis_context(selected_hypothesis_context)
    selected_map = {
        item["hypothesis_id"]: item
        for item in projected_selected_context.get("selected_hypotheses", [])
        if item.get("hypothesis_id")
    }
    strategies = (
        planner_round_output.get("planner_strategies")
        if isinstance(planner_round_output, dict) and isinstance(planner_round_output.get("planner_strategies"), list)
        else []
    )

    strategy_hypothesis_ids: list[str] = []
    strategy_summaries: list[dict[str, Any]] = []
    for strategy in strategies:
        if not isinstance(strategy, dict):
            continue
        hypothesis_id = _string_value(strategy.get("hypothesis_id"))
        if not hypothesis_id:
            continue
        strategy_hypothesis_ids.append(hypothesis_id)
        selected_item = selected_map.get(hypothesis_id, {})
        strategy_summaries.append(
            {
                "strategy_id": _string_value(strategy.get("strategy_id")),
                "hypothesis_id": hypothesis_id,
                "summary": _string_value(selected_item.get("summary")),
                "strategic_objective": _string_value(strategy.get("strategic_objective")),
                "key_check_count": len(_string_list(strategy.get("key_checks"))),
                "success_criteria_count": len(_string_list(strategy.get("success_criteria"))),
                "router_constraint_count": len(_string_list(strategy.get("router_constraints"))),
            }
        )

    selected_ids = set(selected_map.keys())
    produced_ids = set(strategy_hypothesis_ids)
    return {
        "selected_count": len(selected_ids),
        "strategy_count": len(strategy_summaries),
        "missing_strategy_hypothesis_ids": sorted(selected_ids.difference(produced_ids)),
        "unexpected_strategy_hypothesis_ids": sorted(produced_ids.difference(selected_ids)),
        "strategies": strategy_summaries,
    }