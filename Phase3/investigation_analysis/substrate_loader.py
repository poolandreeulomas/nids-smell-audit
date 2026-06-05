"""Prompt-ready projection helpers for Investigation Analysis."""

from __future__ import annotations

from typing import Any


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


def _string_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _compact_feature_scope(feature_scope: object) -> dict[str, Any]:
    raw_scope = feature_scope if isinstance(feature_scope, dict) else {}
    raw_locality = raw_scope.get("locality") if isinstance(
        raw_scope.get("locality"), dict) else {}
    return {
        "features": _string_list(raw_scope.get("features")),
        "feature_groups": _string_list(raw_scope.get("feature_groups")),
        "locality": {
            "scope_type": _string_value(raw_locality.get("scope_type")),
            "scope_value": _string_value(raw_locality.get("scope_value")),
            "localized": raw_locality.get("localized") if isinstance(raw_locality.get("localized"), bool) else False,
            "notes": _string_list(raw_locality.get("notes")),
        },
    }


def project_semantic_substrate(semantic_substrate: dict[str, Any]) -> dict[str, Any]:
    raw = semantic_substrate if isinstance(semantic_substrate, dict) else {}
    compressed_regions = raw.get("compressed_regions") if isinstance(
        raw.get("compressed_regions"), list) else []
    weak_signals = raw.get("preserved_weak_signals") if isinstance(
        raw.get("preserved_weak_signals"), list) else []
    contradictions = raw.get("contradictions") if isinstance(
        raw.get("contradictions"), list) else []
    tensions = raw.get("unresolved_tensions") if isinstance(
        raw.get("unresolved_tensions"), list) else []

    return {
        "substrate_id": _string_value(raw.get("substrate_id")),
        "batch_id": _string_value(raw.get("batch_id")),
        "region_count": len(compressed_regions),
        "weak_signal_count": len(weak_signals),
        "contradiction_count": len(contradictions),
        "tension_count": len(tensions),
        "compressed_regions": [
            {
                "region_id": _string_value(region.get("region_id")) if isinstance(region, dict) else "",
                "region_kind": _string_value(region.get("region_kind")) if isinstance(region, dict) else "",
                "status": _string_value(region.get("status")) if isinstance(region, dict) else "",
                "summary": _string_value(region.get("summary")) if isinstance(region, dict) else "",
                "feature_scope": _compact_feature_scope(region.get("feature_scope") if isinstance(region, dict) else {}),
                "evidence_refs": _string_list(region.get("evidence_refs") if isinstance(region, dict) else []),
                "contradiction_refs": _string_list(region.get("contradiction_refs") if isinstance(region, dict) else []),
                "tension_refs": _string_list(region.get("tension_refs") if isinstance(region, dict) else []),
            }
            for region in compressed_regions
        ],
        "preserved_weak_signals": [
            {
                "weak_signal_id": _string_value(signal.get("weak_signal_id")) if isinstance(signal, dict) else "",
                "descriptor": _string_value(signal.get("descriptor")) if isinstance(signal, dict) else "",
                "feature_scope": _compact_feature_scope(signal.get("feature_scope") if isinstance(signal, dict) else {}),
                "evidence_refs": _string_list(signal.get("evidence_refs") if isinstance(signal, dict) else []),
                "preservation_reason": _string_value(signal.get("preservation_reason")) if isinstance(signal, dict) else "",
            }
            for signal in weak_signals
        ],
        "contradictions": [
            {
                "contradiction_id": _string_value(item.get("contradiction_id")) if isinstance(item, dict) else "",
                "contradiction_kind": _string_value(item.get("contradiction_kind")) if isinstance(item, dict) else "",
                "description": _string_value(item.get("description")) if isinstance(item, dict) else "",
                "supporting_evidence_refs": _string_list(item.get("supporting_evidence_refs") if isinstance(item, dict) else []),
                "conflicting_evidence_refs": _string_list(item.get("conflicting_evidence_refs") if isinstance(item, dict) else []),
            }
            for item in contradictions
        ],
        "unresolved_tensions": [
            {
                "tension_id": _string_value(item.get("tension_id")) if isinstance(item, dict) else "",
                "description": _string_value(item.get("description")) if isinstance(item, dict) else "",
                "related_region_ids": _string_list(item.get("related_region_ids") if isinstance(item, dict) else []),
                "evidence_refs": _string_list(item.get("evidence_refs") if isinstance(item, dict) else []),
            }
            for item in tensions
        ],
    }


