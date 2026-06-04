"""Deterministic input builders for the authoritative Phase 3A runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from hypothesis_ranking.context_resolver import build_ranking_state_min
from investigation_analysis.input_builder import (
    build_analysis_context_min,
    build_analysis_iteration_context_min,
)
from planner.context_resolver import build_planner_round_context, collect_related_substrate_refs
from router.context_reducer import build_router_context_min
from semantic_extraction.input_builder import build_overview_summary_min, build_partition_context
from state.schema import CanonicalBatchState


DEFAULT_SELECTION_BUDGET = 3


def _string_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        stripped = _string_value(value)
        if stripped:
            normalized.append(stripped)
    return normalized


def _load_canonical_batch_state(canonical_batch_state: CanonicalBatchState | dict[str, Any]) -> CanonicalBatchState:
    if isinstance(canonical_batch_state, CanonicalBatchState):
        return canonical_batch_state
    return CanonicalBatchState.from_dict(dict(canonical_batch_state or {}))


def build_phase3a_batch_id(dataset_path: str | Path, *, timestamp: datetime | None = None) -> str:
    ts = timestamp or datetime.now(UTC)
    dataset_stem = Path(dataset_path).stem.lower().replace(" ", "_")
    return f"phase3a_batch_{ts.strftime('%d%m%H%M%S')}_{dataset_stem}_{uuid4().hex[:6]}"


def default_investigation_artifact_framing_refs() -> list[dict[str, str]]:
    return [
        {
            "framing_id": "dependency_backed_regularity",
            "label": "dependency-backed regularity",
            "description": "Broad paired or dependency-backed structure may reflect a stable regularity rather than a single narrow handle.",
        },
        {
            "framing_id": "localized_representation_sensitive_handle",
            "label": "localized representation-sensitive handle",
            "description": "A narrow or representation-sensitive signal may remain locally meaningful even when it does not explain the full substrate.",
        },
        {
            "framing_id": "overlap_preserving_competing_framings",
            "label": "overlap-preserving competing framing",
            "description": "Contradictions and tensions may justify multiple partially compatible hypotheses that should remain alive together.",
        },
    ]


def build_initial_semantic_inputs(dataset_path: str | Path, batch_id: str) -> dict[str, Any]:
    dataset = Path(dataset_path)
    partition_context = build_partition_context(dataset.name)
    return {
        "overview_summary_min": build_overview_summary_min(dataset, batch_id=batch_id),
        "partition_context": partition_context,
    }


def build_initial_analysis_context(dataset_path: str | Path) -> dict[str, Any]:
    dataset = Path(dataset_path)
    return build_analysis_context_min(
        build_partition_context(dataset.name),
        default_investigation_artifact_framing_refs(),
    )


def build_current_state_ref(canonical_batch_state: CanonicalBatchState | dict[str, Any]) -> dict[str, Any]:
    state = _load_canonical_batch_state(canonical_batch_state)
    state_notes: list[str] = [f"state_version={state.state_version}"]

    for hypothesis in state.interpretive_hypotheses:
        state_notes.append(
            " | ".join(
                [
                    f"hypothesis_id={hypothesis.hypothesis_id}",
                    f"status={hypothesis.status}",
                    f"summary={hypothesis.summary}",
                    f"last_updated_round={hypothesis.last_updated_round or 'initialization'}",
                    f"revision_count={hypothesis.revision_count}",
                ]
            )
        )
        for evidence_ref in hypothesis.evidence_refs[:4]:
            state_notes.append(f"{hypothesis.hypothesis_id} evidence_ref={evidence_ref}")
        for open_gap in hypothesis.open_gaps[:3]:
            state_notes.append(f"{hypothesis.hypothesis_id} open_gap={open_gap}")
        for contradiction in hypothesis.preserved_contradictions[:3]:
            state_notes.append(f"{hypothesis.hypothesis_id} preserved_contradiction={contradiction}")
        for finding in hypothesis.merged_findings[:3]:
            state_notes.append(f"{hypothesis.hypothesis_id} merged_finding={finding}")

    return {
        "state_id": f"{state.batch_id}:v{state.state_version}",
        "state_notes": state_notes,
    }


def build_analysis_iteration_context(
    initial_hypothesis_set: dict[str, Any],
    canonical_batch_state: CanonicalBatchState | dict[str, Any],
) -> dict[str, Any]:
    return build_analysis_iteration_context_min(
        initial_hypothesis_set_ref=initial_hypothesis_set,
        current_state_ref=build_current_state_ref(canonical_batch_state),
    )


def build_round_snapshot(
    *,
    batch_id: str,
    round_id: str,
    round_index: int,
    analysis_mode: str,
    canonical_batch_state: CanonicalBatchState | dict[str, Any],
    initial_hypothesis_set: dict[str, Any],
) -> dict[str, Any]:
    state = _load_canonical_batch_state(canonical_batch_state)
    return {
        "batch_id": batch_id,
        "round_id": round_id,
        "round_index": round_index,
        "analysis_mode": analysis_mode,
        "round_start_state_version": state.state_version,
        "current_state_ref": build_current_state_ref(state),
        "initial_hypothesis_set_ref": {
            "analysis_id": _string_value(initial_hypothesis_set.get("analysis_id")),
            "hypothesis_refs": [
                {
                    "hypothesis_id": _string_value(item.get("hypothesis_id")),
                    "summary": _string_value(item.get("summary")),
                }
                for item in (initial_hypothesis_set.get("hypotheses") if isinstance(initial_hypothesis_set.get("hypotheses"), list) else [])
                if isinstance(item, dict) and _string_value(item.get("hypothesis_id"))
            ],
        },
    }


def build_round_ranking_state(
    canonical_batch_state: CanonicalBatchState | dict[str, Any],
    *,
    round_id: str,
    selection_budget: int = DEFAULT_SELECTION_BUDGET,
) -> dict[str, Any]:
    state = _load_canonical_batch_state(canonical_batch_state)
    hypothesis_state_refs = [
        {
            "hypothesis_id": hypothesis.hypothesis_id,
            "state_notes": [
                f"status={hypothesis.status}",
                f"summary={hypothesis.summary}",
                f"revision_count={hypothesis.revision_count}",
                f"last_updated_round={hypothesis.last_updated_round or 'initialization'}",
                *[f"open_gap={item}" for item in hypothesis.open_gaps[:3]],
                *[f"preserved_contradiction={item}" for item in hypothesis.preserved_contradictions[:3]],
                *[f"merged_finding={item}" for item in hypothesis.merged_findings[:3]],
            ],
        }
        for hypothesis in state.interpretive_hypotheses
        if hypothesis.hypothesis_id
    ]
    return build_ranking_state_min(
        round_id=round_id,
        selection_budget=selection_budget,
        hypothesis_state_refs=hypothesis_state_refs,
        round_constraints=[
            f"selection_budget={selection_budget}",
            "allocation_only",
            "preserve_deferred_hypotheses",
            f"round_start_state_version={state.state_version}",
        ],
    )


def overlay_hypothesis_current_status(
    investigation_hypothesis_set: dict[str, Any],
    canonical_batch_state: CanonicalBatchState | dict[str, Any],
) -> dict[str, Any]:
    state = _load_canonical_batch_state(canonical_batch_state)
    status_by_hypothesis_id = {
        hypothesis.hypothesis_id: hypothesis.status
        for hypothesis in state.interpretive_hypotheses
        if hypothesis.hypothesis_id
    }
    payload = dict(investigation_hypothesis_set or {})
    hypotheses = []
    for item in payload.get("hypotheses", []) or []:
        if not isinstance(item, dict):
            continue
        hypothesis = dict(item)
        hypothesis_id = _string_value(hypothesis.get("hypothesis_id"))
        if hypothesis_id and hypothesis_id in status_by_hypothesis_id:
            hypothesis["current_status"] = status_by_hypothesis_id[hypothesis_id]
        hypotheses.append(hypothesis)
    payload["hypotheses"] = hypotheses
    return payload


def build_planner_context(selected_hypothesis_context: dict[str, Any], round_id: str) -> dict[str, Any]:
    from tools.registry import get_tool_capability_records

    tool_capability_records = get_tool_capability_records()
    return build_planner_round_context(
        round_id=round_id,
        related_substrate_refs=collect_related_substrate_refs(selected_hypothesis_context),
        tool_capability_refs=sorted(tool_capability_records.keys()),
        round_constraints=[
            "strategic_only",
            "no_exact_tool_calls",
            "preserve_selected_scope",
            "router_ready_handoff",
        ],
    )


def build_router_context(
    *,
    planner_round_context: dict[str, Any],
    selected_hypothesis_context: dict[str, Any],
    planner_strategy: dict[str, Any],
    max_worker_steps: int,
    max_worker_retries: int,
    max_tasks_per_hypothesis: int,
) -> dict[str, Any]:
    hypothesis_id = _string_value(planner_strategy.get("hypothesis_id"))
    selected_hypotheses = selected_hypothesis_context.get("selected_hypotheses", [])
    selected_hypothesis = next(
        (
            item
            for item in selected_hypotheses
            if isinstance(item, dict) and _string_value(item.get("hypothesis_id")) == hypothesis_id
        ),
        {},
    )

    related_substrate_refs = _string_list(selected_hypothesis.get("evidence_refs"))
    if not related_substrate_refs:
        related_substrate_refs = _string_list(planner_round_context.get("related_substrate_refs"))

    round_constraints = _string_list(planner_round_context.get("round_constraints"))
    guardrails = list(
        dict.fromkeys(
            [
                "bounded_local_scope",
                "no_exact_tool_calls",
                "no_hidden_replanning",
                *round_constraints,
            ]
        )
    )
    key_check_count = len(_string_list(planner_strategy.get("key_checks")))
    max_tasks = min(max_tasks_per_hypothesis, max(1, key_check_count))

    return build_router_context_min(
        related_substrate_refs=related_substrate_refs,
        tool_capability_refs=_string_list(planner_round_context.get("tool_capability_refs")),
        execution_budget={
            "max_worker_steps": max_worker_steps,
            "max_tasks": max_tasks,
            "max_retries": max_worker_retries,
        },
        guardrails=guardrails,
    )


def build_worker_runtime_refs(
    *,
    router_context_min: dict[str, Any],
    semantic_substrate: dict[str, Any],
    dataset_path: str | Path,
) -> dict[str, Any]:
    execution_budget = (
        dict(router_context_min.get("execution_budget") or {})
        if isinstance(router_context_min.get("execution_budget"), dict)
        else {}
    )
    return {
        "tool_handles": {},
        "dataset_handles": {
            "dataset_path": str(dataset_path),
            "semantic_substrate": dict(semantic_substrate or {}),
        },
        "budget_rules": {
            "max_steps": int(execution_budget.get("max_worker_steps") or 0),
            "max_retries": int(execution_budget.get("max_retries") or 0),
        },
    }
