"""State store helpers for Phase 3 canonical batch state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from state.schema import (
    CanonicalBatchState,
    InterpretiveHypothesis,
    StateRevisionRecord,
)


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return list(dict.fromkeys(normalized))


def init_canonical_batch_state(
    *,
    batch_id: str,
    structural_substrate: dict[str, Any],
    hypothesis_set: dict[str, Any] | None = None,
    state_version: int = 1,
) -> CanonicalBatchState:
    """Create the initial canonical batch state from grounded inputs."""
    normalized_batch_id = str(batch_id or "").strip()
    if not normalized_batch_id:
        raise ValueError("batch_id must be a non-empty string")
    if not isinstance(structural_substrate, dict):
        raise TypeError("structural_substrate must be a dictionary")
    if state_version < 1:
        raise ValueError("state_version must be at least 1")

    substrate_batch_id = str(structural_substrate.get("batch_id", "") or "").strip()
    if substrate_batch_id and substrate_batch_id != normalized_batch_id:
        raise ValueError("structural_substrate batch_id does not match batch_id")

    raw_hypothesis_set = hypothesis_set if isinstance(hypothesis_set, dict) else {}
    hypothesis_batch_id = str(raw_hypothesis_set.get("batch_id", "") or "").strip()
    if hypothesis_batch_id and hypothesis_batch_id != normalized_batch_id:
        raise ValueError("hypothesis_set batch_id does not match batch_id")

    interpretive_hypotheses: list[InterpretiveHypothesis] = []
    raw_hypotheses = raw_hypothesis_set.get("hypotheses")
    if isinstance(raw_hypotheses, list):
        for item in raw_hypotheses:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("hypothesis_id", "") or "").strip()
            if not hypothesis_id:
                continue
            interpretive_hypotheses.append(
                InterpretiveHypothesis(
                    hypothesis_id=hypothesis_id,
                    summary=str(item.get("summary", "") or ""),
                    status="unresolved",
                    evidence_refs=_string_list(item.get("evidence_refs")),
                    open_gaps=_string_list(item.get("open_questions")),
                )
            )

    initialization_updates: list[dict[str, Any]] = [
        {
            "action": "register_structural_substrate",
            "substrate_id": str(structural_substrate.get("substrate_id", "") or ""),
            "region_count": len(structural_substrate.get("compressed_regions", []) or []),
            "weak_signal_count": len(
                structural_substrate.get("preserved_weak_signals", []) or []
            ),
            "contradiction_count": len(
                structural_substrate.get("contradictions", []) or []
            ),
            "tension_count": len(
                structural_substrate.get("unresolved_tensions", []) or []
            ),
        }
    ]
    if interpretive_hypotheses:
        initialization_updates.append(
            {
                "action": "register_interpretive_hypotheses",
                "analysis_id": str(raw_hypothesis_set.get("analysis_id", "") or ""),
                "hypothesis_count": len(interpretive_hypotheses),
            }
        )

    return CanonicalBatchState(
        batch_id=normalized_batch_id,
        state_version=state_version,
        structural_substrate=dict(structural_substrate),
        interpretive_hypotheses=interpretive_hypotheses,
        revision_log=[
            StateRevisionRecord(
                revision_type="initialization",
                state_version=state_version,
                applied_updates=initialization_updates,
                timestamp=datetime.now(UTC).isoformat(),
            )
        ],
    )


def canonical_state_to_dict(state: CanonicalBatchState) -> dict[str, Any]:
    """Return canonical batch state as a JSON-serializable dictionary."""
    return state.to_dict()


def get_interpretive_hypothesis(
    state: CanonicalBatchState,
    hypothesis_id: str,
) -> InterpretiveHypothesis | None:
    """Return the current interpretive record for one hypothesis."""
    target_id = str(hypothesis_id or "").strip()
    for item in state.interpretive_hypotheses:
        if item.hypothesis_id == target_id:
            return item
    return None


def apply_interpretive_hypothesis_patch(
    state: CanonicalBatchState,
    *,
    round_id: str,
    hypothesis_id: str,
    summary: str | None = None,
    status: str | None = None,
    evidence_refs: list[str] | None = None,
    open_gaps: list[str] | None = None,
    preserved_contradictions: list[str] | None = None,
    merged_findings: list[str] | None = None,
    update_focus: str | None = None,
    applied_updates: list[dict[str, Any]] | None = None,
) -> CanonicalBatchState:
    """Return a new canonical batch state with one conservative hypothesis update."""
    if not isinstance(state, CanonicalBatchState):
        raise TypeError("state must be a CanonicalBatchState")

    normalized_round_id = str(round_id or "").strip()
    if not normalized_round_id:
        raise ValueError("round_id must be a non-empty string")

    normalized_hypothesis_id = str(hypothesis_id or "").strip()
    if not normalized_hypothesis_id:
        raise ValueError("hypothesis_id must be a non-empty string")

    next_state = CanonicalBatchState.from_dict(state.to_dict())
    target = get_interpretive_hypothesis(next_state, normalized_hypothesis_id)
    if target is None:
        raise KeyError(
            f"unknown hypothesis_id for canonical batch state: {normalized_hypothesis_id}"
        )

    auto_updates: list[dict[str, Any]] = []

    if summary is not None:
        normalized_summary = str(summary or "").strip()
        if not normalized_summary:
            raise ValueError("summary patch must be non-empty when provided")
        if normalized_summary != target.summary:
            auto_updates.append(
                {"field": "summary", "from": target.summary, "to": normalized_summary}
            )
            target.summary = normalized_summary

    if status is not None:
        normalized_status = str(status or "").strip()
        if not normalized_status:
            raise ValueError("status patch must be non-empty when provided")
        if normalized_status != target.status:
            auto_updates.append(
                {"field": "status", "from": target.status, "to": normalized_status}
            )
            target.status = normalized_status

    list_patches = [
        ("evidence_refs", evidence_refs),
        ("open_gaps", open_gaps),
        ("preserved_contradictions", preserved_contradictions),
        ("merged_findings", merged_findings),
    ]
    for field_name, values in list_patches:
        if values is None:
            continue
        normalized_values = _string_list(values)
        previous_values = list(getattr(target, field_name))
        if normalized_values != previous_values:
            auto_updates.append(
                {
                    "field": field_name,
                    "from": previous_values,
                    "to": normalized_values,
                }
            )
            setattr(target, field_name, normalized_values)

    if update_focus is not None:
        normalized_focus = str(update_focus or "").strip()
        if not normalized_focus:
            raise ValueError("update_focus patch must be non-empty when provided")
        if normalized_focus != target.update_focus:
            auto_updates.append(
                {
                    "field": "update_focus",
                    "from": target.update_focus,
                    "to": normalized_focus,
                }
            )
            target.update_focus = normalized_focus

    target.last_updated_round = normalized_round_id
    target.revision_count += 1

    next_state.state_version += 1
    revision_updates = [dict(item) for item in (applied_updates or auto_updates)]
    if not revision_updates:
        revision_updates = [
            {
                "field": "no_op",
                "reason": "No canonical interpretive fields changed during this commit.",
            }
        ]

    next_state.revision_log.append(
        StateRevisionRecord(
            revision_type="state_update",
            state_version=next_state.state_version,
            round_id=normalized_round_id,
            hypothesis_id=normalized_hypothesis_id,
            applied_updates=revision_updates,
            timestamp=datetime.now(UTC).isoformat(),
        )
    )

    return next_state
