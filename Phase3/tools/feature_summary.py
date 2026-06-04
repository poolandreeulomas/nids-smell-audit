"""Phase 2 tool: compact intra-class feature summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from data.dataset_config import DatasetConfig
from data.validation import (
    DatasetValidationError,
    InvalidDatasetConfigError,
    InvalidFeatureNameError,
    MissingLabelColumnError,
    validate_feature_name,
)
from src.explore import analyze_feature_by_class
from tools.common import (
    build_error_result,
    build_success_result,
    build_support,
    get_or_cache,
    resolve_tool_inputs,
)


def feature_summary(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Summarize per-class structural statistics for one numeric feature."""
    try:
        cfg, df, resolved_valid_features = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features
        )
        feature_name = validate_feature_name(
            feature_name, resolved_valid_features)

        summary = get_or_cache(
            df,
            f"feature_summary::{feature_name}",
            lambda: analyze_feature_by_class(
                df, feature_name, label_col=cfg.label_column),
        )

        labels = [label for label in summary.keys() if label !=
                  "variance_ratio"]
        metrics = {
            "mean": {str(label): summary[label].get("mean") for label in labels},
            "std": {str(label): summary[label].get("std") for label in labels},
            "variance": {str(label): summary[label].get("variance") for label in labels},
            "coef_variation": {
                str(label): summary[label].get("coef_variation") for label in labels
            },
            "unique_values": {
                str(label): summary[label].get("unique_values") for label in labels
            },
            "variance_ratio": summary.get("variance_ratio"),
        }

        signals: list[str] = []
        variances = [summary[label].get("variance") for label in labels]
        finite_variances = [
            float(value) for value in variances if isinstance(value, (int, float))]
        if finite_variances and max(abs(value) for value in finite_variances) <= 1e-8:
            signals.append("low_variance")

        variance_ratio = summary.get("variance_ratio")
        if isinstance(variance_ratio, (int, float)) and float(variance_ratio) >= 10.0:
            signals.append("high_variance_imbalance")

        unique_values = [summary[label].get(
            "unique_values") for label in labels]
        finite_unique_values = [
            int(value) for value in unique_values if isinstance(value, (int, float))]
        if finite_unique_values and min(finite_unique_values) <= 3:
            signals.append("low_diversity")

        support = build_support(df, cfg.label_column)
        support["n_per_class"] = {
            str(label): int(summary[label].get("count", 0)) for label in labels
        }
        support["per_class"] = dict(support["n_per_class"])

        representative_value: float | None
        if isinstance(variance_ratio, (int, float)):
            representative_value = float(variance_ratio)
        elif finite_variances:
            representative_value = float(max(finite_variances))
        else:
            representative_value = None

        return build_success_result(
            tool_name="feature_summary",
            feature_name=feature_name,
            value=representative_value,
            signals=signals,
            metrics=metrics,
            support=support,
            step=step,
            meta={"dataset_path": str(dataset_path),
                  "label_column": cfg.label_column},
        )
    except InvalidFeatureNameError as exc:
        return build_error_result(
            tool_name="feature_summary",
            feature_name=feature_name,
            error_code="INVALID_FEATURE",
            error_message=str(exc),
            step=step,
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="feature_summary",
            feature_name=feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="feature_summary",
            feature_name=feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="feature_summary",
            feature_name=feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="feature_summary",
            feature_name=feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
