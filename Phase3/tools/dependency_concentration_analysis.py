"""Phase 3A tool: concentration of one feature's dependency profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
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


def _compute_dependency_metrics(
    df: pd.DataFrame,
    *,
    feature_name: str,
    valid_features: list[str],
) -> dict[str, Any]:
    corr_matrix = get_or_cache(
        df,
        "dependency_concentration_analysis::corr_matrix",
        lambda: df[valid_features].corr(numeric_only=True),
    )

    partner_records: list[tuple[str, float]] = []
    for other_feature in valid_features:
        if other_feature == feature_name:
            continue
        corr_value = corr_matrix.loc[feature_name, other_feature]
        if pd.isna(corr_value):
            continue
        partner_records.append((other_feature, abs(float(corr_value))))

    if not partner_records:
        raise DatasetValidationError(
            "Dependency concentration analysis requires at least one finite pairwise dependency."
        )

    partner_records.sort(key=lambda item: (-item[1], item[0]))
    correlations = np.asarray(
        [value for _, value in partner_records], dtype=float)
    dependency_mass = np.square(correlations)
    dependency_mass_sum = float(dependency_mass.sum())
    if dependency_mass_sum <= 0.0:
        raise DatasetValidationError(
            "Dependency concentration analysis requires non-zero pairwise dependency mass."
        )

    weights = dependency_mass / dependency_mass_sum
    concentration_index = float(np.square(weights).sum())
    effective_partner_count = float(
        1.0 / concentration_index) if concentration_index > 0 else None
    top_partner_name, top_partner_correlation = partner_records[0]
    top_partner_share = float(weights[0])
    top3_share = float(weights[:3].sum())
    strong_partner_count = int(np.sum(correlations >= 0.7))

    return {
        "partner_count": len(partner_records),
        "strong_partner_count": strong_partner_count,
        "top_partner": top_partner_name,
        "top_partner_correlation": top_partner_correlation,
        "top_partner_share": top_partner_share,
        "top3_share": top3_share,
        "concentration_index": concentration_index,
        "effective_partner_count": effective_partner_count,
        "mean_abs_correlation": float(np.mean(correlations)),
        "median_abs_correlation": float(np.median(correlations)),
    }


def dependency_concentration_analysis(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Measure whether one feature's dependency evidence is narrow or diffuse."""
    try:
        cfg, df, resolved_valid_features = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features
        )
        feature_name = validate_feature_name(
            feature_name, resolved_valid_features)

        metrics = _compute_dependency_metrics(
            df,
            feature_name=feature_name,
            valid_features=resolved_valid_features,
        )

        top_partner_share = float(metrics.get("top_partner_share", 0.0))
        top_partner_correlation = float(
            metrics.get("top_partner_correlation", 0.0))
        top3_share = float(metrics.get("top3_share", 0.0))
        mean_abs_correlation = float(metrics.get("mean_abs_correlation", 0.0))

        signals: list[str] = []
        if top_partner_share >= 0.6 and top_partner_correlation >= 0.8:
            signals.append("high_dependency_concentration")
        if top3_share >= 0.8 and top_partner_correlation >= 0.6:
            signals.append("localized_dependency_cluster")
        if mean_abs_correlation >= 0.3 and top_partner_share < 0.45:
            signals.append("diffuse_dependency_background")

        return build_success_result(
            tool_name="dependency_concentration_analysis",
            feature_name=feature_name,
            value=float(metrics.get("concentration_index", 0.0)),
            signals=signals,
            metrics=metrics,
            support=build_support(df, cfg.label_column),
            step=step,
            meta={"dataset_path": str(dataset_path),
                  "label_column": cfg.label_column},
        )
    except InvalidFeatureNameError as exc:
        return build_error_result(
            tool_name="dependency_concentration_analysis",
            feature_name=feature_name,
            error_code="INVALID_FEATURE",
            error_message=str(exc),
            step=step,
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="dependency_concentration_analysis",
            feature_name=feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="dependency_concentration_analysis",
            feature_name=feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="dependency_concentration_analysis",
            feature_name=feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="dependency_concentration_analysis",
            feature_name=feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
