"""Prompt builder for rigid MVP ReAct prompts."""

from __future__ import annotations

import json
from pathlib import Path

from state.schema import AgentState

PROMPT_TEMPLATE_PATH = Path(__file__).with_name("react_prompt.txt")


def _format_available_tools(tool_names: list[str]) -> str:
    if not tool_names:
        return "NONE"
    return "\n".join(f"- {tool_name}" for tool_name in tool_names)


def _format_analyzed_features(analyzed_features: dict) -> str:
    if not analyzed_features:
        return "NONE"
    return ", ".join(sorted(analyzed_features.keys()))


def _format_available_features(available_features: list[str]) -> str:
    if not available_features:
        return "NONE"
    return ", ".join(available_features)


def _format_observation(observation: object) -> str:
    if not isinstance(observation, dict):
        return str(observation)

    compact = {
        "ok": observation.get("ok"),
        "tool": observation.get("tool"),
        "feature_name": observation.get("feature_name"),
        "value": observation.get("value"),
        "error_code": observation.get("error_code"),
    }
    return json.dumps(compact, ensure_ascii=True, sort_keys=True)


def _format_recent_history(history: list[dict], history_window: int) -> str:
    if not history:
        return "NONE"

    recent_steps = history[-history_window:]
    lines = []
    for step in recent_steps:
        step_id = step.get("step_id", "NA")
        thought = step.get("thought", "")
        action = step.get("action", "")
        action_input = step.get("action_input", {})
        observation = _format_observation(step.get("observation", ""))
        lines.append(
            "Step {step_id} | THOUGHT: {thought} | ACTION: {action} | "
            "ACTION_INPUT: {action_input} | OBSERVATION: {observation}".format(
                step_id=step_id,
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
            )
        )
    return "\n".join(lines)


def build_prompt(
    state: AgentState,
    tool_names: list[str],
    history_window: int = 5,
) -> str:
    """Build prompt from state, tools, and recent history."""
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.format(
        objective=state.objective,
        available_tools=_format_available_tools(tool_names),
        available_features=_format_available_features(
            state.available_features),
        analyzed_features=_format_analyzed_features(state.analyzed_features),
        recent_history=_format_recent_history(state.history, history_window),
    )
