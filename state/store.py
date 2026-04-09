"""State store helpers scaffold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from state.schema import AgentState


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


def advance_step(state: AgentState, step_increment: int = 1) -> None:
    """Advance current_step by a positive increment."""
    if step_increment < 0:
        raise ValueError("step_increment must be non-negative")
    state.current_step += step_increment


def state_to_dict(state: AgentState) -> dict[str, Any]:
    """Return state as a JSON-serializable dictionary."""
    return state.to_dict()
