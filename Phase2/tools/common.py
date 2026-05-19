"""Shared helpers for Phase 2 tool implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import math
import pandas as pd

from data.dataset_config import DatasetConfig, get_default_dataset_config
from data.loader import load_dataset


def resolve_tool_inputs(
    dataset_path: str | Path,
    config: DatasetConfig | None,
    dataset_frame: pd.DataFrame | None,
    valid_numeric_features: list[str] | None,
) -> tuple[DatasetConfig, pd.DataFrame, list[str]]:
    """Return normalized config, dataframe, and valid numeric features."""
    cfg = config or get_default_dataset_config()
    if dataset_frame is None or valid_numeric_features is None:
        df, resolved_valid_numeric_features = load_dataset(dataset_path, cfg)
    else:
        df = dataset_frame
        resolved_valid_numeric_features = list(valid_numeric_features)
    return cfg, df, resolved_valid_numeric_features


def get_df_cache(df: pd.DataFrame) -> dict[str, Any]:
    """Return a mutable per-dataframe cache for deterministic tool reuse."""
    cache = df.attrs.get("_phase2_tool_cache")
    if not isinstance(cache, dict):
        cache = {}
        df.attrs["_phase2_tool_cache"] = cache
    return cache


def get_or_cache(df: pd.DataFrame, cache_key: str, factory: Callable[[], Any]) -> Any:
    """Get cached value from dataframe attrs or compute and store it."""
    cache = get_df_cache(df)
    if cache_key not in cache:
        cache[cache_key] = factory()
    return cache[cache_key]


def sanitize_json_like(value: Any) -> Any:
    """Recursively convert NaN/inf values into JSON-safe primitives."""
    if isinstance(value, dict):
        return {str(key): sanitize_json_like(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json_like(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


def build_support(df: pd.DataFrame, label_column: str | None = None) -> dict[str, Any]:
    """Build compact support metadata with backward-compatible keys."""
    n_total = int(len(df))
    n_per_class: dict[str, int] = {}
    if label_column and label_column in df.columns:
        counts = df[label_column].value_counts(dropna=False)
        n_per_class = {str(label): int(count)
                       for label, count in counts.items()}
    return {
        "n_total": n_total,
        "n_per_class": n_per_class,
        "total_samples": n_total,
        "per_class": n_per_class,
    }


def build_success_result(
    *,
    tool_name: str,
    feature_name: str,
    value: float | int | None,
    signals: list[str],
    metrics: dict[str, Any],
    support: dict[str, Any],
    step: Any | None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the common successful tool payload."""
    from state.schema import EvidenceBlock

    clean_metrics = sanitize_json_like(metrics)
    clean_support = sanitize_json_like(support)
    evidence = EvidenceBlock(
        feature=feature_name,
        signals=list(signals),
        metrics=clean_metrics,
        support=clean_support,
        provenance={"source": "tool", "tool": tool_name, "step": step},
        status="active",
    ).to_dict()
    return {
        "ok": True,
        "tool": tool_name,
        "feature_name": feature_name,
        "value": value,
        "error_code": None,
        "error_message": None,
        "meta": sanitize_json_like(meta or {}),
        "evidence": evidence,
    }


def build_error_result(
    *,
    tool_name: str,
    feature_name: str,
    error_code: str,
    error_message: str,
    step: Any | None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the common error payload with an empty EvidenceBlock."""
    return build_success_result(
        tool_name=tool_name,
        feature_name=feature_name,
        value=None,
        signals=[],
        metrics={},
        support=meta or {},
        step=step,
        meta={"error": error_code, **(meta or {})},
    ) | {
        "ok": False,
        "error_code": error_code,
        "error_message": error_message,
    }
