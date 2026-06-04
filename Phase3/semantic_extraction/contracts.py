"""Minimal contracts for the Phase 3A Semantic Extraction runtime."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "phase3a.semantic_extraction.v1"

VALID_REGION_KINDS = {
    "redundancy_region",
    "dependency_region",
    "concentration_region",
    "low_diversity_region",
    "localized_separability_region",
    "representation_sensitive_region",
    "topology_motif_region",
    "mixed_structural_region",
}

VALID_REGION_STATUSES = {
    "emerging",
    "active",
    "localized",
    "uncertain",
    "contradictory",
    "broad_unvalidated",
}

VALID_LOCALITY_SCOPE_TYPES = {
    "feature_group",
    "derived_family",
    "dependency_cluster",
    "representation_cluster",
    "partition_global",
    "mixed",
}


def _string_list(values: list[str] | None = None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def build_locality_descriptor(
    *,
    scope_type: str,
    scope_value: str,
    localized: bool,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "scope_type": scope_type,
        "scope_value": scope_value,
        "localized": localized,
        "notes": _string_list(notes),
    }


def build_feature_scope(
    *,
    features: list[str] | None = None,
    feature_groups: list[str] | None = None,
    locality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "features": _string_list(features),
        "feature_groups": _string_list(feature_groups),
        "locality": dict(locality or {}),
    }


def build_region(
    *,
    region_id: str,
    region_kind: str,
    status: str,
    summary: str,
    structural_descriptors: list[str] | None = None,
    feature_scope: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    supporting_patterns: list[str] | None = None,
    contextual_modifiers: list[str] | None = None,
    uncertainty_notes: list[str] | None = None,
    contradiction_refs: list[str] | None = None,
    tension_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "region_kind": region_kind,
        "status": status,
        "summary": summary,
        "structural_descriptors": _string_list(structural_descriptors),
        "feature_scope": build_feature_scope(**feature_scope) if feature_scope else build_feature_scope(),
        "evidence_refs": _string_list(evidence_refs),
        "supporting_patterns": _string_list(supporting_patterns),
        "contextual_modifiers": _string_list(contextual_modifiers),
        "uncertainty_notes": _string_list(uncertainty_notes),
        "contradiction_refs": _string_list(contradiction_refs),
        "tension_refs": _string_list(tension_refs),
    }


def build_weak_signal(
    *,
    weak_signal_id: str,
    descriptor: str,
    feature_scope: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    preservation_reason: str,
    contextual_modifiers: list[str] | None = None,
    uncertainty_notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "weak_signal_id": weak_signal_id,
        "descriptor": descriptor,
        "feature_scope": dict(feature_scope or {}),
        "evidence_refs": _string_list(evidence_refs),
        "preservation_reason": preservation_reason,
        "contextual_modifiers": _string_list(contextual_modifiers),
        "uncertainty_notes": _string_list(uncertainty_notes),
    }


def build_contradiction(
    *,
    contradiction_id: str,
    contradiction_kind: str,
    description: str,
    feature_scope: dict[str, Any] | None = None,
    supporting_evidence_refs: list[str] | None = None,
    conflicting_evidence_refs: list[str] | None = None,
    context_notes: list[str] | None = None,
    downstream_relevance: str,
) -> dict[str, Any]:
    return {
        "contradiction_id": contradiction_id,
        "contradiction_kind": contradiction_kind,
        "description": description,
        "feature_scope": dict(feature_scope or {}),
        "supporting_evidence_refs": _string_list(supporting_evidence_refs),
        "conflicting_evidence_refs": _string_list(conflicting_evidence_refs),
        "context_notes": _string_list(context_notes),
        "downstream_relevance": downstream_relevance,
    }


def build_tension(
    *,
    tension_id: str,
    description: str,
    related_region_ids: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    context_notes: list[str] | None = None,
    reason_unresolved: str,
) -> dict[str, Any]:
    return {
        "tension_id": tension_id,
        "description": description,
        "related_region_ids": _string_list(related_region_ids),
        "evidence_refs": _string_list(evidence_refs),
        "context_notes": _string_list(context_notes),
        "reason_unresolved": reason_unresolved,
    }


def build_semantic_substrate(
    *,
    substrate_id: str,
    batch_id: str,
    compressed_regions: list[dict[str, Any]] | None = None,
    preserved_weak_signals: list[dict[str, Any]] | None = None,
    contradictions: list[dict[str, Any]] | None = None,
    unresolved_tensions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "substrate_id": substrate_id,
        "batch_id": batch_id,
        "compressed_regions": [dict(item) for item in (compressed_regions or [])],
        "preserved_weak_signals": [dict(item) for item in (preserved_weak_signals or [])],
        "contradictions": [dict(item) for item in (contradictions or [])],
        "unresolved_tensions": [dict(item) for item in (unresolved_tensions or [])],
    }