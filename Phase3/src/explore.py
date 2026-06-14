"""Partition-level overview builder (batch-style).

This script generates a per-partition deterministic overview summary (`analysis_summary.json`)
using `src.feature_index` helpers. Treat it as the current Overview Builder precursor
that should be adapted and refactored into the Phase3a Overview Builder module.
"""

from __future__ import annotations

import json
import os

import pandas as pd
from scipy.spatial.distance import jensenshannon
from scipy.stats import entropy

from src.feature_index import (
    build_compact_feature_index,
    detect_feature_redundancy,
    feature_cardinality,
    get_candidate_features,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# Intra-class structural analysis
# ============================================================

def analyze_feature_by_class(df, feature, label_col="Label"):
    """
    Computes intra-class descriptive statistics for a given feature.
    """

    results = {}

    for label in df[label_col].unique():
        subset = df[df[label_col] == label][feature]

        results[label] = {
            "count": len(subset),
            "mean": float(subset.mean()),
            "std": float(subset.std()),
            "variance": float(subset.var()),
            "unique_values": int(subset.nunique()),
            "coef_variation": float(subset.std() / subset.mean()) if subset.mean() != 0 else None
        }

    variances = [v["variance"] for v in results.values() if v["variance"] > 0]

    if len(variances) >= 2:
        results["variance_ratio"] = float(max(variances) / min(variances))
    else:
        results["variance_ratio"] = None

    return results


# ============================================================
# Distribution-based analysis (discrete features)
# ============================================================

def distribution_metrics(df, feature, label_col="Label"):
    """
    Computes discrete distribution metrics per class.
    """

    results = {}
    distributions = {}

    for label in df[label_col].unique():
        subset = df[df[label_col] == label][feature]
        value_counts = subset.value_counts(normalize=True)

        distributions[label] = value_counts

        results[label] = {
            "dominant_ratio": float(value_counts.max()),
            "entropy": float(entropy(value_counts))
        }

    # Align distributions to same support
    all_values = set().union(*[dist.index for dist in distributions.values()])

    aligned = []
    for label in distributions:
        dist = distributions[label]
        aligned_dist = [dist.get(v, 0) for v in all_values]
        aligned.append(aligned_dist)

    if len(aligned) == 2:
        jsd = jensenshannon(aligned[0], aligned[1])
        results["js_divergence"] = float(jsd)
    else:
        results["js_divergence"] = None

    return results

# ============================================================
# Partition-level analysis
# ============================================================


def _resolve_label_column(df: pd.DataFrame) -> str:
    """Resolve the label column name, preferring common NIDS conventions."""
    candidates = ["Label", "label"]
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    # Fallback: any column whose name contains "label" (case-insensitive)
    for col in df.columns:
        if "label" in col.lower():
            return col
    raise KeyError(
        "No label column found in dataset. "
        "Expected one of: 'Label', 'label', or a column containing 'label' (case-insensitive). "
        f"Available columns: {sorted(df.columns)}"
    )


def analyze_partition(file_path):

    partition_name = os.path.basename(file_path)
    partition_results = {}

    df = pd.read_csv(file_path, nrows=100000)
    df.columns = df.columns.str.strip()

    # Resolve the label column (supports CIC_IDS_2017 'Label' and UNSW_NB15 'label')
    label_col = _resolve_label_column(df)

    # ---- Basic metadata ----
    partition_results["basic_info"] = {
        "shape": df.shape,
        "class_distribution": df[label_col].value_counts().to_dict(),
        "duplicates": int(df.duplicated().sum())
    }

    # ---- Class imbalance ----
    class_counts = df[label_col].value_counts()

    if len(class_counts) > 1:
        imbalance_ratio = float(class_counts.max() / class_counts.min())
    else:
        imbalance_ratio = None

    partition_results["class_imbalance_ratio"] = imbalance_ratio

    # ---- Correlation screening ----
    df["Label_bin"] = (df[label_col] != "BENIGN").astype(int)

    corr = (
        df.corr(numeric_only=True)["Label_bin"]
        .abs()
        .sort_values(ascending=False)
    )

    top_features = corr.drop("Label_bin").head(5).index.tolist()

    partition_results["top_features"] = top_features
    partition_results["feature_analysis"] = {}

    # ---- Intra-class structural metrics ----
    for feature in top_features:
        analysis = analyze_feature_by_class(df, feature, label_col=label_col)
        partition_results["feature_analysis"][feature] = analysis

    # ---- Feature redundancy detection ----

    partition_results["feature_redundancy"] = detect_feature_redundancy(df)

    # ---- Feature cardinality ----
    partition_results["feature_cardinality"] = feature_cardinality(df)

    # ---- Distribution metrics (example: Destination Port) ----
    if "Destination Port" in df.columns:
        dist_metrics = distribution_metrics(df, "Destination Port", label_col=label_col)
        partition_results["distribution_metrics"] = {
            "Destination Port": dist_metrics
        }

    return partition_name, partition_results


def update_cross_segment_stats(cross_stats, partition_results):

    # --- top features recurrence ---
    for feature in partition_results["top_features"]:
        cross_stats["top_feature_counts"][feature] = (
            cross_stats["top_feature_counts"].get(feature, 0) + 1
        )

    # --- redundant feature pairs recurrence ---
    for pair in partition_results["feature_redundancy"]:

        f1 = pair["feature_1"]
        f2 = pair["feature_2"]

        key = " | ".join(sorted([f1, f2]))

        cross_stats["redundant_feature_pairs"][key] = (
            cross_stats["redundant_feature_pairs"].get(key, 0) + 1
        )


def update_global_stats(global_stats, partition_results):

    n_samples = partition_results["basic_info"]["shape"][0]
    class_dist = partition_results["basic_info"]["class_distribution"]

    global_stats["total_samples"] += n_samples
    global_stats["segments_analyzed"] += 1

    for label, count in class_dist.items():
        global_stats["class_distribution"][label] = (
            global_stats["class_distribution"].get(label, 0) + count
        )


# ============================================================
# Main execution
# ============================================================

def main():

    DATA_DIR = os.path.join(BASE_DIR, "..", "data")

    segment_results = {}

    cross_segment_stats = {
        "top_feature_counts": {},
        "redundant_feature_pairs": {},
    }

    global_dataset_stats = {
        "total_samples": 0,
        "class_distribution": {},
        "segments_analyzed": 0
    }

    partitions = [
        f for f in os.listdir(DATA_DIR)
        if f.endswith(".csv")
    ]

    for file_name in partitions:

        file_path = os.path.join(DATA_DIR, file_name)

        partition_name, results = analyze_partition(file_path)

        segment_results[partition_name] = results

        update_cross_segment_stats(cross_segment_stats, results)

        update_global_stats(global_dataset_stats, results)

    # Save JSON summary
    with open("analysis_summary.json", "w") as f:
        final_results = {
            "segments": segment_results,
            "cross_segment_analysis": cross_segment_stats,
            "dataset_summary": global_dataset_stats
        }

        json.dump(final_results, f, indent=4)

    print("\nAnalysis saved to analysis_summary.json")
    print("\n=== PARTITION SUMMARY TABLE ===")

    # Clean and correct summary printing
    for partition, results in segment_results.items():

        print(f"\nPartition: {partition}")
        print("  Classes:", results["basic_info"]["class_distribution"])
        print("  Duplicates:", results["basic_info"]["duplicates"])
        print("  Top features:", results["top_features"])

        dist = results.get("distribution_metrics", {}).get("Destination Port")

        if dist:
            print("  Destination Port metrics:")
            for label, metrics in dist.items():
                if label == "js_divergence":
                    print("    JSD:", metrics)
                else:
                    print(f"    {label} dominant_ratio:",
                          metrics["dominant_ratio"])
                    print(f"    {label} entropy:", metrics["entropy"])

    print("\nSegments analyzed:", len(segment_results))
    print("Total samples:", global_dataset_stats["total_samples"])


if __name__ == "__main__":
    main()
