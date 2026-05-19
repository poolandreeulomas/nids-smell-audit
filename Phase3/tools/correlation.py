"""Correlation tool for MVP tools layer.

This module is fully decoupled from agent logic and relies on the
dataset abstraction layer for loading and validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import math
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
        provenance={"source": "tool", "tool": "correlation", "step": step},
        status="active",
    ).to_dict()
    return {
        "ok": False,
        "tool": "correlation",
        "feature_name": feature_name,
        "value": None,
        "error_code": error_code,
        "error_message": error_message,
        "meta": meta or {},
        "evidence": evidence,
    }


def correlation(
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: Any | None = None,
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
                step=step,
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
                meta={
                    "n_rows": int(len(df)),
                    "n_valid_rows": 0,
                },
                step=step,
            )

        feature_series = pair[feature_name]
        label_series = pair["_binary_label"]
        value = pair[feature_name].corr(pair["_binary_label"])
        if pd.isna(value):
            return _error_result(
                feature_name,
                "INSUFFICIENT_VARIANCE",
                "Correlation is undefined due to zero variance in feature or label.",
                meta={
                    "n_rows": int(len(df)),
                    "n_valid_rows": int(len(pair)),
                    "feature_variance": float(feature_series.var()),
                    "label_variance": float(label_series.var()),
                    "n_unique_feature_values": int(feature_series.nunique(dropna=True)),
                    "feature_nunique": int(feature_series.nunique(dropna=True)),
                    "label_nunique": int(label_series.nunique(dropna=True)),
                    "feature_std": float(feature_series.std(ddof=0)),
                    "label_std": float(label_series.std(ddof=0)),
                    "attack_rate": float(label_series.mean()),
                },
                step=step,
            )

        # Build EvidenceBlock
        n_rows_total = int(len(df))
        n_valid_rows = int(len(pair))
        n_attack = int(label_series.sum())
        n_normal = int(n_valid_rows - n_attack)

        metrics = {
            "correlation": float(value),
            "feature_variance": float(feature_series.var()),
            "label_variance": float(label_series.var()),
            "n_unique_feature_values": int(feature_series.nunique(dropna=True)),
            "feature_std": float(feature_series.std(ddof=0)),
            "label_std": float(label_series.std(ddof=0)),
            "attack_rate": float(label_series.mean()),
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

        provenance = {"source": "tool", "tool": "correlation", "step": step}

        evidence = EvidenceBlock(
            feature=feature_name,
            signals=["pearson_correlation"],
            metrics=metrics,
            support=support,
            provenance=provenance,
            status="active",
        ).to_dict()

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
                "n_rows": n_rows_total,
                "n_valid_rows": n_valid_rows,
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
