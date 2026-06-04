"""Phase 3A tool: bounded shortcut verification for one numeric feature."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import StratifiedKFold
from sklearn.tree import DecisionTreeClassifier

from data.dataset_config import DatasetConfig
from data.validation import (
    DatasetValidationError,
    InvalidDatasetConfigError,
    InvalidFeatureNameError,
    MissingLabelColumnError,
    validate_feature_name,
)
from data.validation import build_attack_mask
from tools.common import (
    build_error_result,
    build_success_result,
    build_support,
    get_or_cache,
    resolve_tool_inputs,
)


def _compute_shortcut_metrics(
    df: pd.DataFrame,
    *,
    feature_name: str,
    label_column: str,
    normal_labels: list[str],
    attack_labels: list[str],
    attack_label_mode: str,
) -> dict[str, Any]:
    feature_values = pd.to_numeric(
        df[feature_name], errors="coerce").to_numpy(dtype=float)
    label_series = df[label_column]
    valid_mask = np.isfinite(
        feature_values) & label_series.notna().to_numpy(dtype=bool)

    if int(valid_mask.sum()) < 4:
        raise DatasetValidationError(
            "Shortcut analysis requires at least 4 finite labeled rows for the selected feature."
        )

    targets = build_attack_mask(
        label_series[valid_mask],
        normal_labels,
        attack_labels,
        attack_label_mode,
    ).astype(int)
    class_counts = np.bincount(targets, minlength=2)
    min_class_count = int(class_counts.min())
    if min_class_count < 2:
        raise DatasetValidationError(
            "Shortcut analysis requires at least 2 rows per class after filtering finite values."
        )

    x = feature_values[valid_mask].reshape(-1, 1)
    y = targets
    n_splits = min(5, min_class_count)

    cv_scores: list[float] = []
    cv_thresholds: list[float] = []
    splitter = StratifiedKFold(n_splits=n_splits, shuffle=False)
    for train_idx, test_idx in splitter.split(x, y):
        classifier = DecisionTreeClassifier(max_depth=1, random_state=0)
        classifier.fit(x[train_idx], y[train_idx])
        predictions = classifier.predict(x[test_idx])
        cv_scores.append(
            float(balanced_accuracy_score(y[test_idx], predictions)))
        if classifier.tree_.node_count > 1:
            cv_thresholds.append(float(classifier.tree_.threshold[0]))

    final_classifier = DecisionTreeClassifier(max_depth=1, random_state=0)
    final_classifier.fit(x, y)
    final_predictions = final_classifier.predict(x)
    train_balanced_accuracy = float(
        balanced_accuracy_score(y, final_predictions))

    threshold: float | None = None
    if final_classifier.tree_.node_count > 1:
        threshold = float(final_classifier.tree_.threshold[0])

    return {
        "cv_balanced_accuracy": float(np.mean(cv_scores)),
        "cv_balanced_accuracy_std": float(np.std(cv_scores)),
        "train_balanced_accuracy": train_balanced_accuracy,
        "threshold": threshold,
        "fold_count": n_splits,
        "attack_rate": float(y.mean()),
        "retained_rows": int(len(y)),
        "coverage_ratio": float(len(y) / len(df)) if len(df) else 0.0,
        "thresholds": cv_thresholds,
    }


def shortcut_analysis(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Measure whether one feature behaves like a strong one-split shortcut."""
    try:
        cfg, df, resolved_valid_features = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features
        )
        feature_name = validate_feature_name(
            feature_name, resolved_valid_features)

        metrics = get_or_cache(
            df,
            f"shortcut_analysis::{feature_name}",
            lambda: _compute_shortcut_metrics(
                df,
                feature_name=feature_name,
                label_column=cfg.label_column,
                normal_labels=cfg.normal_labels,
                attack_labels=cfg.attack_labels,
                attack_label_mode=cfg.attack_label_mode,
            ),
        )

        cv_balanced_accuracy = float(metrics.get("cv_balanced_accuracy", 0.0))
        train_balanced_accuracy = float(
            metrics.get("train_balanced_accuracy", 0.0))
        gap = train_balanced_accuracy - cv_balanced_accuracy

        signals: list[str] = []
        if cv_balanced_accuracy >= 0.9:
            signals.append("strong_shortcut_signal")
        elif cv_balanced_accuracy >= 0.75:
            signals.append("moderate_shortcut_signal")
        else:
            signals.append("weak_shortcut_evidence")
        if gap >= 0.1:
            signals.append("shortcut_instability")

        return build_success_result(
            tool_name="shortcut_analysis",
            feature_name=feature_name,
            value=cv_balanced_accuracy,
            signals=signals,
            metrics={
                "cv_balanced_accuracy": cv_balanced_accuracy,
                "cv_balanced_accuracy_std": metrics.get("cv_balanced_accuracy_std"),
                "train_balanced_accuracy": train_balanced_accuracy,
                "generalization_gap": gap,
                "threshold": metrics.get("threshold"),
                "fold_count": metrics.get("fold_count"),
                "attack_rate": metrics.get("attack_rate"),
                "retained_rows": metrics.get("retained_rows"),
                "coverage_ratio": metrics.get("coverage_ratio"),
            },
            support=build_support(df, cfg.label_column),
            step=step,
            meta={"dataset_path": str(dataset_path),
                  "label_column": cfg.label_column},
        )
    except InvalidFeatureNameError as exc:
        return build_error_result(
            tool_name="shortcut_analysis",
            feature_name=feature_name,
            error_code="INVALID_FEATURE",
            error_message=str(exc),
            step=step,
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="shortcut_analysis",
            feature_name=feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="shortcut_analysis",
            feature_name=feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="shortcut_analysis",
            feature_name=feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="shortcut_analysis",
            feature_name=feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
