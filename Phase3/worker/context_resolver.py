"""Runtime-only local context resolution helpers for Worker execution."""

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
        stripped = _string_value(value)
        if stripped:
            normalized.append(stripped)
    return normalized


def _feature_scope_payload(feature_scope: object) -> tuple[list[str], list[str], dict[str, Any]]:
    raw_scope = feature_scope if isinstance(feature_scope, dict) else {}
    raw_locality = raw_scope.get("locality") if isinstance(raw_scope.get("locality"), dict) else {}
    return (
        _string_list(raw_scope.get("features")),
        _string_list(raw_scope.get("feature_groups")),
        {
            "scope_type": _string_value(raw_locality.get("scope_type")),
            "scope_value": _string_value(raw_locality.get("scope_value")),
            "localized": raw_locality.get("localized") if isinstance(raw_locality.get("localized"), bool) else False,
            "notes": _string_list(raw_locality.get("notes")),
        },
    )


def _merge_local_context_entry(
    target: dict[str, Any],
    *,
    features: list[str],
    feature_groups: list[str],
    locality: dict[str, Any],
    source_kind: str,
    source_id: str,
    summary: str,
) -> None:
    target_features = set(target.setdefault("feature_names", []))
    target_features.update(features)
    target["feature_names"] = sorted(target_features)

    target_groups = set(target.setdefault("feature_groups", []))
    target_groups.update(feature_groups)
    target["feature_groups"] = sorted(target_groups)

    if not target.get("locality"):
        target["locality"] = dict(locality)
    source_items = target.setdefault("source_items", [])
    source_items.append(
        {
            "source_kind": source_kind,
            "source_id": source_id,
            "summary": summary,
        }
    )


def build_evidence_context_index(semantic_substrate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = semantic_substrate if isinstance(semantic_substrate, dict) else {}
    index: dict[str, dict[str, Any]] = {}

    def get_entry(context_ref: str) -> dict[str, Any]:
        entry = index.get(context_ref)
        if entry is None:
            entry = {
                "context_ref": context_ref,
                "feature_names": [],
                "feature_groups": [],
                "locality": {},
                "source_items": [],
            }
            index[context_ref] = entry
        return entry

    for region in raw.get("compressed_regions", []):
        if not isinstance(region, dict):
            continue
        features, feature_groups, locality = _feature_scope_payload(region.get("feature_scope"))
        summary = _string_value(region.get("summary"))
        source_id = _string_value(region.get("region_id"))
        for context_ref in _string_list(region.get("evidence_refs")):
            _merge_local_context_entry(
                get_entry(context_ref),
                features=features,
                feature_groups=feature_groups,
                locality=locality,
                source_kind="compressed_region",
                source_id=source_id,
                summary=summary,
            )

    for signal in raw.get("preserved_weak_signals", []):
        if not isinstance(signal, dict):
            continue
        features, feature_groups, locality = _feature_scope_payload(signal.get("feature_scope"))
        summary = _string_value(signal.get("descriptor")) or _string_value(signal.get("preservation_reason"))
        source_id = _string_value(signal.get("weak_signal_id"))
        for context_ref in _string_list(signal.get("evidence_refs")):
            _merge_local_context_entry(
                get_entry(context_ref),
                features=features,
                feature_groups=feature_groups,
                locality=locality,
                source_kind="preserved_weak_signal",
                source_id=source_id,
                summary=summary,
            )

    for contradiction in raw.get("contradictions", []):
        if not isinstance(contradiction, dict):
            continue
        features, feature_groups, locality = _feature_scope_payload(contradiction.get("feature_scope"))
        description = _string_value(contradiction.get("description"))
        contradiction_id = _string_value(contradiction.get("contradiction_id"))
        for context_ref in _string_list(contradiction.get("supporting_evidence_refs")):
            _merge_local_context_entry(
                get_entry(context_ref),
                features=features,
                feature_groups=feature_groups,
                locality=locality,
                source_kind="contradiction_support",
                source_id=contradiction_id,
                summary=description,
            )
        for context_ref in _string_list(contradiction.get("conflicting_evidence_refs")):
            _merge_local_context_entry(
                get_entry(context_ref),
                features=features,
                feature_groups=feature_groups,
                locality=locality,
                source_kind="contradiction_conflict",
                source_id=contradiction_id,
                summary=description,
            )

    for tension in raw.get("unresolved_tensions", []):
        if not isinstance(tension, dict):
            continue
        description = _string_value(tension.get("description"))
        source_id = _string_value(tension.get("tension_id"))
        locality = {
            "scope_type": "tension",
            "scope_value": source_id,
            "localized": False,
            "notes": _string_list(tension.get("context_notes")),
        }
        for context_ref in _string_list(tension.get("evidence_refs")):
            _merge_local_context_entry(
                get_entry(context_ref),
                features=[],
                feature_groups=[],
                locality=locality,
                source_kind="unresolved_tension",
                source_id=source_id,
                summary=description,
            )

    return index


def build_local_context_records(
    semantic_substrate: dict[str, Any],
    local_context_refs: list[str],
) -> list[dict[str, Any]]:
    index = build_evidence_context_index(semantic_substrate)
    records: list[dict[str, Any]] = []
    for context_ref in local_context_refs:
        if context_ref in index:
            records.append(index[context_ref])
            continue
        records.append(
            {
                "context_ref": context_ref,
                "feature_names": [],
                "feature_groups": [],
                "locality": {},
                "source_items": [],
            }
        )
    return records