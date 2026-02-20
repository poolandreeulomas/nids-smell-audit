"""
Exploratory structural audit of NIDS benchmark partitions.

Purpose:
--------
This script collects structural statistics per dataset partition
to identify potential risks such as:

- Deterministic feature-label dependencies
- Low intra-class diversity
- Extreme variance imbalance
- Shortcut learning risks

Important:
----------
This is NOT a smell detection module yet.
It only gathers quantitative signals.

Results are stored in analysis_summary.json
for later cross-partition comparison.
"""

from scipy.stats import entropy
from scipy.spatial.distance import jensenshannon
import os
import pandas as pd
import numpy as np
import json

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

def analyze_partition(file_path):

    partition_name = os.path.basename(file_path)
    partition_results = {}

    df = pd.read_csv(file_path, nrows=100000)
    df.columns = df.columns.str.strip()

    # ---- Basic metadata ----
    partition_results["basic_info"] = {
        "shape": df.shape,
        "class_distribution": df["Label"].value_counts().to_dict(),
        "duplicates": int(df.duplicated().sum())
    }

    # ---- Correlation screening ----
    df["Label_bin"] = (df["Label"] != "BENIGN").astype(int)

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
        analysis = analyze_feature_by_class(df, feature)
        partition_results["feature_analysis"][feature] = analysis

    # ---- Distribution metrics (example: Destination Port) ----
    if "Destination Port" in df.columns:
        dist_metrics = distribution_metrics(df, "Destination Port")
        partition_results["distribution_metrics"] = {
            "Destination Port": dist_metrics
        }

    return partition_name, partition_results


# ============================================================
# Main execution
# ============================================================

def main():

    DATA_DIR = os.path.join(BASE_DIR, "..", "data")

    partitions = [
        f for f in os.listdir(DATA_DIR)
        if f.endswith(".csv")
    ]

    all_results = {}

    for file_name in partitions:
        file_path = os.path.join(DATA_DIR, file_name)
        partition_name, results = analyze_partition(file_path)
        all_results[partition_name] = results

    # Save JSON summary
    with open("analysis_summary.json", "w") as f:
        json.dump(all_results, f, indent=4)

    print("\nAnalysis saved to analysis_summary.json")
    print("\n=== PARTITION SUMMARY TABLE ===")

    # Clean and correct summary printing
    for partition, results in all_results.items():

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
                    print(f"    {label} dominant_ratio:", metrics["dominant_ratio"])
                    print(f"    {label} entropy:", metrics["entropy"])


if __name__ == "__main__":
    main()