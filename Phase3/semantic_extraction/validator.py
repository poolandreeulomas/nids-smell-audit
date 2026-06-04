"""Validation helpers for the Phase 3A Semantic Extraction runtime."""

from __future__ import annotations

import re
from typing import Any

from semantic_extraction.contracts import (
    VALID_LOCALITY_SCOPE_TYPES,
    VALID_REGION_KINDS,
    VALID_REGION_STATUSES,
)


_FORBIDDEN_LANGUAGE_PATTERNS = {
    "hypothesis_language": re.compile(r"\bhypothes(?:is|es|ize|ized|izing)\b", re.IGNORECASE),
    "prioritization_language": re.compile(r"\bprioriti[sz](?:e|ed|ing|ation)?\b", re.IGNORECASE),
    "planning_language": re.compile(r"\bplan(?:ning|ned|s)?\b", re.IGNORECASE),
    "routing_language": re.compile(r"\broute(?:d|s|ing)?\b|\bworker\b", re.IGNORECASE),
    "causal_language": re.compile(r"\bcaus(?:e|al|ed|ing)\b|\bmechanism\b|\broot cause\b", re.IGNORECASE),
    "artifact_family_language": re.compile(r"\bartifact(?:[- ]family)?\b", re.IGNORECASE),
    "next_step_language": re.compile(r"\bnext step\b|\binvestigate next\b", re.IGNORECASE),
    "validation_language": re.compile(r"\bvalidat(?:e|ed|es|ion)\b|\bcertif(?:y|ied)\b|\bprove[sd]?\b|\bconfirm(?:ed|s)?\b", re.IGNORECASE),
}


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _report(
    *,
    ok: bool,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
    stats: dict[str, Any] | None = None,
    invariants: dict[str, Any] | None = None,
    forbidden_language_hits: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings or [],
    }
    if stats is not None:
        payload["stats"] = stats
    if invariants is not None:
        payload["invariants"] = invariants
    if forbidden_language_hits is not None:
        payload["forbidden_language_hits"] = forbidden_language_hits
    return payload


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_string_list(value: object, *, allow_empty: bool = True) -> bool:
    if not isinstance(value, list):
        return False
    if not allow_empty and not value:
        return False
    return all(_is_non_empty_string(item) for item in value)


def _collect_forbidden_language(field_name: str, value: object) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return []
    hits: list[dict[str, str]] = []
    for code, pattern in _FORBIDDEN_LANGUAGE_PATTERNS.items():
        if pattern.search(value):
            hits.append({"field": field_name, "code": code})
    return hits


def validate_overview_summary_min(overview_summary_min: dict[str, Any]) -> dict[str, Any]:
    raw = dict(overview_summary_min or {})
    errors: list[dict[str, str]] = []

    if not _is_non_empty_string(raw.get("batch_id")):
        errors.append(
            _error("batch_id", "batch_id must be a non-empty string."))

    evidence_records = raw.get("evidence_records")
    if not isinstance(evidence_records, list) or not evidence_records:
        errors.append(_error("evidence_records",
                      "evidence_records must be a non-empty list."))
        evidence_records = []

    if not isinstance(raw.get("feature_scope_refs"), list):
        errors.append(_error("feature_scope_refs",
                      "feature_scope_refs must be a list."))
    if not isinstance(raw.get("global_observation_refs"), list):
        errors.append(_error("global_observation_refs",
                      "global_observation_refs must be a list."))

    seen_evidence_ids: set[str] = set()
    for index, record in enumerate(evidence_records):
        field_prefix = f"evidence_records[{index}]"
        if not isinstance(record, dict):
            errors.append(
                _error(field_prefix, "Each evidence record must be an object."))
            continue
        if not _is_non_empty_string(record.get("evidence_id")):
            errors.append(_error(
                f"{field_prefix}.evidence_id", "evidence_id must be a non-empty string."))
        else:
            evidence_id = str(record["evidence_id"]).strip()
            if evidence_id in seen_evidence_ids:
                errors.append(_error(
                    f"{field_prefix}.evidence_id", f"Duplicate evidence_id '{evidence_id}'."))
            seen_evidence_ids.add(evidence_id)
        if not _is_non_empty_string(record.get("source_type")):
            errors.append(_error(
                f"{field_prefix}.source_type", "source_type must be a non-empty string."))
        if not _is_non_empty_string(record.get("source_name")):
            errors.append(_error(
                f"{field_prefix}.source_name", "source_name must be a non-empty string."))
        if not _is_string_list(record.get("feature_names")):
            errors.append(_error(
                f"{field_prefix}.feature_names", "feature_names must be a list of strings."))
        if not _is_string_list(record.get("metric_names")):
            errors.append(_error(
                f"{field_prefix}.metric_names", "metric_names must be a list of strings."))
        if not _is_non_empty_string(record.get("observation_text")):
            errors.append(_error(f"{field_prefix}.observation_text",
                          "observation_text must be a non-empty string."))

    return _report(ok=not errors, errors=errors)


