"""Phase 2 tool: relation between two numeric features."""

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
from tools.common import (
    build_error_result,
    build_success_result,
    build_support,
    get_or_cache,
    resolve_tool_inputs,
)


def feature_relation(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
    related_feature_name: str | None = None,
) -> dict[str, Any]:
    """Return pairwise correlation evidence for two numeric features.

    If `related_feature_name` is omitted, the strongest correlated partner for
    `feature_name` is selected deterministically from the correlation matrix.
    """
    try:
        cfg, df, resolved_valid_features = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features
        )
        validate_feature_name(feature_name, resolved_valid_features)

        corr_matrix = get_or_cache(
            df,
            "feature_relation::corr_matrix",
            lambda: df[resolved_valid_features].corr(numeric_only=True),
        )

        partner = related_feature_name
        if partner is not None:
            validate_feature_name(partner, resolved_valid_features)
        else:
            candidates = []
            for other_feature in resolved_valid_features:
                if other_feature == feature_name:
                    continue
                value = corr_matrix.loc[feature_name, other_feature]
                if pd.isna(value):
                    continue
                candidates.append(
                    (abs(float(value)), other_feature, float(value)))
            if not candidates:
                return build_error_result(
                    tool_name="feature_relation",
                    feature_name=feature_name,
                    error_code="INSUFFICIENT_RELATION_DATA",
                    error_message="No valid partner feature found for relation analysis.",
                    step=step,
                )
            candidates.sort(key=lambda item: (-item[0], item[1]))
            partner = candidates[0][1]

        corr_value = corr_matrix.loc[feature_name, partner]
        if pd.isna(corr_value):
            return build_error_result(
                tool_name="feature_relation",
                feature_name=f"{feature_name}|{partner}",
                error_code="INSUFFICIENT_VARIANCE",
                error_message="Correlation between selected features is undefined.",
                step=step,
            )

        corr_value = float(corr_value)
        signals: list[str] = []
        if abs(corr_value) >= 0.95:
            signals.append("high_redundancy")

        pair_name = "|".join(sorted([feature_name, partner]))
        return build_success_result(
            tool_name="feature_relation",
            feature_name=pair_name,
            value=corr_value,
            signals=signals,
            metrics={"correlation": corr_value},
            support=build_support(df, cfg.label_column),
            step=step,
            meta={
                "dataset_path": str(dataset_path),
                "label_column": cfg.label_column,
                "feature_1": feature_name,
                "feature_2": partner,
            },
        )
    except InvalidFeatureNameError as exc:
        return build_error_result(
            tool_name="feature_relation",
            feature_name=feature_name,
            error_code="INVALID_FEATURE",
            error_message=str(exc),
            step=step,
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="feature_relation",
            feature_name=feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="feature_relation",
            feature_name=feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="feature_relation",
            feature_name=feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="feature_relation",
            feature_name=feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
