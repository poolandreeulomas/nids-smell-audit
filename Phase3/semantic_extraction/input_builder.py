"""Adapters that build Semantic Extraction inputs from current Phase3 surfaces."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from judge.context_loader import get_judge_partition_context
from src.explore import analyze_partition


_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")


def _split_paragraphs(text: str) -> list[str]:
    return [
        paragraph.strip()
        for paragraph in _PARAGRAPH_SPLIT_RE.split(str(text or "").strip())
        if paragraph.strip()
    ]


def build_partition_context(partition_name: str) -> dict[str, list[str]]:
    paragraphs = _split_paragraphs(get_judge_partition_context(partition_name))

    semantics: list[str] = []
    expected_properties: list[str] = []
    epistemic_warnings: list[str] = []
    investigation_guidance: list[str] = []

    if len(paragraphs) >= 1:
        semantics.append(paragraphs[0])
    if len(paragraphs) >= 4:
        semantics.append(paragraphs[3])

    if len(paragraphs) >= 5:
        expected_properties.append(paragraphs[4])

    if len(paragraphs) >= 2:
        epistemic_warnings.append(paragraphs[1])

    if len(paragraphs) >= 3:
        investigation_guidance.append(paragraphs[2])
    if len(paragraphs) >= 6:
        investigation_guidance.append(paragraphs[5])

    return {
        "partition_semantics": semantics,
        "expected_structural_properties": expected_properties,
        "epistemic_warnings": epistemic_warnings,
        "investigation_guidance": investigation_guidance,
    }


def build_overview_summary_min(dataset_path: str | Path, *, batch_id: str) -> dict[str, Any]:
    partition_name, partition_results = analyze_partition(str(dataset_path))
    evidence_records: list[dict[str, Any]] = []
    global_observation_refs: list[str] = []
    feature_scope_refs: set[str] = set()
    next_evidence_index = 1

    def add_record(
        *,
        source_type: str,
        source_name: str,
        feature_names: list[str],
        metric_names: list[str],
        observation_text: str,
        is_global: bool = False,
    ) -> None:
        nonlocal next_evidence_index
        evidence_id = f"e{next_evidence_index}"
        next_evidence_index += 1
        normalized_features = [feature_name for feature_name in feature_names if isinstance(feature_name, str) and feature_name.strip()]
        evidence_records.append(
            {
                "evidence_id": evidence_id,
                "source_type": source_type,
                "source_name": source_name,
                "feature_names": normalized_features,
                "metric_names": [metric_name for metric_name in metric_names if isinstance(metric_name, str) and metric_name.strip()],
                "observation_text": observation_text.strip(),
            }
        )
        feature_scope_refs.update(normalized_features)
        if is_global:
            global_observation_refs.append(evidence_id)

    basic_info = dict(partition_results.get("basic_info", {}) or {})
    duplicates = basic_info.get("duplicates")
    if isinstance(duplicates, int):
        add_record(
            source_type="duplication_observation",
            source_name="partition_duplicates",
            feature_names=[],
            metric_names=["duplicates"],
            observation_text=f"The deterministic partition overview found {duplicates} duplicated rows.",
            is_global=True,
        )

    class_imbalance_ratio = partition_results.get("class_imbalance_ratio")
    if class_imbalance_ratio is not None:
        add_record(
            source_type="overview_summary",
            source_name="class_imbalance_ratio",
            feature_names=[],
            metric_names=["class_imbalance_ratio"],
            observation_text=(
                "The partition-level overview reports a class imbalance ratio of "
                f"{float(class_imbalance_ratio):.4g}."
            ),
            is_global=True,
        )

    top_features = list(partition_results.get("top_features", []) or [])
    for rank, feature_name in enumerate(top_features, start=1):
        add_record(
            source_type="overview_summary",
            source_name="top_feature_rank",
            feature_names=[feature_name],
            metric_names=["top_feature_rank"],
            observation_text=f"{feature_name} appears in top_feature_rank position {rank} in the partition overview.",
        )

    feature_analysis = dict(partition_results.get("feature_analysis", {}) or {})
    for feature_name in sorted(feature_analysis.keys()):
        analysis = dict(feature_analysis.get(feature_name, {}) or {})
        variance_ratio = analysis.get("variance_ratio")
        unique_values_by_class = {
            label: stats.get("unique_values")
            for label, stats in analysis.items()
            if isinstance(stats, dict) and "unique_values" in stats
        }
        metrics = ["variance_ratio", "unique_values"]
        observation_text = (
            f"{feature_name} shows class-conditioned structural variation with variance_ratio={variance_ratio} "
            f"and unique_values_by_class={unique_values_by_class}."
        )
        add_record(
            source_type="distribution_metric",
            source_name="feature_analysis",
            feature_names=[feature_name],
            metric_names=metrics,
            observation_text=observation_text,
        )

    feature_redundancy = list(partition_results.get("feature_redundancy", []) or [])
    sorted_redundancy = sorted(
        [pair for pair in feature_redundancy if isinstance(pair, dict)],
        key=lambda pair: (-abs(float(pair.get("correlation", 0.0))), str(pair.get("feature_1", "")), str(pair.get("feature_2", ""))),
    )
    for pair in sorted_redundancy[:10]:
        feature_1 = str(pair.get("feature_1") or "").strip()
        feature_2 = str(pair.get("feature_2") or "").strip()
        correlation = float(pair.get("correlation", 0.0))
        if not feature_1 or not feature_2:
            continue
        add_record(
            source_type="dependency_observation",
            source_name="feature_redundancy",
            feature_names=[feature_1, feature_2],
            metric_names=["correlation"],
            observation_text=(
                f"{feature_1} and {feature_2} form a strong dependency pair with correlation={correlation:.4g}."
            ),
        )

    feature_cardinality = dict(partition_results.get("feature_cardinality", {}) or {})
    cardinality_rows = sorted(
        [
            (feature_name, dict(metrics or {}))
            for feature_name, metrics in feature_cardinality.items()
            if isinstance(metrics, dict)
        ],
        key=lambda item: (
            float(item[1].get("cardinality_ratio") if item[1].get("cardinality_ratio") is not None else 1.0),
            item[0],
        ),
    )
    for feature_name, metrics in cardinality_rows[:10]:
        unique_values = metrics.get("unique_values")
        cardinality_ratio = metrics.get("cardinality_ratio")
        add_record(
            source_type="cardinality_metric",
            source_name="feature_cardinality",
            feature_names=[feature_name],
            metric_names=["unique_values", "cardinality_ratio"],
            observation_text=(
                f"{feature_name} has unique_values={unique_values} and cardinality_ratio={cardinality_ratio}."
            ),
        )

    distribution_metrics = dict(partition_results.get("distribution_metrics", {}) or {})
    for feature_name in sorted(distribution_metrics.keys()):
        metrics = dict(distribution_metrics.get(feature_name, {}) or {})
        metric_names = sorted(metrics.keys())
        add_record(
            source_type="distribution_metric",
            source_name="distribution_metrics",
            feature_names=[feature_name],
            metric_names=metric_names,
            observation_text=f"{feature_name} includes distribution metrics: {metrics}.",
        )

    return {
        "batch_id": batch_id,
        "dataset_name": Path(partition_name).name,
        "overview_source": "src.explore.analyze_partition",
        "evidence_records": evidence_records,
        "feature_scope_refs": sorted(feature_scope_refs),
        "global_observation_refs": global_observation_refs,
    }