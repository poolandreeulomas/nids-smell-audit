"""Project overview evidence into a prompt-ready Semantic Extraction context."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _normalize_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        normalized.append(stripped)
    return normalized


def normalize_partition_context(partition_context: dict[str, Any] | None) -> dict[str, list[str]]:
    raw = dict(partition_context or {})
    return {
        "semantics": _normalize_string_list(raw.get("partition_semantics") or raw.get("semantics")),
        "expected_properties": _normalize_string_list(
            raw.get("expected_structural_properties") or raw.get("expected_properties")
        ),
        "epistemic_warnings": _normalize_string_list(raw.get("epistemic_warnings")),
        "investigation_guidance": _normalize_string_list(raw.get("investigation_guidance")),
    }


def _normalize_evidence_record(record: dict[str, Any]) -> dict[str, Any]:
    evidence_id = str(record.get("evidence_id") or "").strip()
    source_type = str(record.get("source_type") or "").strip()
    source_name = str(record.get("source_name") or "").strip()
    observation_text = str(record.get("observation_text") or "").strip()

    return {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "source_name": source_name,
        "feature_names": _normalize_string_list(record.get("feature_names")),
        "metric_names": _normalize_string_list(record.get("metric_names")),
        "observation_text": observation_text,
    }


def project_overview_evidence(overview_summary_min: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(overview_summary_min or {})
    normalized_records = [
        _normalize_evidence_record(record)
        for record in list(raw.get("evidence_records") or [])
        if isinstance(record, dict)
    ]
    normalized_records.sort(key=lambda record: (record["source_type"], record["source_name"], record["evidence_id"]))

    source_type_counts = Counter(record["source_type"] for record in normalized_records if record["source_type"])
    feature_frequency = Counter(
        feature_name
        for record in normalized_records
        for feature_name in record["feature_names"]
    )

    return {
        "batch_id": str(raw.get("batch_id") or "").strip(),
        "evidence_records": normalized_records,
        "evidence_count": len(normalized_records),
        "source_type_counts": dict(sorted(source_type_counts.items())),
        "feature_scope_refs": _normalize_string_list(raw.get("feature_scope_refs")),
        "global_observation_refs": _normalize_string_list(raw.get("global_observation_refs")),
        "feature_frequency": dict(sorted(feature_frequency.items())),
    }


def collect_valid_evidence_ids(projected_evidence: dict[str, Any]) -> set[str]:
    evidence_ids: set[str] = set()
    for record in list(projected_evidence.get("evidence_records") or []):
        if not isinstance(record, dict):
            continue
        evidence_id = record.get("evidence_id")
        if isinstance(evidence_id, str) and evidence_id.strip():
            evidence_ids.add(evidence_id.strip())
    return evidence_ids