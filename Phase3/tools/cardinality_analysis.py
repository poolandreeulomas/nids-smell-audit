"""Phase 2 tool: compact feature cardinality analysis."""

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
from src.feature_index import feature_cardinality
from tools.common import (
    build_error_result,
    build_success_result,
    build_support,
    get_or_cache,
    resolve_tool_inputs,
)


def cardinality_analysis(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Return low-cardinality evidence for one numeric feature."""
    try:
        cfg, df, resolved_valid_features = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features
        )
        feature_name = validate_feature_name(
            feature_name, resolved_valid_features)

        summaries = get_or_cache(
            df, "feature_cardinality", lambda: feature_cardinality(df))
        summary = summaries.get(feature_name, {})
        unique_values = summary.get("unique_values")
        cardinality_ratio = summary.get("cardinality_ratio")

        signals: list[str] = []
        if isinstance(cardinality_ratio, (int, float)) and float(cardinality_ratio) <= 0.05:
            signals.append("low_cardinality")
        if (
            isinstance(cardinality_ratio, (int, float)) and float(
                cardinality_ratio) <= 0.01
        ) or (isinstance(unique_values, (int, float)) and int(unique_values) <= 2):
            signals.append("near_constant")

        return build_success_result(
            tool_name="cardinality_analysis",
            feature_name=feature_name,
            value=float(cardinality_ratio) if isinstance(
                cardinality_ratio, (int, float)) else None,
            signals=signals,
            metrics={
                "unique_values": unique_values,
                "cardinality_ratio": cardinality_ratio,
            },
            support=build_support(df, cfg.label_column),
            step=step,
            meta={"dataset_path": str(dataset_path),
                  "label_column": cfg.label_column},
        )
    except InvalidFeatureNameError as exc:
        return build_error_result(
            tool_name="cardinality_analysis",
            feature_name=feature_name,
            error_code="INVALID_FEATURE",
            error_message=str(exc),
            step=step,
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="cardinality_analysis",
            feature_name=feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="cardinality_analysis",
            feature_name=feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="cardinality_analysis",
            feature_name=feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="cardinality_analysis",
            feature_name=feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
