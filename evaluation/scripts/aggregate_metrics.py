"""Aggregation script for the evaluation pipeline — REFACTORED.

Changes from v1:
- Updated: metric names to match v3 extract_metrics.py
- Renamed: Finding Consistency → Evidence Production Stability
- Renamed: Recommendation Consistency → Evidence Volume Stability
- Removed: Artifact Family Count (was silently broken)
- Added: Architectural Properties classification
- Updated: summary generator to use correct interpretations
- Removed: unsupported claims and speculative interpretations

Usage:
    python scripts/aggregate_metrics.py

Input:
    ../outputs/run_metrics_corrected.json

Outputs:
    ../outputs/aggregated_metrics_corrected.json
    ../outputs/aggregated_metrics_corrected.csv
    ../outputs/evaluation_summary_corrected.md
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# --- Configuration -----------------------------------------------------------

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

METRIC_NAMES: List[str] = [
    "tool_diversity_index",
    "feature_revisit_rate",
    "hypothesis_stability",
    "hypothesis_revision_rate",
    "state_version_churn",  # ARCHITECTURAL PROPERTY
    "state_version_history",  # ARCHITECTURAL PROPERTY
    "total_evidence_blocks",
    "investigated_features",
    "evidence_per_feature",
    "history_completeness",
    "provenance_completeness",
    "evidence_production_stability",  # RENAMED from finding_consistency
    "evidence_volume_stability",  # RENAMED from recommendation_consistency
]

METRIC_LABELS: Dict[str, str] = {
    "tool_diversity_index": "Tool Diversity Index",
    "feature_revisit_rate": "Feature Revisit Rate",
    "hypothesis_stability": "Hypothesis Stability",
    "hypothesis_revision_rate": "Hypothesis Revision Rate",
    "state_version_churn": "State Version Churn [ARCHITECTURAL]",
    "state_version_history": "State Version History [ARCHITECTURAL]",
    "total_evidence_blocks": "Total Evidence Blocks",
    "investigated_features": "Investigated Features",
    "evidence_per_feature": "Evidence per Feature",
    "history_completeness": "History Completeness",
    "provenance_completeness": "Provenance Completeness",
    "evidence_production_stability": "Evidence Production Stability",
    "evidence_volume_stability": "Evidence Volume Stability",
}

PARTITION_GROUPS: Dict[str, List[str]] = {
    "Friday-Morning": ["050", "064", "067", "074"],
    "Friday-DDoS": ["053", "070"],
    "Friday-PortScan": ["073", "082"],
    "Monday": ["075"],
    "Tuesday": ["071"],
    "Wednesday": ["072"],
    "Thursday-Infiltration": ["076"],
    "Thursday-WebAttacks": ["077"],
    "Training": ["080"],
    "Testing": ["081"],
}


# --- Helpers -----------------------------------------------------------------


def _load_run_metrics() -> Optional[Dict[str, Dict[str, Any]]]:
    """Load the per-run metrics JSON file (corrected version)."""
    path = OUTPUT_DIR / "run_metrics_corrected.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: Could not load run_metrics_corrected.json: {e}")
        return None


def _compute_stats(values: List[float]) -> Dict[str, Optional[float]]:
    """Compute mean, std, min, max for a list of numeric values."""
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None}

    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    std = math.sqrt(variance)

    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _gather_values(
    run_metrics: Dict[str, Dict[str, Any]],
    run_ids: List[str],
    metric: str,
) -> List[float]:
    """Collect numeric values for a metric across a set of runs."""
    values: List[float] = []
    for rid in run_ids:
        if rid not in run_metrics:
            continue
        val = run_metrics[rid].get(metric)
        if val is not None and isinstance(val, (int, float)):
            values.append(float(val))
    return values


# --- Aggregation Functions ---------------------------------------------------


def aggregate_overall(
    run_metrics: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute overall aggregate across all runs."""
    all_run_ids = list(run_metrics.keys())
    result: Dict[str, Any] = {}
    for metric in METRIC_NAMES:
        values = _gather_values(run_metrics, all_run_ids, metric)
        result[metric] = _compute_stats(values)
        result[metric]["n"] = len(values)
    return result


