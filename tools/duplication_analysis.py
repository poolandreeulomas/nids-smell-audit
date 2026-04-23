"""Phase 2 tool: dataset-level duplication analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from data.dataset_config import DatasetConfig
from data.validation import DatasetValidationError, InvalidDatasetConfigError, MissingLabelColumnError
from tools.common import (
    build_error_result,
    build_success_result,
    build_support,
    get_or_cache,
    resolve_tool_inputs,
)


def duplication_analysis(
    feature_name: str | None,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Return exact-duplicate evidence for the whole dataset partition."""
    dataset_feature_name = "__dataset__"
    try:
        cfg, df, _ = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features)

        duplicate_mask = get_or_cache(
            df, "duplication_analysis::mask", lambda: df.duplicated())
        duplicate_count = int(duplicate_mask.sum())
        n_total = int(len(df))
        duplicate_ratio = float(
            duplicate_count / n_total) if n_total > 0 else 0.0

        signals: list[str] = []
        if duplicate_ratio >= 0.2:
            signals.append("high_duplication")
        elif duplicate_ratio >= 0.05:
            signals.append("moderate_duplication")

        metrics = {
            "duplicate_count": duplicate_count,
            "duplicate_ratio": duplicate_ratio,
        }

        if cfg.label_column in df.columns:
            duplicate_class_counts = (
                df.loc[duplicate_mask, cfg.label_column].value_counts(
                    dropna=False).to_dict()
            )
            metrics["duplicate_count_per_class"] = {
                str(label): int(count) for label, count in duplicate_class_counts.items()
            }

        return build_success_result(
            tool_name="duplication_analysis",
            feature_name=dataset_feature_name,
            value=duplicate_ratio,
            signals=signals,
            metrics=metrics,
            support=build_support(df, cfg.label_column),
            step=step,
            meta={"dataset_path": str(dataset_path),
                  "label_column": cfg.label_column},
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="duplication_analysis",
            feature_name=dataset_feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="duplication_analysis",
            feature_name=dataset_feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="duplication_analysis",
            feature_name=dataset_feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="duplication_analysis",
            feature_name=dataset_feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
