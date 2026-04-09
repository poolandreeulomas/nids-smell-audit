"""Correlation tool for MVP tools layer.

This module is fully decoupled from agent logic and relies on the
dataset abstraction layer for loading and validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pandas.api.types import is_numeric_dtype

from data.dataset_config import DatasetConfig, get_default_dataset_config
from data.loader import load_dataset
from data.validation import (
    build_attack_mask,
    DatasetValidationError,
    InvalidFeatureNameError,
    InvalidDatasetConfigError,
    MissingLabelColumnError,
    validate_feature_name,
)


def _error_result(
    feature_name: str,
    error_code: str,
    error_message: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": "correlation",
        "feature_name": feature_name,
        "value": None,
        "error_code": error_code,
        "error_message": error_message,
        "meta": meta or {},
    }


def correlation(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
) -> dict[str, Any]:
    """Compute correlation(feature, binary_label).

    Returns a machine-readable dict with a stable schema.
    """
    cfg = config or get_default_dataset_config()

    try:
        if dataset_frame is None or valid_numeric_features is None:
            df, resolved_valid_numeric_features = load_dataset(
                dataset_path, cfg)
        else:
            df = dataset_frame
            resolved_valid_numeric_features = list(valid_numeric_features)

        validate_feature_name(feature_name, resolved_valid_numeric_features)

        if not is_numeric_dtype(df[feature_name]):
            return _error_result(
                feature_name,
                "UNSUPPORTED_FEATURE_TYPE",
                f"Feature '{feature_name}' is not numeric.",
                meta={"dtype": str(df[feature_name].dtype)},
            )

        attack_mask = build_attack_mask(
            label_series=df[cfg.label_column],
            normal_labels=cfg.normal_labels,
            attack_labels=cfg.attack_labels,
            attack_label_mode=cfg.attack_label_mode,
        )
        binary_label = pd.Series(attack_mask.astype(int), index=df.index)
        pair = pd.concat([df[feature_name], binary_label], axis=1).dropna()
        pair.columns = [feature_name, "_binary_label"]

        if pair.empty:
            return _error_result(
                feature_name,
                "INSUFFICIENT_DATA",
                "No valid rows remain after dropping missing values.",
            )

        value = pair[feature_name].corr(pair["_binary_label"])
        if pd.isna(value):
            return _error_result(
                feature_name,
                "INSUFFICIENT_VARIANCE",
                "Correlation is undefined due to zero variance in feature or label.",
            )

        return {
            "ok": True,
            "tool": "correlation",
            "feature_name": feature_name,
            "value": float(value),
            "error_code": None,
            "error_message": None,
            "meta": {
                "dataset_path": str(dataset_path),
                "label_column": cfg.label_column,
                "n_rows": int(len(df)),
                "n_valid_rows": int(len(pair)),
                "normal_labels": list(cfg.normal_labels),
                "attack_labels": list(cfg.attack_labels),
                "attack_label_mode": cfg.attack_label_mode,
            },
        }
    except InvalidFeatureNameError as exc:
        return _error_result(feature_name, "INVALID_FEATURE", str(exc))
    except InvalidDatasetConfigError as exc:
        return _error_result(feature_name, "INVALID_CONFIG", str(exc))
    except MissingLabelColumnError as exc:
        return _error_result(feature_name, "MISSING_LABEL_COLUMN", str(exc))
    except DatasetValidationError as exc:
        return _error_result(feature_name, "DATASET_VALIDATION_ERROR", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _error_result(feature_name, "RUNTIME_ERROR", str(exc))