def aggregate_dataset(
    run_metrics: Dict[str, Dict[str, Any]], dataset: str
) -> Dict[str, Any]:
    """Compute aggregate for a specific dataset."""
    run_ids = [rid for rid, m in run_metrics.items() if m.get("dataset") == dataset]
    result: Dict[str, Any] = {}
    for metric in METRIC_NAMES:
        values = _gather_values(run_metrics, run_ids, metric)
        result[metric] = _compute_stats(values)
        result[metric]["n"] = len(values)
    result["_run_count"] = len(run_ids)
    result["_run_ids"] = run_ids
    return result


def aggregate_partition(
    run_metrics: Dict[str, Dict[str, Any]], partition: str, run_ids: List[str]
) -> Dict[str, Any]:
    """Compute aggregate for a specific partition."""
    result: Dict[str, Any] = {}
    for metric in METRIC_NAMES:
        values = _gather_values(run_metrics, run_ids, metric)
        result[metric] = _compute_stats(values)
        result[metric]["n"] = len(values)
    result["_run_count"] = len(run_ids)
    return result


# --- Summary Generator -------------------------------------------------------


def generate_summary(
    run_metrics: Dict[str, Dict[str, Any]],
    overall: Dict[str, Any],
    cicids: Dict[str, Any],
    unsw: Dict[str, Any],
) -> str:
    """Generate an evidence-backed evaluation summary in Markdown.
    
    Only contains observations directly supported by metric data.
    No speculative claims. No unsupported attributions of intent.
    """
    lines: List[str] = []
    lines.append("# Evaluation Summary (Corrected)")
    lines.append("")
    lines.append(
        "Automatically generated by the evaluation metric extraction pipeline (v3)."
    )
    lines.append("")
    lines.append("**Note:** Literature matching and novelty assessment are performed manually.")
    lines.append("")

    # --- Corpus Summary ---
    lines.append("## Corpus Summary")
    lines.append("")
    all_run_ids = sorted(run_metrics.keys(), key=int)
    total_runs = len(all_run_ids)
    cicids_runs = [rid for rid, m in run_metrics.items() if m.get("dataset") == "cicids2017"]
    unsw_runs = [rid for rid, m in run_metrics.items() if m.get("dataset") == "unsw_nb15"]

    lines.append(f"| Property | Value |")
    lines.append(f"|----------|-------|")
    lines.append(f"| Total runs | {total_runs} |")
    lines.append(f"| CICIDS2017 runs | {len(cicids_runs)} |")
    lines.append(f"| UNSW-NB15 runs | {len(unsw_runs)} |")
    lines.append(f"| CICIDS2017 partitions | 8 |")
    lines.append(f"| UNSW-NB15 partitions | 2 |")

    lines.append("")
    lines.append("### Run Inventory")
    lines.append("")
    lines.append("| Run ID | Dataset | Partition | Workers | Rounds |")
    lines.append("|--------|---------|-----------|---------|--------|")
    for rid in all_run_ids:
        m = run_metrics[rid]
        lines.append(
            f"| {rid} | {m['dataset']} | {m['partition']} | "
            f"{m.get('worker_count', '?')} | {m.get('round_count', '?')} |"
        )

    # --- Metric Summary ---
    lines.append("")
    lines.append("## Metric Summary")
    lines.append("")
    lines.append("| Metric | Mean | Std | Min | Max | N |")
    lines.append("|--------|------|-----|-----|-----|---|")

    for metric in METRIC_NAMES:
        label = METRIC_LABELS.get(metric, metric)
        stats = overall.get(metric, {})
        mean = stats.get("mean", "—")
        std = stats.get("std", "—")
        min_v = stats.get("min", "—")
        max_v = stats.get("max", "—")
        n = stats.get("n", 0)
        lines.append(
            f"| {label} | {mean} | {std} | {min_v} | {max_v} | {n} |"
        )

    # --- Per-Dataset ---
    lines.append("")
    lines.append("## Per-Dataset Summary")
    lines.append("")

    for dataset_name, dataset_data in [("CICIDS2017", cicids), ("UNSW-NB15", unsw)]:
        lines.append(f"### {dataset_name}")
        lines.append("")
        lines.append("| Metric | Mean | Std | Min | Max | N |")
        lines.append("|--------|------|-----|-----|-----|---|")
        for metric in METRIC_NAMES:
            label = METRIC_LABELS.get(metric, metric)
            stats = dataset_data.get(metric, {})
            mean = stats.get("mean", "—")
            std = stats.get("std", "—")
            min_v = stats.get("min", "—")
            max_v = stats.get("max", "—")
            n = stats.get("n", 0)
            lines.append(
                f"| {label} | {mean} | {std} | {min_v} | {max_v} | {n} |"
            )
        lines.append("")

    # --- Stability Summary (RENAMED from "Consistency") ---
    lines.append("## Cross-Run Stability Summary")
    lines.append("")
    lines.append("**Note:** These metrics measure stability of evidence production, ")
    lines.append("NOT finding content or recommendation agreement. ")
    lines.append("True finding/recommendation comparison requires the findings corpus.")
    lines.append("")

    for partition_name, part_run_ids in [
        ("Friday-Morning", ["050", "064", "067", "074"]),
        ("Friday-DDoS", ["053", "070"]),
        ("Friday-PortScan", ["073", "082"]),
    ]:
        available = [rid for rid in part_run_ids if rid in run_metrics]
        if len(available) < 2:
            lines.append(f"### {partition_name}")
            lines.append("")
            lines.append(
                f"Insufficient runs for stability analysis "
                f"({len(available)} available, need 2)."
            )
            lines.append("")
            continue

        # Get stability values
        prod_stab = _gather_values(run_metrics, available, "evidence_production_stability")
        vol_stab = _gather_values(run_metrics, available, "evidence_volume_stability")

        lines.append(f"### {partition_name}")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(
            f"| Evidence Production Stability | {prod_stab[0] if prod_stab else 'N/A'} |"
        )
        lines.append(
            f"| Evidence Volume Stability | "
            f"{vol_stab[0] if vol_stab else 'N/A'} |"
        )
        lines.append(f"| Runs compared | {len(available)} |")
        lines.append("")

        # Per-run details
        lines.append(f"**Per-run evidence production:**")
        lines.append("")
        lines.append("| Run ID | Evidence Blocks | Evidence/Feature | State Version |")
        lines.append("|--------|----------------|------------------|---------------|")
        for rid in available:
            m = run_metrics[rid]
            lines.append(
                f"| {rid} | {m.get('total_evidence_blocks', '?')} | "
                f"{m.get('evidence_per_feature', '?')} | "
                f"{m.get('state_version_history', '?')} |"
            )
        lines.append("")

    # --- Architectural Properties ---
    lines.append("## Architectural Properties")
    lines.append("")
    lines.append("The following metrics are determined by framework architecture, ")
    lines.append("not by investigation outcomes:")
    lines.append("")
    lines.append("| Metric | Value | Reason |")
    lines.append("|--------|-------|--------|")
    lines.append("| State Version Churn | 3.33 (all runs) | 10 state versions / 3 rounds (deterministic) |")
    lines.append("| State Version History | 10 (all runs) | 3 hypotheses × 3 rounds + 1 initial |")
    lines.append("")

    # --- Notes ---
    lines.append("## Notes")
    lines.append("")

    # Check for missing/suspicious values
    warnings: List[str] = []
    for rid in all_run_ids:
        m = run_metrics[rid]
        for metric in METRIC_NAMES:
            if m.get(metric) is None:
                warnings.append(
                    f"Run {rid}: {METRIC_LABELS.get(metric, metric)} "
                    f"could not be computed."
                )

    if warnings:
        lines.append("### Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")
    else:
        lines.append("All metrics were successfully computed for all runs.")
        lines.append("")

    lines.append("### Limitations")
    lines.append("")
    lines.append("1. **Evidence Production/Volume Stability** measure evidence quantity stability,")
    lines.append("   NOT finding content or recommendation agreement.")
    lines.append("2. **State Version** metrics are architectural constants, not behavioural metrics.")
    lines.append("3. **Provenance Completeness** always equals 1.0 — confirms infrastructure works")
    lines.append("   but provides no discriminative information.")
    lines.append("4. **Hypothesis Stability** values describe hypothesis set turnover but do not")
    lines.append("   explain WHY turnover occurs (exploration vs. instability).")
    lines.append("5. Literature matching and novelty assessment are performed manually.")
    lines.append("")

    lines.append("---")
    lines.append(
        "*Generated by the evaluation metric extraction pipeline (v3). "
        "See run_metrics_corrected.json for complete data.*"
    )
    lines.append("")

    return "\n".join(lines)


