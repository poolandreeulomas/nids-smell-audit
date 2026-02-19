from scipy.stats import entropy
from scipy.spatial.distance import jensenshannon
import os
import pandas as pd
import numpy as np


def analyze_feature_by_class(df, feature, label_col="Label"):
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

    # Variance ratio (largest / smallest)
    variances = [v["variance"] for v in results.values() if v["variance"] > 0]
    if len(variances) >= 2:
        results["variance_ratio"] = float(max(variances) / min(variances))
    else:
        results["variance_ratio"] = None

    return results


def distribution_metrics(df, feature, label_col="Label"):
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

    # Align distributions for JSD
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


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def analyze_partition(file_path):
    print(f"\n==============================")
    print(f"Analyzing partition: {os.path.basename(file_path)}")
    print(f"==============================")

    df = pd.read_csv(file_path, nrows=100000)
    df.columns = df.columns.str.strip()

    # -------------------------
    # PHASE 1 — Sanity check
    # -------------------------
    print("\n--- BASIC INFO ---")
    print("Shape:", df.shape)
    print("Class distribution:")
    print(df['Label'].value_counts())
    print("Duplicate rows:", df.duplicated().sum())

    # -------------------------
    # PHASE 2 — Correlation screening
    # -------------------------
    df["Label_bin"] = (df["Label"] != "BENIGN").astype(int)

    corr = (
        df.corr(numeric_only=True)["Label_bin"]
        .abs()
        .sort_values(ascending=False)
    )

    top_features = corr.drop("Label_bin").head(5).index.tolist()

    print("\nTop 5 features by correlation:", top_features)

    # -------------------------
    # PHASE 3 — Intra-class analysis
    # -------------------------
    for feature in top_features:
        print(f"\n--- Feature: {feature} ---")
        analysis = analyze_feature_by_class(df, feature)
        for key, value in analysis.items():
            print(key, ":", value)

    # -------------------------
    # PHASE 4 — Distribution analysis (example)
    # -------------------------
    if "Destination Port" in df.columns:
        print("\n--- Distribution metrics: Destination Port ---")
        dist_metrics = distribution_metrics(df, "Destination Port")
        for key, value in dist_metrics.items():
            print(key, ":", value)

def main():

    DATA_DIR = os.path.join(BASE_DIR, "..", "data")

    partitions = [
        "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
        "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv",
        "Friday-WorkingHours-Morning.pcap_ISCX.csv",
    ]

    for file_name in partitions:
        file_path = os.path.join(DATA_DIR, file_name)
        analyze_partition(file_path)


if __name__ == "__main__":
    main()
