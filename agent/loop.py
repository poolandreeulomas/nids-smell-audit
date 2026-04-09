"""Bounded ReAct loop controller for MVP agent."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from agent.executor import execute_action
from agent.parser import parse_react_output
from data.dataset_config import DatasetConfig
from prompts.builder import build_prompt
from state.schema import AgentState
from state.store import (
    advance_step,
    append_error,
    append_history,
    merge_metadata,
    set_promising_features,
    update_analyzed_feature,
)
from utils.reproducibility import build_reproducibility_metadata, hash_text_sha256

LlmCallable = Callable[[str], str]


def _format_trace_payload(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    if value is None:
        return "None"
    return str(value)


def _print_trace_block(step_id: int, title: str, payload: dict[str, Any]) -> None:
    print(f"\n=== ReAct Step {step_id} | {title} ===")
    for key, value in payload.items():
        print(f"{key}: {_format_trace_payload(value)}")


def _record_step(
    *,
    state: AgentState,
    step_id: int,
    thought: str | None,
    action: str | None,
    action_input: dict[str, Any] | None,
    observation: dict[str, Any],
    raw_model_output: str,
    prompt_text: str,
    status: str,
) -> None:
    append_history(
        state,
        {
            "step_id": step_id,
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "observation": observation,
            "raw_model_output": raw_model_output,
            "prompt_snapshot": prompt_text,
            "prompt_snapshot_hash": hash_text_sha256(prompt_text),
            "execution_status": status,
        },
    )


def _update_state_after_tool(
    state: AgentState,
    action: str,
    feature_name: str,
    tool_result: dict[str, Any],
) -> None:
    feature_state = state.analyzed_features.get(feature_name, {})
    tools_used = list(feature_state.get("tools_used", []))
    tool_results = dict(feature_state.get("tool_results", {}))
    if action not in tools_used:
        tools_used.append(action)
    tool_results[action] = tool_result

    evidence = {
        "tools_used": tools_used,
        action: tool_result.get("value"),
        "tool_results": tool_results,
        "last_result": tool_result,
    }
    update_analyzed_feature(state, feature_name, evidence)

    ranked_features = sorted(
        state.analyzed_features.items(),
        key=lambda item: (
            len(item[1].get("tools_used", [])),
            abs(float(item[1].get("correlation", 0.0) or 0.0)),
            float(item[1].get("wasserstein", 0.0) or 0.0),
        ),
        reverse=True,
    )
    set_promising_features(state, [name for name, _ in ranked_features])


def run_agent(
    *,
    state: AgentState,
    llm_callable: LlmCallable,
    dataset_path: str | Path,
    dataset_config: DatasetConfig,
    tool_names: list[str],
    model_name: str,
    model_version: str | None = None,
    temperature: float = 0.0,
    seed: int | None = None,
    top_p: float | None = None,
    repo_path: str | Path | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    trace: bool = False,
) -> AgentState:
    """Execute a single bounded ReAct run and return updated state."""
    prompt_preview = build_prompt(state, tool_names)
    reproducibility = build_reproducibility_metadata(
        model_name=model_name,
        model_version=model_version,
        prompt_text=prompt_preview,
        temperature=temperature,
        seed=seed,
        dataset_path=dataset_path,
        dataset_config=asdict(dataset_config),
        available_features=state.available_features,
        max_steps=state.max_steps,
        top_p=top_p,
        repo_path=repo_path,
        include_dataset_hash=True,
    )
    merge_metadata(state, {"reproducibility": reproducibility})

    while state.current_step < state.max_steps:
        step_id = state.current_step + 1
        prompt_text = build_prompt(state, tool_names)

        try:
            raw_model_output = llm_callable(prompt_text)
        except Exception as exc:  # noqa: BLE001
            observation = {
                "ok": False,
                "error_code": "LLM_ERROR",
                "error_message": str(exc),
            }
            if trace:
                _print_trace_block(
                    step_id,
                    "LLM_ERROR",
                    {
                        "OBSERVATION": observation,
                    },
                )
            append_error(state, {"step_id": step_id, **observation})
            _record_step(
                state=state,
                step_id=step_id,
                thought=None,
                action=None,
                action_input=None,
                observation=observation,
                raw_model_output="",
                prompt_text=prompt_text,
                status="LLM_ERROR",
            )
            advance_step(state)
            continue

        parsed = parse_react_output(raw_model_output)
        if not parsed.get("ok", False):
            observation = {
                "ok": False,
                "error_code": parsed.get("error_code", "PARSE_ERROR"),
                "error_message": parsed.get("error_message", "Parser failure."),
            }
            if trace:
                _print_trace_block(
                    step_id,
                    "PARSE_ERROR",
                    {
                        "RAW_MODEL_OUTPUT": raw_model_output,
                        "OBSERVATION": observation,
                    },
                )
            append_error(state, {"step_id": step_id, **observation})
            _record_step(
                state=state,
                step_id=step_id,
                thought=None,
                action=None,
                action_input=None,
                observation=observation,
                raw_model_output=raw_model_output,
                prompt_text=prompt_text,
                status="PARSE_ERROR",
            )
            advance_step(state)
            continue

        action = parsed["action"]
        action_input = parsed["action_input"]
        thought = parsed["thought"]
        if trace:
            _print_trace_block(
                step_id,
                "MODEL_DECISION",
                {
                    "THOUGHT": thought,
                    "ACTION": action,
                    "ACTION_INPUT": action_input,
                },
            )
        result = execute_action(
            action=action,
            action_input=action_input,
            dataset_path=dataset_path,
            dataset_config=dataset_config,
            state=state,
            dataset_frame=dataset_frame,
            valid_numeric_features=valid_numeric_features,
        )

        status = "OK"
        error_code = result.get("error_code")
        if error_code == "INVALID_ACTION":
            status = "INVALID_ACTION"
            append_error(state, {"step_id": step_id, **result})
        elif error_code == "REPEATED_FEATURE_BLOCKED":
            status = "REPEATED_FEATURE_BLOCKED"
            append_error(state, {"step_id": step_id, **result})
        elif not result.get("ok", False):
            status = "TOOL_ERROR"
            append_error(state, {"step_id": step_id, **result})
        else:
            _update_state_after_tool(
                state, action, action_input["feature_name"], result)

        if trace:
            _print_trace_block(
                step_id,
                "TOOL_RESULT",
                {
                    "STATUS": status,
                    "OBSERVATION": result,
                },
            )

        _record_step(
            state=state,
            step_id=step_id,
            thought=thought,
            action=action,
            action_input=action_input,
            observation=result,
            raw_model_output=raw_model_output,
            prompt_text=prompt_text,
            status=status,
        )
        advance_step(state)

    return state
