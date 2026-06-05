"""Phase 3A tool: local neighborhood consistency over one numeric feature."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

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


_ENABLE_ENV_VAR = "PHASE3A_ENABLE_NEIGHBORHOOD_CONSISTENCY_ANALYSIS"


def _neighborhood_analysis_enabled() -> bool:
    raw_value = os.environ.get(_ENABLE_ENV_VAR)
    if raw_value is None:
        return True
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def _compute_neighborhood_metrics(
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

    retained_rows = int(valid_mask.sum())
    if retained_rows < 6:
        raise DatasetValidationError(
            "Neighborhood consistency analysis requires at least 6 finite labeled rows."
        )

    x = feature_values[valid_mask].reshape(-1, 1)
    y = build_attack_mask(
        label_series[valid_mask],
        normal_labels,
        attack_labels,
        attack_label_mode,
    ).astype(int)

    neighbor_count = min(5, retained_rows - 1)
    if neighbor_count < 1:
        raise DatasetValidationError(
            "Neighborhood consistency analysis requires at least one neighbor per row."
        )

    model = NearestNeighbors(n_neighbors=neighbor_count + 1)
    model.fit(x)
    _, indices = model.kneighbors(x)
    neighbor_indices = indices[:, 1:]

    agreement = (y[neighbor_indices] == y[:, None]).mean(axis=1)
    local_consistency_rate = float(np.mean(agreement))
    inconsistency_rate = float(1.0 - local_consistency_rate)

    attack_mask = y == 1
    benign_mask = y == 0
    attack_consistency_rate = float(
        np.mean(agreement[attack_mask])) if attack_mask.any() else None
    benign_consistency_rate = float(
        np.mean(agreement[benign_mask])) if benign_mask.any() else None

    boundary_instability_rate = float(
        np.mean((agreement > 0.2) & (agreement < 0.8)))

    duplicate_conflict_rows = 0
    duplicate_rows = 0
    for _, group in pd.DataFrame({"value": x[:, 0], "label": y}).groupby("value"):
        if len(group) < 2:
            continue
        duplicate_rows += int(len(group))
        if group["label"].nunique() > 1:
            duplicate_conflict_rows += int(len(group))
    duplicate_conflict_rate = float(
        duplicate_conflict_rows / retained_rows) if retained_rows else 0.0
    duplicate_cluster_rate = float(
        duplicate_rows / retained_rows) if retained_rows else 0.0

    return {
        "neighbor_count": neighbor_count,
        "retained_rows": retained_rows,
        "coverage_ratio": float(retained_rows / len(df)) if len(df) else 0.0,
        "local_consistency_rate": local_consistency_rate,
        "inconsistency_rate": inconsistency_rate,
        "attack_consistency_rate": attack_consistency_rate,
        "benign_consistency_rate": benign_consistency_rate,
        "boundary_instability_rate": boundary_instability_rate,
        "duplicate_conflict_rate": duplicate_conflict_rate,
        "duplicate_cluster_rate": duplicate_cluster_rate,
    }


def neighborhood_consistency_analysis(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Measure local label-topology consistency along one numeric feature."""
    if not _neighborhood_analysis_enabled():
        return {
            "ok": True,
            "tool": "neighborhood_consistency_analysis",
            "feature_name": feature_name,
            "value": None,
            "skipped": True,
            "reason": "disabled_by_runtime_config",
            "meta": {
                "runtime_config_env_var": _ENABLE_ENV_VAR,
                "runtime_config_value": os.environ.get(_ENABLE_ENV_VAR),
            },
        }

    try:
        cfg, df, resolved_valid_features = resolve_tool_inputs(
            dataset_path, config, dataset_frame, valid_numeric_features
        )
        feature_name = validate_feature_name(
            feature_name, resolved_valid_features)

        metrics = get_or_cache(
            df,
            f"neighborhood_consistency_analysis::{feature_name}",
            lambda: _compute_neighborhood_metrics(
                df,
                feature_name=feature_name,
                label_column=cfg.label_column,
                normal_labels=cfg.normal_labels,
                attack_labels=cfg.attack_labels,
                attack_label_mode=cfg.attack_label_mode,
            ),
        )

        inconsistency_rate = float(metrics.get("inconsistency_rate", 0.0))
        local_consistency_rate = float(
            metrics.get("local_consistency_rate", 0.0))
        duplicate_conflict_rate = float(
            metrics.get("duplicate_conflict_rate", 0.0))
        boundary_instability_rate = float(
            metrics.get("boundary_instability_rate", 0.0))

        signals: list[str] = []
        if inconsistency_rate >= 0.35:
            signals.append("high_label_neighborhood_conflict")
        elif inconsistency_rate >= 0.2:
            signals.append("moderate_label_neighborhood_conflict")
        if duplicate_conflict_rate >= 0.05:
            signals.append("duplicate_label_conflict")
        if boundary_instability_rate >= 0.25:
            signals.append("unstable_local_topology")
        if local_consistency_rate >= 0.9:
            signals.append("stable_local_topology")

        return build_success_result(
            tool_name="neighborhood_consistency_analysis",
            feature_name=feature_name,
            value=inconsistency_rate,
            signals=signals,
            metrics=metrics,
            support=build_support(df, cfg.label_column),
            step=step,
            meta={"dataset_path": str(dataset_path),
                  "label_column": cfg.label_column},
        )
    except InvalidFeatureNameError as exc:
        return build_error_result(
            tool_name="neighborhood_consistency_analysis",
            feature_name=feature_name,
            error_code="INVALID_FEATURE",
            error_message=str(exc),
            step=step,
        )
    except InvalidDatasetConfigError as exc:
        return build_error_result(
            tool_name="neighborhood_consistency_analysis",
            feature_name=feature_name,
            error_code="INVALID_CONFIG",
            error_message=str(exc),
            step=step,
        )
    except MissingLabelColumnError as exc:
        return build_error_result(
            tool_name="neighborhood_consistency_analysis",
            feature_name=feature_name,
            error_code="MISSING_LABEL_COLUMN",
            error_message=str(exc),
            step=step,
        )
    except DatasetValidationError as exc:
        return build_error_result(
            tool_name="neighborhood_consistency_analysis",
            feature_name=feature_name,
            error_code="DATASET_VALIDATION_ERROR",
            error_message=str(exc),
            step=step,
        )
    except Exception as exc:  # noqa: BLE001
        return build_error_result(
            tool_name="neighborhood_consistency_analysis",
            feature_name=feature_name,
            error_code="RUNTIME_ERROR",
            error_message=str(exc),
            step=step,
        )
