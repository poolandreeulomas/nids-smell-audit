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


def build_compact_feature_index(df, label_col="Label", redundancy_threshold: float = 0.95):
    """Produce a compact, deterministic per-feature summary suitable for candidate selection.

    Returned map (dict) keys are feature names and values are small dicts with:
      - unique_values: int
      - cardinality_ratio: float
      - skewness: float (pandas skew)
      - redundancy: list of partner dicts {feature: str, correlation: float} (may be empty)

    This function intentionally keeps outputs small and avoids per-class raw dumps.
    """
    import numpy as _np

    summaries = {}

    # Numeric columns only
    numeric_cols = list(df.select_dtypes(include=[_np.number]).columns)
    n_samples = len(df)

    # Precompute cardinality and skew
    for col in numeric_cols:
        unique_vals = int(df[col].nunique())
        cardinality_ratio = float(
            unique_vals / n_samples) if n_samples > 0 else None
        try:
            skewness = float(df[col].skew())
        except Exception:
            skewness = None

        summaries[col] = {
            "unique_values": unique_vals,
            "cardinality_ratio": cardinality_ratio,
            "skewness": skewness,
            "redundancy": [],
        }

    # Redundancy: detect highly correlated pairs and attach partners
    try:
        corr_matrix = df.corr(numeric_only=True)
        for i, col1 in enumerate(corr_matrix.columns):
            for col2 in corr_matrix.columns[i+1:]:
                corr_value = corr_matrix.loc[col1, col2]
                if abs(corr_value) >= redundancy_threshold:
                    # attach to both features
                    if col1 in summaries:
                        summaries[col1]["redundancy"].append(
                            {"feature": col2, "correlation": float(corr_value)})
                    if col2 in summaries:
                        summaries[col2]["redundancy"].append(
                            {"feature": col1, "correlation": float(corr_value)})
    except Exception:
        # Be forgiving: if correlation computation fails, leave redundancy empty
        pass

    return summaries


def get_candidate_features(criteria: str, df=None, summaries: dict | None = None, top_k: int = 10):
    """Deterministically return compact candidate features for a given criteria.

    - `criteria`: one of 'low cardinality', 'high skew', or 'redundancy' (case-insensitive).
    - `df`: optional DataFrame; required if `summaries` not provided.
    - `summaries`: optional precomputed output of `build_compact_feature_index`.

    Returns a list of compact records: {"feature_name": str, "signals": [...], "score": float}
    Signals are short tokens describing why the candidate was selected.
    """
    if summaries is None:
        if df is None:
            raise ValueError("df or summaries must be provided")
        summaries = build_compact_feature_index(df)

    key = (criteria or "").strip().lower()
    # normalize synonyms
    if key in ("low cardinality", "low_cardinality", "low_card"):
        mode = "low_cardinality"
    elif key in ("high skew", "skew", "high_skew"):
        mode = "high_skew"
    elif key in ("redundancy", "redundant", "high redundancy", "redundant_pairs"):
        mode = "redundancy"
    else:
        raise ValueError(f"unsupported criteria: {criteria}")

    records = []
    if mode == "low_cardinality":
        for feat, v in summaries.items():
            cr = v.get("cardinality_ratio")
            score = float(cr) if cr is not None else float("inf")
            signals = [f"unique_values={v.get('unique_values')}",
                       f"cardinality_ratio={round(cr, 3) if cr is not None else None}"]
            records.append(
                {"feature_name": feat, "signals": signals, "score": score})
        # lower cardinality_ratio is more interesting
        records.sort(key=lambda r: (
            r["score"] if r["score"] is not None else float("inf"), r["feature_name"]))

    elif mode == "high_skew":
        for feat, v in summaries.items():
            sk = v.get("skewness")
            score = -abs(float(sk)) if sk is not None else float("inf")
            signals = [f"skewness={round(sk, 3) if sk is not None else None}"]
            records.append(
                {"feature_name": feat, "signals": signals, "score": score})
        # more extreme skew (abs) first
        records.sort(key=lambda r: (r["score"], r["feature_name"]))

    elif mode == "redundancy":
        for feat, v in summaries.items():
            partners = v.get("redundancy") or []
            # score by number of partners then max correlation
            n_partners = len(partners)
            max_corr = max([abs(p.get("correlation", 0.0))
                           for p in partners]) if partners else 0.0
            score = (-n_partners, -max_corr)
            signals = [
                f"redundant_with={p['feature']}@{round(p['correlation'], 3)}" for p in partners[:3]]
            records.append(
                {"feature_name": feat, "signals": signals, "score": score})
        # sort by number of partners desc, then by max_corr desc, then name
        records.sort(key=lambda r: (r["score"], r["feature_name"]))

    # return top_k compact records, omit heavy fields
    compact = []
    for rec in records[:top_k]:
        compact.append(
            {"feature_name": rec["feature_name"], "signals": rec["signals"]})

    return compact


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
