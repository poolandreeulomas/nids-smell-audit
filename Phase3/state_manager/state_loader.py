"""Helpers for loading and projecting canonical state for State Manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from state.schema import CanonicalBatchState
from state.store import get_interpretive_hypothesis
from utils.run_logging import load_json


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


def _has_relevant_overlap(
    values: list[str],
    relevant_evidence_refs: set[str],
) -> bool:
    if not relevant_evidence_refs:
        return True
    return bool(set(values) & relevant_evidence_refs)


def _project_structural_substrate(
    structural_substrate: dict[str, Any],
    *,
    relevant_evidence_refs: set[str],
) -> dict[str, Any]:
    raw = structural_substrate if isinstance(structural_substrate, dict) else {}

    projected_regions: list[dict[str, Any]] = []
    for region in raw.get("compressed_regions", []) or []:
        if not isinstance(region, dict):
            continue
        region_evidence_refs = _string_list(region.get("evidence_refs"))
        if not _has_relevant_overlap(region_evidence_refs, relevant_evidence_refs):
            continue
        projected_regions.append(
            {
                "region_id": str(region.get("region_id", "") or ""),
                "region_kind": str(region.get("region_kind", "") or ""),
                "status": str(region.get("status", "") or ""),
                "summary": str(region.get("summary", "") or ""),
                "feature_scope": dict(region.get("feature_scope", {}) or {}),
                "evidence_refs": region_evidence_refs,
            }
        )

    projected_weak_signals: list[dict[str, Any]] = []
    for signal in raw.get("preserved_weak_signals", []) or []:
        if not isinstance(signal, dict):
            continue
        signal_evidence_refs = _string_list(signal.get("evidence_refs"))
        if not _has_relevant_overlap(signal_evidence_refs, relevant_evidence_refs):
            continue
        projected_weak_signals.append(
            {
                "weak_signal_id": str(signal.get("weak_signal_id", "") or ""),
                "descriptor": str(signal.get("descriptor", "") or ""),
                "feature_scope": dict(signal.get("feature_scope", {}) or {}),
                "evidence_refs": signal_evidence_refs,
            }
        )

    projected_contradictions: list[dict[str, Any]] = []
    for contradiction in raw.get("contradictions", []) or []:
        if not isinstance(contradiction, dict):
            continue
        supporting_refs = _string_list(contradiction.get("supporting_evidence_refs"))
        conflicting_refs = _string_list(contradiction.get("conflicting_evidence_refs"))
        if not _has_relevant_overlap(
            supporting_refs + conflicting_refs,
            relevant_evidence_refs,
        ):
            continue
        projected_contradictions.append(
            {
                "contradiction_id": str(contradiction.get("contradiction_id", "") or ""),
                "description": str(contradiction.get("description", "") or ""),
                "supporting_evidence_refs": supporting_refs,
                "conflicting_evidence_refs": conflicting_refs,
            }
        )

    projected_tensions: list[dict[str, Any]] = []
    for tension in raw.get("unresolved_tensions", []) or []:
        if not isinstance(tension, dict):
            continue
        tension_evidence_refs = _string_list(tension.get("evidence_refs"))
        if not _has_relevant_overlap(tension_evidence_refs, relevant_evidence_refs):
            continue
        projected_tensions.append(
            {
                "tension_id": str(tension.get("tension_id", "") or ""),
                "description": str(tension.get("description", "") or ""),
                "evidence_refs": tension_evidence_refs,
            }
        )

    return {
        "substrate_id": str(raw.get("substrate_id", "") or ""),
        "batch_id": str(raw.get("batch_id", "") or ""),
        "compressed_regions": projected_regions,
        "preserved_weak_signals": projected_weak_signals,
        "contradictions": projected_contradictions,
        "unresolved_tensions": projected_tensions,
    }


def load_canonical_batch_state(
    source: CanonicalBatchState | dict[str, Any] | str | Path,
) -> CanonicalBatchState:
    if isinstance(source, CanonicalBatchState):
        return source

    if isinstance(source, (str, Path)):
        return CanonicalBatchState.from_dict(load_json(source))

    if isinstance(source, dict):
        return CanonicalBatchState.from_dict(source)

    raise TypeError("canonical batch state source must be a dict, Path, or CanonicalBatchState")


def collect_state_evidence_refs(canonical_batch_state: CanonicalBatchState) -> set[str]:
    substrate = canonical_batch_state.structural_substrate
    evidence_ids: set[str] = set()

    for region in substrate.get("compressed_regions", []) or []:
        if isinstance(region, dict):
            evidence_ids.update(_string_list(region.get("evidence_refs")))

    for signal in substrate.get("preserved_weak_signals", []) or []:
        if isinstance(signal, dict):
            evidence_ids.update(_string_list(signal.get("evidence_refs")))

    for contradiction in substrate.get("contradictions", []) or []:
        if isinstance(contradiction, dict):
            evidence_ids.update(_string_list(contradiction.get("supporting_evidence_refs")))
            evidence_ids.update(_string_list(contradiction.get("conflicting_evidence_refs")))

    for tension in substrate.get("unresolved_tensions", []) or []:
        if isinstance(tension, dict):
            evidence_ids.update(_string_list(tension.get("evidence_refs")))

    for hypothesis in canonical_batch_state.interpretive_hypotheses:
        evidence_ids.update(_string_list(hypothesis.evidence_refs))

    return evidence_ids


def build_state_manager_context(
    canonical_batch_state: CanonicalBatchState | dict[str, Any] | str | Path,
    aggregation_handoff: dict[str, Any],
) -> dict[str, Any]:
    state = load_canonical_batch_state(canonical_batch_state)
    raw_handoff = aggregation_handoff if isinstance(aggregation_handoff, dict) else {}
    normalized_hypothesis_id = str(raw_handoff.get("hypothesis_id", "") or "").strip()
    target_hypothesis = get_interpretive_hypothesis(state, normalized_hypothesis_id)
    relevant_evidence_refs = set(_string_list(raw_handoff.get("evidence_refs")))
    if target_hypothesis is not None:
        relevant_evidence_refs.update(_string_list(target_hypothesis.evidence_refs))

    known_evidence_refs = collect_state_evidence_refs(state)
    known_evidence_refs.update(_string_list(raw_handoff.get("evidence_refs")))

    recent_revision_log = [
        entry.to_dict()
        for entry in state.revision_log
        if entry.revision_type == "initialization"
        or entry.hypothesis_id == normalized_hypothesis_id
    ][-3:]

    return {
        "batch_id": state.batch_id,
        "state_version": state.state_version,
        "target_hypothesis": target_hypothesis.to_dict() if target_hypothesis else {},
        "structural_substrate_ref": _project_structural_substrate(
            state.structural_substrate,
            relevant_evidence_refs=relevant_evidence_refs,
        ),
        "recent_revision_log": recent_revision_log,
        "aggregation_handoff": dict(raw_handoff),
        "known_evidence_refs": sorted(known_evidence_refs),
    }