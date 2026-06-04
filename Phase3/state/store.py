"""State store helpers scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List

from state.schema import (
    AgentState,
    CanonicalBatchState,
    EvidenceBlock,
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


def init_state(
    run_id: str,
    objective: str,
    max_steps: int,
    available_features: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentState:
    """Create an explicit initial state for one run."""
    return AgentState(
        run_id=run_id,
        objective=objective,
        current_step=0,
        max_steps=max_steps,
        available_features=list(available_features or []),
        analyzed_features={},
        history=[],
        promising_features=[],
        errors=[],
        metadata=dict(metadata or {}),
    )


def append_history(state: AgentState, step_record: dict[str, Any]) -> None:
    """Append one step record to state history with a timestamp if missing."""
    record = dict(step_record)
    record.setdefault("timestamp", datetime.now(UTC).isoformat())
    state.history.append(record)


def update_analyzed_feature(
    state: AgentState,
    feature_name: str,
    evidence: dict[str, Any],
) -> None:
    """Store or update evidence associated with a feature."""
    existing = state.analyzed_features.get(feature_name, {})
    merged = {**existing, **evidence}
    state.analyzed_features[feature_name] = merged


def append_error(state: AgentState, error_record: dict[str, Any]) -> None:
    """Append one structured error record to state.errors."""
    record = dict(error_record)
    record.setdefault("timestamp", datetime.now(UTC).isoformat())
    state.errors.append(record)


def set_promising_features(state: AgentState, features: list[str]) -> None:
    """Replace promising features with an ordered deduplicated list."""
    deduped = list(dict.fromkeys(features))
    state.promising_features = deduped


def merge_metadata(state: AgentState, metadata: dict[str, Any]) -> None:
    """Merge metadata dictionary into state metadata."""
    state.metadata.update(metadata)


def get_last_hypothesis(state: AgentState) -> str | None:
    """Return the last stored hypothesis string or None if missing."""
    return state.metadata.get("last_hypothesis")


def record_hypothesis_if_changed(state: AgentState, hypothesis: str) -> None:
    """Record hypothesis into metadata if it differs from last.

    - Appends to `hypothesis_history` list and increments
      `hypothesis_revision_count` when the hypothesis text changes.
    - Stores the current hypothesis into `last_hypothesis`.
    """
    if hypothesis is None:
        return

    last = state.metadata.get("last_hypothesis")
    if last == hypothesis:
        # No change; nothing to do
        return

    # Append to history (keep it short)
    history = state.metadata.get("hypothesis_history")
    if not isinstance(history, list):
        history = []
    history.append({"step": state.current_step, "hypothesis": hypothesis})
    state.metadata["hypothesis_history"] = history

    # Increment revision counter
    count = state.metadata.get("hypothesis_revision_count", 0)
    try:
        count = int(count) + 1
    except Exception:
        count = 1
    state.metadata["hypothesis_revision_count"] = count

    # update last_hypothesis
    state.metadata["last_hypothesis"] = hypothesis


def advance_step(state: AgentState, step_increment: int = 1) -> None:
    """Advance current_step by a positive increment."""
    if step_increment < 0:
        raise ValueError("step_increment must be non-negative")
    state.current_step += step_increment


def state_to_dict(state: AgentState) -> dict[str, Any]:
    """Return state as a JSON-serializable dictionary."""
    return state.to_dict()


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
            "contradiction_count": len(structural_substrate.get("contradictions", []) or []),
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


def add_evidence(
    state: AgentState,
    feature: str,
    block: EvidenceBlock | dict,
    *,
    deduplicate: bool = False,
) -> int:
    """Append an evidence block for `feature` and return its index.

    - `block` may be an `EvidenceBlock` instance or a plain `dict`.
    - If `deduplicate=True`, perform a deterministic content fingerprint
      check and return an existing index instead of appending.

    This function intentionally performs lightweight coercion only; more
    advanced validation and policies belong in later steps.
    """
    # Normalize incoming block to a plain dict for storage.
    if isinstance(block, EvidenceBlock):
        eb_dict = block.to_dict()
    elif isinstance(block, dict):
        eb_dict = EvidenceBlock.from_dict(block).to_dict()
    else:
        try:
            eb_dict = EvidenceBlock.from_dict(dict(block)).to_dict()
        except Exception as exc:  # pragma: no cover - defensive
            raise TypeError(
                "block must be EvidenceBlock or dict-like") from exc

    lst: List[Dict[str, Any]] = state.evidence_by_feature.setdefault(feature, [
    ])

    import hashlib
    import json

    canonical = json.dumps(eb_dict, sort_keys=True, separators=(",", ":"))
    target = hashlib.sha1(canonical.encode("utf-8")).hexdigest()

    if deduplicate:
        for i, existing in enumerate(lst):
            candidate = existing if isinstance(
                existing, dict) else existing.to_dict()
            h = hashlib.sha1(json.dumps(candidate, sort_keys=True, separators=(
                ",", ":")).encode("utf-8")).hexdigest()
            if h == target:
                return i

    lst.append(eb_dict)

    # Update a minimal analyzed_features summary for backward compatibility.
    try:
        existing = state.analyzed_features.get(feature, {}) or {}
        tools_used = set(existing.get("tools_used", []) or [])
        prov = eb_dict.get("provenance", {}) or {}
        tool_name = prov.get("tool") or prov.get("source")
        if tool_name:
            tools_used.add(tool_name)
        merged = dict(existing)
        merged["tools_used"] = sorted(tools_used)
        merged["last_result"] = eb_dict
        state.analyzed_features[feature] = merged
    except Exception:
        # Never fail state updates due to analysis summary problems.
        pass

    return len(lst) - 1


def update_feature_status(
    state: AgentState, feature: str, status: str, *, reason: str | None = None
) -> None:
    """Update the `status` of the latest evidence block for `feature`.

    Appends a deterministic status-history record into the block's
    provenance under `status_history` and keeps `state.analyzed_features`
    `last_result.status` in sync when present.
    """
    lst = state.evidence_by_feature.get(feature, []) or []
    if not lst:
        raise ValueError(f"no evidence present for feature: {feature}")

    last = lst[-1]
    # Work both with EvidenceBlock instances and plain dicts.
    if isinstance(last, EvidenceBlock):
        previous = last.status
        last.status = status
        history = last.provenance.setdefault("status_history", [])
    else:
        previous = last.get("status")
        last["status"] = status
        history = last.setdefault("status_history", [])

    history.append({
        "step": state.current_step,
        "previous_status": previous,
        "new_status": status,
        "reason": reason,
    })

    # Mirror to analyzed_features summary if present.
    try:
        summary = state.analyzed_features.get(feature)
        if isinstance(summary, dict) and "last_result" in summary and isinstance(summary["last_result"], dict):
            summary["last_result"]["status"] = status
            state.analyzed_features[feature] = summary
    except Exception:
        pass


def record_contradiction(
    state: AgentState, feature: str, reason: str, evidence_refs: List[int] | None = None
) -> None:
    """Append a structured contradiction record to `state.contradiction_memory`.

    - `evidence_refs` are validated against the current feature evidence list
      and only valid integer indices are kept. A shallow snapshot of the
      latest evidence block is included for traceability.
    """
    lst = state.evidence_by_feature.get(feature, []) or []
    validated: List[int] = []
    if evidence_refs:
        for r in evidence_refs:
            if isinstance(r, int) and 0 <= r < len(lst):
                validated.append(r)

    snapshot = None
    if lst:
        last = lst[-1]
        if isinstance(last, EvidenceBlock):
            snapshot = last.to_dict()
        else:
            snapshot = dict(last)
        # Limit snapshot keys to keep records compact.
        snapshot = {k: snapshot[k] for k in (
            "feature", "status", "metrics") if k in snapshot}

    record = {
        "feature": feature,
        "reason": reason,
        "evidence_refs": validated,
        "step": state.current_step,
        "evidence_snapshot": snapshot,
    }
    state.contradiction_memory.append(record)
