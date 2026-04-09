"""Tool registry for MVP tools layer.

This registry is independent from agent logic and can be consumed by any caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from data.dataset_config import DatasetConfig
from tools.correlation import correlation
from tools.wasserstein import wasserstein

ToolFn = Callable[..., dict[str, Any]]


def get_tool_registry() -> dict[str, ToolFn]:
    """Return ACTION name -> tool callable mapping."""
    return {
        "correlation": correlation,
        "wasserstein": wasserstein,
    }


def run_tool(
    tool_name: str,
    feature_name: str,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
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

    return tool(
        feature_name=feature_name,
        dataset_path=dataset_path,
        config=config,
        dataset_frame=dataset_frame,
        valid_numeric_features=valid_numeric_features,
    )