def project_analysis_context_min(analysis_context_min: dict[str, Any]) -> dict[str, Any]:
    raw = analysis_context_min if isinstance(
        analysis_context_min, dict) else {}
    partition_context_ref = raw.get("partition_context_ref") if isinstance(
        raw.get("partition_context_ref"), dict) else {}
    artifact_framing_refs = raw.get("artifact_framing_refs") if isinstance(
        raw.get("artifact_framing_refs"), list) else []

    return {
        "partition_context_ref": {
            "semantics": _string_list(partition_context_ref.get("semantics")),
            "expected_properties": _string_list(partition_context_ref.get("expected_properties")),
            "epistemic_warnings": _string_list(partition_context_ref.get("epistemic_warnings")),
            "investigation_guidance": _string_list(partition_context_ref.get("investigation_guidance")),
        },
        "artifact_framing_refs": [
            {
                "framing_id": _string_value(item.get("framing_id")) if isinstance(item, dict) else "",
                "label": _string_value(item.get("label")) if isinstance(item, dict) else "",
                "description": _string_value(item.get("description")) if isinstance(item, dict) else "",
            }
            for item in artifact_framing_refs
        ],
    }


def project_analysis_iteration_context_min(analysis_iteration_context_min: dict[str, Any] | None) -> dict[str, Any]:
    raw = analysis_iteration_context_min if isinstance(
        analysis_iteration_context_min, dict) else {}
    initial_hypothesis_set_ref = (
        raw.get("initial_hypothesis_set_ref")
        if isinstance(raw.get("initial_hypothesis_set_ref"), dict)
        else {}
    )
    current_state_ref = raw.get("current_state_ref") if isinstance(
        raw.get("current_state_ref"), dict) else {}

    return {
        "initial_hypothesis_set_ref": {
            "analysis_id": _string_value(initial_hypothesis_set_ref.get("analysis_id")),
            "hypothesis_refs": [
                {
                    "hypothesis_id": _string_value(item.get("hypothesis_id")) if isinstance(item, dict) else "",
                    "summary": _string_value(item.get("summary")) if isinstance(item, dict) else "",
                }
                for item in (
                    initial_hypothesis_set_ref.get("hypothesis_refs")
                    if isinstance(initial_hypothesis_set_ref.get("hypothesis_refs"), list)
                    else []
                )
            ],
        },
        "current_state_ref": {
            "state_id": _string_value(current_state_ref.get("state_id")),
            "state_notes": _string_list(current_state_ref.get("state_notes")),
        },
        "critic_guidance": _string_list(raw.get("critic_guidance")),
    }


def collect_valid_evidence_ids(semantic_substrate: dict[str, Any]) -> set[str]:
    raw = semantic_substrate if isinstance(semantic_substrate, dict) else {}
    evidence_ids: set[str] = set()

    for region in raw.get("compressed_regions", []):
        if isinstance(region, dict):
            evidence_ids.update(_string_list(region.get("evidence_refs")))

    for signal in raw.get("preserved_weak_signals", []):
        if isinstance(signal, dict):
            evidence_ids.update(_string_list(signal.get("evidence_refs")))

    for contradiction in raw.get("contradictions", []):
        if isinstance(contradiction, dict):
            evidence_ids.update(_string_list(
                contradiction.get("supporting_evidence_refs")))
            evidence_ids.update(_string_list(
                contradiction.get("conflicting_evidence_refs")))

    for tension in raw.get("unresolved_tensions", []):
        if isinstance(tension, dict):
            evidence_ids.update(_string_list(tension.get("evidence_refs")))

    return evidence_ids


def build_hypothesis_index(hypothesis_set: dict[str, Any]) -> dict[str, Any]:
    raw = hypothesis_set if isinstance(hypothesis_set, dict) else {}
    raw_hypotheses = raw.get("hypotheses") if isinstance(
        raw.get("hypotheses"), list) else []
    hypotheses: list[dict[str, Any]] = []

    for hypothesis in raw_hypotheses:
        if not isinstance(hypothesis, dict):
            continue
        hypotheses.append(
            {
                "hypothesis_id": _string_value(hypothesis.get("hypothesis_id")),
                "evidence_refs": sorted(set(_string_list(hypothesis.get("evidence_refs")))),
                "open_questions": _string_list(hypothesis.get("open_questions")),
            }
        )

    overlap_pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(hypotheses):
        left_evidence = set(left["evidence_refs"])
        if not left_evidence:
            continue
        for right in hypotheses[left_index + 1:]:
            shared_evidence = sorted(
                left_evidence.intersection(right["evidence_refs"]))
            if shared_evidence:
                overlap_pairs.append(
                    {
                        "left_hypothesis_id": left["hypothesis_id"],
                        "right_hypothesis_id": right["hypothesis_id"],
                        "shared_evidence_refs": shared_evidence,
                    }
                )

    return {
        "hypothesis_count": len(hypotheses),
        "evidence_ref_coverage": sorted(
            {
                evidence_ref
                for hypothesis in hypotheses
                for evidence_ref in hypothesis["evidence_refs"]
            }
        ),
        "overlap_pairs": overlap_pairs,
        "hypotheses": [
            {
                "hypothesis_id": hypothesis["hypothesis_id"],
                "evidence_refs": hypothesis["evidence_refs"],
                "open_question_count": len(hypothesis["open_questions"]),
            }
            for hypothesis in hypotheses
        ],
    }
