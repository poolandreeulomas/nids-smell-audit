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
# Feature redundancy detection
# ============================================================


def detect_feature_redundancy(df, threshold=0.95):
    """
    Detect highly correlated feature pairs.

    High correlation between features may indicate redundancy or derived variables in the dataset, which can lead to shortcut learning.
    """
    corr_matrix = df.corr(numeric_only=True)

    redundant_pairs = []

    for i, col1 in enumerate(corr_matrix.columns):
        for col2 in corr_matrix.columns[i+1:]:

            corr_value = corr_matrix.loc[col1, col2]
            if abs(corr_value) >= threshold:
                redundant_pairs.append({
                    "feature_1": col1,
                    "feature_2": col2,
                    "correlation": float(corr_value)
                })
    return redundant_pairs

# ============================================================
# Feature cardinality statistics
# ============================================================


def feature_cardinality(df):
    """
    Computes cardinality statistics for numeric features.

    Cardinality ratio = unique_values / number_of_samples

    Useful for detecting deterministic or low - diversity features.
    """

    results = {}

    n_samples = len(df)

    for col in df.select_dtypes(include=[np.number]).columns:
        unique_values = df[col].nunique()
        results[col] = {
            "unique_values": int(unique_values),
            "cardinality_ratio": float(unique_values / n_samples) if n_samples > 0 else None
        }
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

    # ---- Class imbalance ----
    class_counts = df["Label"].value_counts()

    if len(class_counts) > 1:
        imbalance_ratio = float(class_counts.max() / class_counts.min())
    else:
        imbalance_ratio = None

    partition_results["class_imbalance_ratio"] = imbalance_ratio

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

    # ---- Feature redundancy detection ----

    partition_results["feature_redundancy"] = detect_feature_redundancy(df)

    # ---- Feature cardinality ----
    partition_results["feature_cardinality"] = feature_cardinality(df)

    # ---- Distribution metrics (example: Destination Port) ----
    if "Destination Port" in df.columns:
        dist_metrics = distribution_metrics(df, "Destination Port")
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
