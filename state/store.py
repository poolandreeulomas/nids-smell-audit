"""State store helpers scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List

from state.schema import AgentState, EvidenceBlock


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
