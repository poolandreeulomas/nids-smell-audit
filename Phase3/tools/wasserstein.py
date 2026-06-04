"""Wasserstein distance tool for MVP tools layer.

This module is fully decoupled from agent logic and relies on the
dataset abstraction layer for loading and validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import math
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
from scipy.stats import wasserstein_distance

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
from state.schema import EvidenceBlock


def _error_result(
    feature_name: str,
    error_code: str,
    error_message: str,
    meta: dict[str, Any] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    evidence = EvidenceBlock(
        feature=feature_name,
        signals=[],
        metrics={},
        support=meta or {},
        provenance={"source": "tool", "tool": "wasserstein", "step": step},
        status="active",
    ).to_dict()
    return {
        "ok": False,
        "tool": "wasserstein",
        "feature_name": feature_name,
        "value": None,
        "error_code": error_code,
        "error_message": error_message,
        "meta": meta or {},
        "evidence": evidence,
    }


def wasserstein(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
) -> dict[str, Any]:
    """Compute normalized Wasserstein distance for one feature.

    Normalization follows the professor baseline:
    normalized = raw_wasserstein / std(all_valid_feature_values)
    """
    cfg = config or get_default_dataset_config()

    try:
        if dataset_frame is None or valid_numeric_features is None:
            df, resolved_valid_numeric_features = load_dataset(
                dataset_path, cfg)
        else:
            df = dataset_frame
            resolved_valid_numeric_features = list(valid_numeric_features)

        feature_name = validate_feature_name(
            feature_name, resolved_valid_numeric_features)

        if not is_numeric_dtype(df[feature_name]):
            return _error_result(
                feature_name,
                "UNSUPPORTED_FEATURE_TYPE",
                f"Feature '{feature_name}' is not numeric.",
                meta={"dtype": str(df[feature_name].dtype)},
                step=step,
            )

        feature_values = df[feature_name].to_numpy(dtype=float)
        label_values = df[cfg.label_column]

        finite_mask = np.isfinite(feature_values)
        feature_values = feature_values[finite_mask]
        label_values = label_values.iloc[finite_mask]

        attack_mask = build_attack_mask(
            label_series=label_values,
            normal_labels=cfg.normal_labels,
            attack_labels=cfg.attack_labels,
            attack_label_mode=cfg.attack_label_mode,
        )
        normal_mask = ~attack_mask

        attack_values = feature_values[attack_mask]
        normal_values = feature_values[normal_mask]

        if attack_values.size == 0 or normal_values.size == 0:
            return _error_result(
                feature_name,
                "INSUFFICIENT_CLASS_DATA",
                "Feature has no valid values for one class after filtering.",
                meta={
                    "n_attack": int(attack_values.size),
                    "n_normal": int(normal_values.size),
                },
                step=step,
            )

        raw_distance = float(wasserstein_distance(
            normal_values, attack_values))
        combined_std = float(np.std(feature_values))

        if combined_std <= 0.0:
            normalized = 0.0
        else:
            normalized = float(raw_distance / combined_std)

        # Build EvidenceBlock
        n_rows_total = int(len(df))
        n_valid_rows = int(feature_values.size)
        n_attack = int(attack_values.size)
        n_normal = int(normal_values.size)

        metrics = {
            "raw_distance": raw_distance,
            "normalization_std": combined_std,
            "normalized": normalized,
        }

        # Sanitize NaN floats to None for JSON portability
        for k, v in list(metrics.items()):
            try:
                if isinstance(v, float) and math.isnan(v):
                    metrics[k] = None
            except Exception:
                continue

        support = {
            "total_samples": n_rows_total,
            "n_valid_rows": n_valid_rows,
            "per_class": {"normal": n_normal, "attack": n_attack},
        }

        provenance = {"source": "tool", "tool": "wasserstein", "step": step}

        evidence = EvidenceBlock(
            feature=feature_name,
            signals=["wasserstein_distance"],
            metrics=metrics,
            support=support,
            provenance=provenance,
            status="active",
        ).to_dict()

        return {
            "ok": True,
            "tool": "wasserstein",
            "feature_name": feature_name,
            "value": normalized,
            "error_code": None,
            "error_message": None,
            "meta": {
                "dataset_path": str(dataset_path),
                "label_column": cfg.label_column,
                "raw_distance": raw_distance,
                "normalization_std": combined_std,
                "n_rows": n_rows_total,
                "n_valid_rows": n_valid_rows,
                "n_normal": n_normal,
                "n_attack": n_attack,
                "normal_labels": list(cfg.normal_labels),
                "attack_labels": list(cfg.attack_labels),
                "attack_label_mode": cfg.attack_label_mode,
            },
            "evidence": evidence,
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
