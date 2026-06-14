"""Deterministic aggregation logic for the Phase 3B Coverage Builder.

Computes coverage from a collection of Partition Memories.
No LLM, no reasoning, no validation — pure data aggregation.
"""

from __future__ import annotations

from typing import Any


def _safe_str_list(value: Any) -> list[str]:
    """Convert a value to a list of strings, gracefully handling missing data."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_deduplicate(items: list[Any]) -> list[Any]:
    """Deduplicate a list by JSON representation, preserving order."""
    seen: set[str] = set()
    result: list[Any] = []
    for item in items:
        import json
        key = json.dumps(item, sort_keys=True, ensure_ascii=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _extract_artifact_families(
    partition_memory: dict[str, Any],
) -> set[str]:
    """Extract artifact family names from a partition memory."""
    families_raw = partition_memory.get("artifact_families")
    if isinstance(families_raw, list):
        family_names: set[str] = set()
        for entry in families_raw:
            if isinstance(entry, dict):
                name = entry.get("family")
                if isinstance(name, str) and name.strip():
                    family_names.add(name.strip())
            elif isinstance(entry, str) and entry.strip():
                family_names.add(entry.strip())
        return family_names
    return set()


def _extract_finding_names(
    partition_memory: dict[str, Any],
) -> set[str]:
    """Extract canonical finding names from a partition memory."""
    findings_raw = partition_memory.get("major_findings")
    if isinstance(findings_raw, list):
        names: set[str] = set()
        for finding in findings_raw:
            if isinstance(finding, dict):
                name = finding.get("canonical_name")
                if isinstance(name, str) and name.strip():
                    names.add(name.strip())
            elif isinstance(finding, str) and finding.strip():
                names.add(finding.strip())
        return names
    return set()


def _extract_partition_summary(
    partition_memory: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact partition summary."""
    assessment = partition_memory.get("overall_assessment", {})
    if not isinstance(assessment, dict):
        assessment = {}

    families_raw = partition_memory.get("artifact_families")
    families_count = len(families_raw) if isinstance(families_raw, list) else 0

    findings_raw = partition_memory.get("major_findings")
    findings_count = len(findings_raw) if isinstance(findings_raw, list) else 0

    risks_raw = partition_memory.get("open_risks")
    risks_count = len(risks_raw) if isinstance(risks_raw, list) else 0

    return {
        "partition_id": str(partition_memory.get("partition_id", "")),
        "recommendation": str(partition_memory.get("recommendation", "")),
        "risk_level": str(assessment.get("risk_level", "")),
        "confidence_level": str(assessment.get("confidence_level", "")),
        "major_findings_count": findings_count,
        "artifact_families_count": families_count,
        "open_risks_count": risks_count,
    }


def _extract_coverage_signals(
    partition_memory: dict[str, Any],
) -> list[Any]:
    """Extract coverage signals from a partition memory."""
    signals_raw = partition_memory.get("coverage_signals")
    if isinstance(signals_raw, list):
        return list(signals_raw)
    return []


def build_dataset_memory(
    partition_memories: list[dict[str, Any]],
    *,
    partitions_available: int | None = None,
) -> dict[str, Any]:
    """Build a Dataset Memory from a list of Partition Memories.

    Args:
        partition_memories: List of parsed Partition Memory dicts.
            Each should contain partition_id, recommendation,
            overall_assessment, artifact_families, major_findings,
            open_risks, coverage_signals.
        partitions_available: Optional explicit count of partitions
            in the dataset. If None, uses len(partition_memories).

    Returns:
        Dataset Memory dict with execution_metadata,
        artifact_family_coverage, finding_coverage,
        partition_summaries, global_signals.
    """
    total = partitions_available if partitions_available is not None else len(partition_memories)

    # Separate successful and failed
    successful: list[dict[str, Any]] = []
    for pm in partition_memories:
        if isinstance(pm, dict) and "error" not in pm and pm.get("partition_id"):
            successful.append(pm)

    completed = len(successful)
    failed = total - completed

    # --- Artifact Family Coverage ---
    all_family_names: set[str] = set()
    for pm in successful:
        all_family_names |= _extract_artifact_families(pm)

    sorted_families = sorted(all_family_names)
    artifact_family_coverage: list[dict[str, str]] = []
    for family in sorted_families:
        count = sum(
            1 for pm in successful if family in _extract_artifact_families(pm)
        )
        artifact_family_coverage.append({
            "family": family,
            "coverage": f"{count}/{total}",
        })

    # --- Finding Coverage ---
    all_finding_names: set[str] = set()
    for pm in successful:
        all_finding_names |= _extract_finding_names(pm)

    sorted_findings = sorted(all_finding_names)
    finding_coverage: list[dict[str, str]] = []
    for finding in sorted_findings:
        count = sum(
            1 for pm in successful if finding in _extract_finding_names(pm)
        )
        finding_coverage.append({
            "finding": finding,
            "coverage": f"{count}/{total}",
        })

    # --- Partition Summaries ---
    partition_summaries: list[dict[str, Any]] = []
    for pm in successful:
        partition_summaries.append(_extract_partition_summary(pm))

    # --- Global Signals ---
    all_signals: list[Any] = []
    for pm in successful:
        all_signals.extend(_extract_coverage_signals(pm))
    global_signals = _json_deduplicate(all_signals)

    return {
        "execution_metadata": {
            "partitions_available": total,
            "partitions_completed": completed,
            "partitions_failed": failed,
        },
        "artifact_family_coverage": artifact_family_coverage,
        "finding_coverage": finding_coverage,
        "partition_summaries": partition_summaries,
        "global_signals": global_signals,
    }