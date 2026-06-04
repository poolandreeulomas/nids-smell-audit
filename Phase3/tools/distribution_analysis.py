"""Phase 2 tool: compact distribution analysis."""

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
from src.explore import distribution_metrics
from tools.common import (
    build_error_result,
    build_success_result,
    build_support,
    get_or_cache,
    resolve_tool_inputs,
)


def distribution_analysis(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Analyze class-conditioned value distributions for one feature."""
    try:
        cfg, df, resolved_valid_features = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features
        )
        feature_name = validate_feature_name(
            feature_name, resolved_valid_features)

        summary = get_or_cache(
            df,
            f"distribution_analysis::{feature_name}",
            lambda: distribution_metrics(
                df, feature_name, label_col=cfg.label_column),
        )

        labels = [label for label in summary.keys() if label !=
                  "js_divergence"]
        metrics = {
            "entropy": {str(label): summary[label].get("entropy") for label in labels},
            "dominant_ratio": {
                str(label): summary[label].get("dominant_ratio") for label in labels
            },
            "js_divergence": summary.get("js_divergence"),
        }

        signals: list[str] = []
        entropies = [summary[label].get("entropy") for label in labels]
        finite_entropies = [
            float(value) for value in entropies if isinstance(value, (int, float))]
        if finite_entropies and min(finite_entropies) <= 1.0:
            signals.append("low_entropy")

        dominant_ratios = [summary[label].get(
            "dominant_ratio") for label in labels]
        finite_dominant = [
            float(value) for value in dominant_ratios if isinstance(value, (int, float))]
        if finite_dominant and max(finite_dominant) >= 0.8:
            signals.append("dominant_value")

        js_divergence = summary.get("js_divergence")
        if isinstance(js_divergence, (int, float)) and float(js_divergence) >= 0.5:
            signals.append("high_class_separation")

        representative_value: float | None
        if isinstance(js_divergence, (int, float)):
            representative_value = float(js_divergence)
        elif finite_dominant:
            representative_value = float(max(finite_dominant))
        else:
            representative_value = None

        return build_success_result(
            tool_name="distribution_analysis",
            feature_name=feature_name,
            value=representative_value,
            signals=signals,
            metrics=metrics,
            support=build_support(df, cfg.label_column),
            step=step,
            meta={"dataset_path": str(dataset_path),
                  "label_column": cfg.label_column},
        )
    except InvalidFeatureNameError as exc:
        return build_error_result(
            tool_name="distribution_analysis",
            feature_name=feature_name,
            error_code="INVALID_FEATURE",
            error_message=str(exc),
            step=step,
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="distribution_analysis",
            feature_name=feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="distribution_analysis",
            feature_name=feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="distribution_analysis",
            feature_name=feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="distribution_analysis",
            feature_name=feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
