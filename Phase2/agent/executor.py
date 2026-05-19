"""Action validation and tool dispatch for MVP agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from data.dataset_config import DatasetConfig
from state.schema import AgentState
from tools.registry import get_tool_registry, run_tool


def _execution_error(
    action: str | None,
    feature_name: str | None,
    error_code: str,
    error_message: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "tool": action,
        "feature_name": feature_name,
        "value": None,
        "error_code": error_code,
        "error_message": error_message,
        "meta": meta or {},
    }


def _is_repeated_feature_blocked(
    state: AgentState,
    action: str,
    feature_name: str,
    available_tools: set[str],
) -> tuple[bool, str | None]:
    feature_state = state.analyzed_features.get(feature_name, {})
    tools_used = set(feature_state.get("tools_used", []))

    if action in tools_used:
        return True, f"Tool '{action}' already used for feature '{feature_name}'."

    if available_tools.issubset(tools_used):
        return True, f"Feature '{feature_name}' is already fully analyzed."

    return False, None


def _parse_feature_relation_input(feature_name: str) -> tuple[str, str | None, str]:
    parts = [part.strip() for part in feature_name.split("|")]
    if len(parts) != 2 or any(not part for part in parts):
        return feature_name, None, feature_name

    primary_feature, related_feature = parts
    feature_key = "|".join(sorted(parts))
    return primary_feature, related_feature, feature_key


def execute_action(
    *,
    action: str,
    action_input: dict[str, Any],
    dataset_path: str | Path,
    dataset_config: DatasetConfig,
    state: AgentState,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    step: int | None = None,
) -> dict[str, Any]:
    """Validate action request and dispatch to tools layer."""
    registry = get_tool_registry()
    available_tools = set(registry.keys())

    feature_name = action_input.get("feature_name")
    related_feature_name: str | None = None

    if action == "duplication_analysis":
        if not isinstance(feature_name, str) or not feature_name.strip():
            feature_name = "__dataset__"
        feature_key = "__dataset__"
    else:
        if not isinstance(feature_name, str) or not feature_name.strip():
            return _execution_error(
                action,
                None,
                "INVALID_ACTION_INPUT",
                "ACTION_INPUT.feature_name must be a non-empty string.",
            )
        feature_name = feature_name.strip()
        feature_key = feature_name
        if action == "feature_relation" and "|" in feature_name:
            feature_name, related_feature_name, feature_key = _parse_feature_relation_input(
                feature_name
            )

    if action not in registry:
        return _execution_error(
            action,
            feature_name,
            "INVALID_ACTION",
            f"Unknown tool '{action}'.",
            meta={"available_tools": sorted(available_tools)},
        )

    blocked, reason = _is_repeated_feature_blocked(
        state=state,
        action=action,
        feature_name=feature_key,
        available_tools=available_tools,
    )
    if blocked:
        return _execution_error(
            action,
            feature_name,
            "REPEATED_FEATURE_BLOCKED",
            reason or "Repeated feature blocked.",
        )

    # Dispatch to tool callable directly so we can forward `step` provenance.
    tool = registry.get(action)
    if tool is None:
        return _execution_error(
            action,
            feature_name,
            "INVALID_ACTION",
            f"Unknown tool '{action}'.",
            meta={"available_tools": sorted(available_tools)},
        )

    try:
        tool_kwargs = {
            "feature_name": feature_name,
            "dataset_path": dataset_path,
            "config": dataset_config,
            "dataset_frame": dataset_frame,
            "valid_numeric_features": valid_numeric_features,
            "step": step,
        }
        if action == "feature_relation" and related_feature_name is not None:
            tool_kwargs["related_feature_name"] = related_feature_name
        # Prefer calling with `step` argument; fallback for tools without it.
        try:
            result = tool(**tool_kwargs)
        except TypeError:
            tool_kwargs.pop("step", None)
            result = tool(**tool_kwargs)
    except Exception as exc:  # noqa: BLE001
        return _execution_error(
            action,
            feature_name,
            "RUNTIME_ERROR",
            str(exc),
        )

    if not result.get("ok", False) and result.get("error_code") == "INVALID_ACTION":
        return _execution_error(
            action,
            feature_name,
            "INVALID_ACTION",
            result.get("error_message", "Unknown tool."),
            meta=result.get("meta", {}),
        )

    return result
