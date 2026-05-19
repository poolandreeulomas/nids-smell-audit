"""Compact per-feature indexing helpers used by the live Phase 2 runtime."""

from __future__ import annotations

from typing import Any

import numpy as np


def detect_feature_redundancy(df, threshold: float = 0.95) -> list[dict[str, Any]]:
    """Detect highly correlated numeric feature pairs."""
    corr_matrix = df.corr(numeric_only=True)
    redundant_pairs: list[dict[str, Any]] = []

    for index, feature_a in enumerate(corr_matrix.columns):
        for feature_b in corr_matrix.columns[index + 1:]:
            corr_value = corr_matrix.loc[feature_a, feature_b]
            if abs(corr_value) >= threshold:
                redundant_pairs.append(
                    {
                        "feature_1": feature_a,
                        "feature_2": feature_b,
                        "correlation": float(corr_value),
                    }
                )
    return redundant_pairs


def feature_cardinality(df) -> dict[str, dict[str, float | int | None]]:
    """Compute cardinality statistics for numeric features."""
    results: dict[str, dict[str, float | int | None]] = {}
    n_samples = len(df)

    for column in df.select_dtypes(include=[np.number]).columns:
        unique_values = df[column].nunique()
        results[column] = {
            "unique_values": int(unique_values),
            "cardinality_ratio": float(unique_values / n_samples) if n_samples > 0 else None,
        }
    return results


def build_compact_feature_index(df, label_col: str = "Label", redundancy_threshold: float = 0.95):
    """Build a compact, deterministic summary for candidate selection and prompting."""
    del label_col

    summaries: dict[str, dict[str, Any]] = {}
    numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
    n_samples = len(df)

    for column in numeric_cols:
        unique_values = int(df[column].nunique())
        cardinality_ratio = float(
            unique_values / n_samples) if n_samples > 0 else None
        try:
            skewness = float(df[column].skew())
        except Exception:
            skewness = None

        summaries[column] = {
            "unique_values": unique_values,
            "cardinality_ratio": cardinality_ratio,
            "skewness": skewness,
            "redundancy": [],
        }

    try:
        corr_matrix = df.corr(numeric_only=True)
        for index, feature_a in enumerate(corr_matrix.columns):
            for feature_b in corr_matrix.columns[index + 1:]:
                corr_value = corr_matrix.loc[feature_a, feature_b]
                if abs(corr_value) >= redundancy_threshold:
                    if feature_a in summaries:
                        summaries[feature_a]["redundancy"].append(
                            {"feature": feature_b,
                                "correlation": float(corr_value)}
                        )
                    if feature_b in summaries:
                        summaries[feature_b]["redundancy"].append(
                            {"feature": feature_a,
                                "correlation": float(corr_value)}
                        )
    except Exception:
        pass

    return summaries


def get_candidate_features(criteria: str, df=None, summaries: dict | None = None, top_k: int = 10):
    """Return compact candidate features for one structural criterion."""
    if summaries is None:
        if df is None:
            raise ValueError("df or summaries must be provided")
        summaries = build_compact_feature_index(df)

    key = (criteria or "").strip().lower()
    if key in ("low cardinality", "low_cardinality", "low_card"):
        mode = "low_cardinality"
    elif key in ("high skew", "skew", "high_skew"):
        mode = "high_skew"
    elif key in ("redundancy", "redundant", "high redundancy", "redundant_pairs"):
        mode = "redundancy"
    else:
        raise ValueError(f"unsupported criteria: {criteria}")

    records: list[dict[str, Any]] = []
    if mode == "low_cardinality":
        for feature_name, summary in summaries.items():
            cardinality_ratio = summary.get("cardinality_ratio")
            score = float(
                cardinality_ratio) if cardinality_ratio is not None else float("inf")
            signals = [
                f"unique_values={summary.get('unique_values')}",
                f"cardinality_ratio={round(cardinality_ratio, 3) if cardinality_ratio is not None else None}",
            ]
            records.append(
                {"feature_name": feature_name, "signals": signals, "score": score}
            )
        records.sort(key=lambda item: (item["score"], item["feature_name"]))

    elif mode == "high_skew":
        for feature_name, summary in summaries.items():
            skewness = summary.get("skewness")
            score = -abs(float(skewness)
                         ) if skewness is not None else float("inf")
            signals = [
                f"skewness={round(skewness, 3) if skewness is not None else None}"]
            records.append(
                {"feature_name": feature_name, "signals": signals, "score": score}
            )
        records.sort(key=lambda item: (item["score"], item["feature_name"]))

    else:
        for feature_name, summary in summaries.items():
            partners = summary.get("redundancy") or []
            n_partners = len(partners)
            max_corr = max([abs(partner.get("correlation", 0.0))
                           for partner in partners]) if partners else 0.0
            signals = [
                f"redundant_with={partner['feature']}@{round(partner['correlation'], 3)}"
                for partner in partners[:3]
            ]
            records.append(
                {
                    "feature_name": feature_name,
                    "signals": signals,
                    "score": (-n_partners, -max_corr),
                }
            )
        records.sort(key=lambda item: (item["score"], item["feature_name"]))

    return [
        {"feature_name": record["feature_name"], "signals": record["signals"]}
        for record in records[:top_k]
    ]