def validate_partition_context(partition_context: dict[str, Any]) -> dict[str, Any]:
    raw = dict(partition_context or {})
    errors: list[dict[str, str]] = []

    for key in ("semantics", "expected_properties", "epistemic_warnings", "investigation_guidance"):
        value = raw.get(key)
        if not isinstance(value, list):
            errors.append(_error(key, f"{key} must be a list."))
            continue
        if not all(_is_non_empty_string(item) for item in value):
            errors.append(
                _error(key, f"{key} must contain only non-empty strings."))

    return _report(ok=not errors, errors=errors)


def _validate_locality(locality: object, field_name: str, errors: list[dict[str, str]]) -> bool:
    if not isinstance(locality, dict):
        errors.append(_error(field_name, "locality must be an object."))
        return False
    ok = True
    scope_type = locality.get("scope_type")
    if scope_type not in VALID_LOCALITY_SCOPE_TYPES:
        errors.append(_error(f"{field_name}.scope_type",
                      "scope_type is not allowed."))
        ok = False
    if not _is_non_empty_string(locality.get("scope_value")):
        errors.append(_error(f"{field_name}.scope_value",
                      "scope_value must be a non-empty string."))
        ok = False
    if not isinstance(locality.get("localized"), bool):
        errors.append(_error(f"{field_name}.localized",
                      "localized must be a boolean."))
        ok = False
    if not _is_string_list(locality.get("notes")):
        errors.append(_error(f"{field_name}.notes",
                      "notes must be a list of strings."))
        ok = False
    return ok


def _validate_feature_scope(
    feature_scope: object,
    field_name: str,
    errors: list[dict[str, str]],
    *,
    require_feature_groups: bool,
) -> bool:
    if not isinstance(feature_scope, dict):
        errors.append(_error(field_name, "feature_scope must be an object."))
        return False

    ok = True
    if not _is_string_list(feature_scope.get("features"), allow_empty=False):
        errors.append(_error(f"{field_name}.features",
                      "features must be a non-empty list of strings."))
        ok = False
    feature_groups = feature_scope.get("feature_groups")
    if require_feature_groups:
        if not isinstance(feature_groups, list):
            errors.append(
                _error(f"{field_name}.feature_groups", "feature_groups must be a list."))
            ok = False
        elif not all(_is_non_empty_string(item) for item in feature_groups):
            errors.append(_error(f"{field_name}.feature_groups",
                          "feature_groups must contain only non-empty strings."))
            ok = False
    locality_ok = _validate_locality(feature_scope.get(
        "locality"), f"{field_name}.locality", errors)
    return ok and locality_ok