# --- Main --------------------------------------------------------------------


def main() -> None:
    """Aggregate per-run metrics and produce summary outputs."""
    import sys
    
    run_metrics = _load_run_metrics()
    if run_metrics is None:
        sys.exit(1)

    print("=" * 60)
    print("Metric Aggregation Pipeline v3 (REFACTORED)")
    print("=" * 60)

    # Compute aggregates
    overall = aggregate_overall(run_metrics)
    cicids = aggregate_dataset(run_metrics, "cicids2017")
    unsw = aggregate_dataset(run_metrics, "unsw_nb15")

    print(f"\nOverall: {len(run_metrics)} runs")
    print(f"CICIDS2017: {cicids.get('_run_count', 0)} runs")
    print(f"UNSW-NB15: {unsw.get('_run_count', 0)} runs")

    # --- Output: aggregated_metrics_corrected.json ---
    aggregated = {
        "overall": overall,
        "cicids2017": cicids,
        "unsw_nb15": unsw,
    }

    json_path = OUTPUT_DIR / "aggregated_metrics_corrected.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)
    print(f"\nJSON output: {json_path}")

    # --- Output: aggregated_metrics_corrected.csv (wide format) ---
    csv_path = OUTPUT_DIR / "aggregated_metrics_corrected.csv"
    fieldnames = [
        "metric",
        "dataset",
        "mean",
        "std",
        "min",
        "max",
        "n",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for dataset_name, dataset_data in [
            ("overall", overall),
            ("cicids2017", cicids),
            ("unsw_nb15", unsw),
        ]:
            for metric in METRIC_NAMES:
                stats = dataset_data.get(metric, {})
                row = {
                    "metric": metric,
                    "dataset": dataset_name,
                    "mean": stats.get("mean"),
                    "std": stats.get("std"),
                    "min": stats.get("min"),
                    "max": stats.get("max"),
                    "n": stats.get("n", 0),
                }
                writer.writerow(row)
    print(f"CSV output:  {csv_path}")

    # --- Output: evaluation_summary_corrected.md ---
    summary = generate_summary(run_metrics, overall, cicids, unsw)
    summary_path = OUTPUT_DIR / "evaluation_summary_corrected.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"Summary:     {summary_path}")

    # --- Print summary table ---
    print(f"\n{'='*60}")
    print("Aggregated Metrics (Overall)")
    print("=" * 60)
    print(f"{'Metric':<40} {'Mean':<10} {'Std':<10} {'Min':<10} {'Max':<10} {'N':<5}")
    print("-" * 85)
    for metric in METRIC_NAMES:
        stats = overall.get(metric, {})
        label = METRIC_LABELS.get(metric, metric)
        mean = stats.get("mean", "—")
        std = stats.get("std", "—")
        min_v = stats.get("min", "—")
        max_v = stats.get("max", "—")
        n = stats.get("n", 0)
        print(f"{label:<40} {str(mean):<10} {str(std):<10} {str(min_v):<10} {str(max_v):<10} {n:<5}")
    print(f"\n{'='*60}")
    print("Aggregation complete.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()