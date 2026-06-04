"""Tool registry for MVP tools layer.

This registry is independent from agent logic and can be consumed by any caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from data.dataset_config import DatasetConfig
from tools.contracts import build_tool_capability_record
from tools.cardinality_analysis import cardinality_analysis
from tools.dependency_concentration_analysis import dependency_concentration_analysis
from tools.distribution_analysis import distribution_analysis
from tools.duplication_analysis import duplication_analysis
from tools.feature_relation import feature_relation
from tools.feature_summary import feature_summary
from tools.neighborhood_consistency_analysis import neighborhood_consistency_analysis
from tools.shortcut_analysis import shortcut_analysis

ToolFn = Callable[..., dict[str, Any]]


def get_tool_capability_records() -> dict[str, dict[str, Any]]:
    """Return Phase 3A capability metadata for the admitted tools."""
    return {
        "feature_summary": build_tool_capability_record(
            tool_name="feature_summary",
            epistemic_role="structural_summary",
            supported_scopes=["feature"],
            required_inputs=["feature_name"],
            result_shape="feature_observation",
            boundedness_notes="Summarizes one numeric feature under class-conditioned evidence.",
        ),
        "distribution_analysis": build_tool_capability_record(
            tool_name="distribution_analysis",
            epistemic_role="distribution_verification",
            supported_scopes=["feature"],
            required_inputs=["feature_name"],
            result_shape="feature_observation",
            boundedness_notes="Analyzes one numeric feature's class-conditioned distribution profile.",
        ),
        "cardinality_analysis": build_tool_capability_record(
            tool_name="cardinality_analysis",
            epistemic_role="cardinality_verification",
            supported_scopes=["feature"],
            required_inputs=["feature_name"],
            result_shape="feature_observation",
            boundedness_notes="Checks low-cardinality and near-constant behavior for one feature.",
        ),
        "feature_relation": build_tool_capability_record(
            tool_name="feature_relation",
            epistemic_role="relation_verification",
            supported_scopes=["feature", "feature_pair"],
            required_inputs=["feature_name"],
            result_shape="pair_observation",
            boundedness_notes="Measures one bounded pairwise relation and never expands beyond two features.",
        ),
        "shortcut_analysis": build_tool_capability_record(
            tool_name="shortcut_analysis",
            epistemic_role="shortcut_verification",
            supported_scopes=["feature"],
            required_inputs=["feature_name"],
            result_shape="feature_observation",
            boundedness_notes="Uses a deterministic one-feature decision stump to test shortcut-like predictive leverage.",
        ),
        "neighborhood_consistency_analysis": build_tool_capability_record(
            tool_name="neighborhood_consistency_analysis",
            epistemic_role="local_consistency_verification",
            supported_scopes=["feature"],
            required_inputs=["feature_name"],
            result_shape="feature_observation",
            boundedness_notes="Measures local label-topology consistency around one feature with bounded deterministic neighborhoods.",
        ),
        "dependency_concentration_analysis": build_tool_capability_record(
            tool_name="dependency_concentration_analysis",
            epistemic_role="dependency_contextualization",
            supported_scopes=["feature"],
            required_inputs=["feature_name"],
            result_shape="feature_observation",
            boundedness_notes="Measures whether one feature's dependency profile is concentrated into a narrow structural cluster.",
        ),
        "duplication_analysis": build_tool_capability_record(
            tool_name="duplication_analysis",
            epistemic_role="duplication_verification",
            supported_scopes=["dataset"],
            required_inputs=[],
            result_shape="dataset_observation",
            boundedness_notes="Checks exact duplication at dataset scope without semantic interpretation.",
        ),
    }


def get_tool_capability_record(tool_name: str) -> dict[str, Any] | None:
    """Return one capability record when admitted, else None."""
    return get_tool_capability_records().get(tool_name)


def get_tool_registry() -> dict[str, ToolFn]:
    """Return ACTION name -> tool callable mapping."""
    return {
        "feature_summary": feature_summary,
        "distribution_analysis": distribution_analysis,
        "cardinality_analysis": cardinality_analysis,
        "feature_relation": feature_relation,
        "shortcut_analysis": shortcut_analysis,
        "neighborhood_consistency_analysis": neighborhood_consistency_analysis,
        "dependency_concentration_analysis": dependency_concentration_analysis,
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