def validate_semantic_substrate(
    substrate: dict[str, Any],
    *,
    valid_evidence_ids: set[str] | None = None,
) -> dict[str, Any]:
    raw = dict(substrate or {})
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not _is_non_empty_string(raw.get("substrate_id")):
        errors.append(
            _error("substrate_id", "substrate_id must be a non-empty string."))
    if not _is_non_empty_string(raw.get("batch_id")):
        errors.append(
            _error("batch_id", "batch_id must be a non-empty string."))

    compressed_regions = raw.get("compressed_regions")
    weak_signals = raw.get("preserved_weak_signals")
    contradictions = raw.get("contradictions")
    tensions = raw.get("unresolved_tensions")

    if not isinstance(compressed_regions, list):
        errors.append(_error("compressed_regions",
                      "compressed_regions must be a list."))
        compressed_regions = []
    if not isinstance(weak_signals, list):
        errors.append(_error("preserved_weak_signals",
                      "preserved_weak_signals must be a list."))
        weak_signals = []
    if not isinstance(contradictions, list):
        errors.append(
            _error("contradictions", "contradictions must be a list."))
        contradictions = []
    if not isinstance(tensions, list):
        errors.append(_error("unresolved_tensions",
                      "unresolved_tensions must be a list."))
        tensions = []

    contradiction_ids: set[str] = set()
    tension_ids: set[str] = set()
    region_ids: set[str] = set()

    for index, contradiction in enumerate(contradictions):
        field_prefix = f"contradictions[{index}]"
        if not isinstance(contradiction, dict):
            errors.append(
                _error(field_prefix, "Each contradiction must be an object."))
            continue
        contradiction_id = contradiction.get("contradiction_id")
        if not _is_non_empty_string(contradiction_id):
            errors.append(_error(f"{field_prefix}.contradiction_id",
                          "contradiction_id must be a non-empty string."))
        else:
            contradiction_id = str(contradiction_id).strip()
            if contradiction_id in contradiction_ids:
                errors.append(_error(f"{field_prefix}.contradiction_id",
                              f"Duplicate contradiction_id '{contradiction_id}'."))
            contradiction_ids.add(contradiction_id)

    for index, tension in enumerate(tensions):
        field_prefix = f"unresolved_tensions[{index}]"
        if not isinstance(tension, dict):
            errors.append(
                _error(field_prefix, "Each tension must be an object."))
            continue
        tension_id = tension.get("tension_id")
        if not _is_non_empty_string(tension_id):
            errors.append(
                _error(f"{field_prefix}.tension_id", "tension_id must be a non-empty string."))
        else:
            tension_id = str(tension_id).strip()
            if tension_id in tension_ids:
                errors.append(
                    _error(f"{field_prefix}.tension_id", f"Duplicate tension_id '{tension_id}'."))
            tension_ids.add(tension_id)

    for index, region in enumerate(compressed_regions):
        field_prefix = f"compressed_regions[{index}]"
        if not isinstance(region, dict):
            errors.append(
                _error(field_prefix, "Each region must be an object."))
            continue
        region_id = region.get("region_id")
        if not _is_non_empty_string(region_id):
            errors.append(
                _error(f"{field_prefix}.region_id", "region_id must be a non-empty string."))
        else:
            region_id = str(region_id).strip()
            if region_id in region_ids:
                errors.append(
                    _error(f"{field_prefix}.region_id", f"Duplicate region_id '{region_id}'."))
            region_ids.add(region_id)

        if region.get("region_kind") not in VALID_REGION_KINDS:
            errors.append(
                _error(f"{field_prefix}.region_kind", "region_kind is not allowed."))
        if region.get("status") not in VALID_REGION_STATUSES:
            errors.append(
                _error(f"{field_prefix}.status", "status is not allowed."))
        if not _is_non_empty_string(region.get("summary")):
            errors.append(_error(f"{field_prefix}.summary",
                          "summary must be a non-empty string."))
        forbidden_language_hits.extend(_collect_forbidden_language(
            f"{field_prefix}.summary", region.get("summary")))

        if not _is_string_list(region.get("structural_descriptors")):
            errors.append(_error(f"{field_prefix}.structural_descriptors",
                          "structural_descriptors must be a list of strings."))
        else:
            for item in region.get("structural_descriptors", []):
                forbidden_language_hits.extend(
                    _collect_forbidden_language(
                        f"{field_prefix}.structural_descriptors", item)
                )

        _validate_feature_scope(region.get(
            "feature_scope"), f"{field_prefix}.feature_scope", errors, require_feature_groups=True)

        evidence_refs = region.get("evidence_refs")
        if not _is_string_list(evidence_refs, allow_empty=False):
            errors.append(_error(f"{field_prefix}.evidence_refs",
                          "evidence_refs must be a non-empty list of strings."))
        elif valid_evidence_ids is not None:
            for evidence_id in evidence_refs:
                if evidence_id not in valid_evidence_ids:
                    errors.append(_error(
                        f"{field_prefix}.evidence_refs", f"Unknown evidence reference '{evidence_id}'."))

        for list_field in (
            "supporting_patterns",
            "contextual_modifiers",
            "uncertainty_notes",
            "contradiction_refs",
            "tension_refs",
        ):
            if not _is_string_list(region.get(list_field)):
                errors.append(_error(
                    f"{field_prefix}.{list_field}", f"{list_field} must be a list of strings."))

        for item in region.get("contextual_modifiers", []):
            forbidden_language_hits.extend(_collect_forbidden_language(
                f"{field_prefix}.contextual_modifiers", item))
        for item in region.get("uncertainty_notes", []):
            forbidden_language_hits.extend(_collect_forbidden_language(
                f"{field_prefix}.uncertainty_notes", item))

        for contradiction_id in region.get("contradiction_refs", []):
            if contradiction_id not in contradiction_ids:
                errors.append(_error(f"{field_prefix}.contradiction_refs",
                              f"Unknown contradiction reference '{contradiction_id}'."))
        for tension_id in region.get("tension_refs", []):
            if tension_id not in tension_ids:
                errors.append(_error(
                    f"{field_prefix}.tension_refs", f"Unknown tension reference '{tension_id}'."))

    for index, weak_signal in enumerate(weak_signals):
        field_prefix = f"preserved_weak_signals[{index}]"
        if not isinstance(weak_signal, dict):
            errors.append(
                _error(field_prefix, "Each weak signal must be an object."))
            continue
        if not _is_non_empty_string(weak_signal.get("weak_signal_id")):
            errors.append(_error(
                f"{field_prefix}.weak_signal_id", "weak_signal_id must be a non-empty string."))
        if not _is_non_empty_string(weak_signal.get("descriptor")):
            errors.append(
                _error(f"{field_prefix}.descriptor", "descriptor must be a non-empty string."))
        forbidden_language_hits.extend(_collect_forbidden_language(
            f"{field_prefix}.descriptor", weak_signal.get("descriptor")))
        if not _is_non_empty_string(weak_signal.get("preservation_reason")):
            errors.append(_error(f"{field_prefix}.preservation_reason",
                          "preservation_reason must be a non-empty string."))
        forbidden_language_hits.extend(
            _collect_forbidden_language(
                f"{field_prefix}.preservation_reason", weak_signal.get("preservation_reason"))
        )

        _validate_feature_scope(weak_signal.get(
            "feature_scope"), f"{field_prefix}.feature_scope", errors, require_feature_groups=False)

        evidence_refs = weak_signal.get("evidence_refs")
        if not _is_string_list(evidence_refs, allow_empty=False):
            errors.append(_error(f"{field_prefix}.evidence_refs",
                          "evidence_refs must be a non-empty list of strings."))
        elif valid_evidence_ids is not None:
            for evidence_id in evidence_refs:
                if evidence_id not in valid_evidence_ids:
                    errors.append(_error(
                        f"{field_prefix}.evidence_refs", f"Unknown evidence reference '{evidence_id}'."))

        for list_field in ("contextual_modifiers", "uncertainty_notes"):
            if not _is_string_list(weak_signal.get(list_field)):
                errors.append(_error(
                    f"{field_prefix}.{list_field}", f"{list_field} must be a list of strings."))

    for index, contradiction in enumerate(contradictions):
        field_prefix = f"contradictions[{index}]"
        if not isinstance(contradiction, dict):
            continue
        if not _is_non_empty_string(contradiction.get("contradiction_kind")):
            errors.append(_error(f"{field_prefix}.contradiction_kind",
                          "contradiction_kind must be a non-empty string."))
        if not _is_non_empty_string(contradiction.get("description")):
            errors.append(_error(
                f"{field_prefix}.description", "description must be a non-empty string."))
        forbidden_language_hits.extend(_collect_forbidden_language(
            f"{field_prefix}.description", contradiction.get("description")))

        _validate_feature_scope(contradiction.get(
            "feature_scope"), f"{field_prefix}.feature_scope", errors, require_feature_groups=False)

        for list_field in ("supporting_evidence_refs", "conflicting_evidence_refs", "context_notes"):
            allow_empty = list_field == "context_notes"
            if not _is_string_list(contradiction.get(list_field), allow_empty=allow_empty):
                requirement = "a list of strings" if allow_empty else "a non-empty list of strings"
                errors.append(
                    _error(f"{field_prefix}.{list_field}", f"{list_field} must be {requirement}."))

        if valid_evidence_ids is not None:
            for list_field in ("supporting_evidence_refs", "conflicting_evidence_refs"):
                for evidence_id in contradiction.get(list_field, []):
                    if evidence_id not in valid_evidence_ids:
                        errors.append(_error(
                            f"{field_prefix}.{list_field}", f"Unknown evidence reference '{evidence_id}'."))

        if not _is_non_empty_string(contradiction.get("downstream_relevance")):
            errors.append(_error(f"{field_prefix}.downstream_relevance",
                          "downstream_relevance must be a non-empty string."))
        forbidden_language_hits.extend(
            _collect_forbidden_language(
                f"{field_prefix}.downstream_relevance", contradiction.get("downstream_relevance"))
        )

    for index, tension in enumerate(tensions):
        field_prefix = f"unresolved_tensions[{index}]"
        if not isinstance(tension, dict):
            continue
        if not _is_non_empty_string(tension.get("description")):
            errors.append(_error(
                f"{field_prefix}.description", "description must be a non-empty string."))
        forbidden_language_hits.extend(_collect_forbidden_language(
            f"{field_prefix}.description", tension.get("description")))
        if not _is_string_list(tension.get("related_region_ids"), allow_empty=False):
            errors.append(_error(f"{field_prefix}.related_region_ids",
                          "related_region_ids must be a non-empty list of strings."))
        else:
            for region_id in tension.get("related_region_ids", []):
                if region_id not in region_ids:
                    errors.append(_error(
                        f"{field_prefix}.related_region_ids", f"Unknown region reference '{region_id}'."))

        if not _is_string_list(tension.get("evidence_refs"), allow_empty=False):
            errors.append(_error(f"{field_prefix}.evidence_refs",
                          "evidence_refs must be a non-empty list of strings."))
        elif valid_evidence_ids is not None:
            for evidence_id in tension.get("evidence_refs", []):
                if evidence_id not in valid_evidence_ids:
                    errors.append(_error(
                        f"{field_prefix}.evidence_refs", f"Unknown evidence reference '{evidence_id}'."))

        if not _is_string_list(tension.get("context_notes")):
            errors.append(_error(
                f"{field_prefix}.context_notes", "context_notes must be a list of strings."))
        if not _is_non_empty_string(tension.get("reason_unresolved")):
            errors.append(_error(f"{field_prefix}.reason_unresolved",
                          "reason_unresolved must be a non-empty string."))
        forbidden_language_hits.extend(
            _collect_forbidden_language(
                f"{field_prefix}.reason_unresolved", tension.get("reason_unresolved"))
        )

    if forbidden_language_hits:
        for hit in forbidden_language_hits:
            warnings.append(
                _error(hit["field"], f"Semantic language flag detected ({hit['code']})."))

    stats = {
        "region_count": len(compressed_regions),
        "weak_signal_count": len(weak_signals),
        "contradiction_count": len(contradictions),
        "tension_count": len(tensions),
        "grounded_reference_count": len(valid_evidence_ids or set()),
    }
    invariants = {
        "grounded_only": not any("Unknown evidence reference" in error["message"] for error in errors),
        "contradictions_preserved": bool(contradictions),
        "minority_signals_preserved": bool(weak_signals),
        "causal_inference_introduced": any(hit["code"] == "causal_language" for hit in forbidden_language_hits),
        "context_used_only_for_interpretation": not any(
            hit["code"] == "validation_language" for hit in forbidden_language_hits
        ),
    }

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats=stats,
        invariants=invariants,
        forbidden_language_hits=forbidden_language_hits,
    )
