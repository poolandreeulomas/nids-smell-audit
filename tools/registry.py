"""Tool registry for MVP tools layer.

This registry is independent from agent logic and can be consumed by any caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from data.dataset_config import DatasetConfig
from tools.cardinality_analysis import cardinality_analysis
from tools.distribution_analysis import distribution_analysis
from tools.duplication_analysis import duplication_analysis
from tools.feature_relation import feature_relation
from tools.feature_summary import feature_summary

ToolFn = Callable[..., dict[str, Any]]


def get_tool_registry() -> dict[str, ToolFn]:
    """Return ACTION name -> tool callable mapping."""
    return {
        "feature_summary": feature_summary,
        "distribution_analysis": distribution_analysis,
        "cardinality_analysis": cardinality_analysis,
        "feature_relation": feature_relation,
        "duplication_analysis": duplication_analysis,
    }


def run_tool(
    tool_name: str,
    feature_name: str | None,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    related_feature_name: str | None = None,
) -> dict[str, Any]:
    """Dispatch one tool call with a uniform machine-readable output."""
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if tool is None:
        return {
            "ok": False,
            "tool": tool_name,
            "feature_name": feature_name,
            "value": None,
            "error_code": "INVALID_ACTION",
            "error_message": f"Unknown tool '{tool_name}'.",
            "meta": {"available_tools": sorted(registry.keys())},
        }

    tool_kwargs = {
        "feature_name": feature_name,
        "dataset_path": dataset_path,
        "config": config,
        "dataset_frame": dataset_frame,
        "valid_numeric_features": valid_numeric_features,
    }
    if tool_name == "feature_relation" and related_feature_name is not None:
        tool_kwargs["related_feature_name"] = related_feature_name

    return tool(**tool_kwargs)
