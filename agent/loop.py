"""Bounded ReAct loop controller for MVP agent."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from agent.executor import execute_action
from agent.parser import parse_react_output
from data.dataset_config import DatasetConfig
from prompts.builder import build_prompt
from state.schema import AgentState
from state.store import (
    add_evidence,
    advance_step,
    append_error,
    append_history,
    get_last_hypothesis,
    merge_metadata,
    record_contradiction,
    record_hypothesis_if_changed,
    set_promising_features,
    update_feature_status,
    update_analyzed_feature,
)
from utils.human_readable import parse_thought_fields, summarize_action, summarize_observation
from utils.reproducibility import build_reproducibility_metadata, hash_text_sha256

LlmCallable = Callable[[str], str]
MAX_TOTAL_PARSE_ERRORS = 2
MAX_CONSECUTIVE_PARSE_ERRORS = 2


def _is_high_end_model(model_name: str) -> bool:
    return "5." in model_name


def _is_parse_failure_status(status: str) -> bool:
    return status in {"PARSE_ERROR", "INVALID_JSON"}


def _mark_parse_error_termination(
    state: AgentState,
    *,
    model_name: str,
    step_id: int,
) -> None:
    message = f"Run stopped early due to parse errors (model: {model_name})"
    merge_metadata(
        state,
        {
            "status": "terminated_due_to_parse_errors",
            "termination_log": message,
        },
    )
    append_error(
        state,
        {
            "step_id": step_id,
            "ok": False,
            "error_code": "RUN_TERMINATED",
            "error_message": message,
        },
    )


def _print_trace_step(
    step_id: int,
    thought: str | None,
    action: str | None,
    action_input: dict[str, Any] | None,
    observation: dict[str, Any],
    status: str,
) -> None:
    thought_fields = parse_thought_fields(thought)

    print()
    print("-" * 72)
    print(f"STEP {step_id:02d} | STATUS: {status}")
    print("-" * 72)
    print(
        f"HYPOTHESIS : {thought_fields.get('hypothesis') or thought or 'No useful thought was recorded for this step.'}"
    )
    if thought_fields.get("scope"):
        print(f"SCOPE      : {thought_fields['scope']}")
    if thought_fields.get("next_action"):
        print(f"PLAN       : {thought_fields['next_action']}")
    print(f"ACTION     : {summarize_action(action, action_input)}")
    print(f"OBSERVATION: {summarize_observation(observation)}")


def _extract_hypothesis(thought: str | None) -> str | None:
    if not isinstance(thought, str):
        return None
    marker = "Hypothesis:"
    start = thought.find(marker)
    if start < 0:
        return None
    remainder = thought[start + len(marker):].strip()
    hypothesis = remainder.split(" | ", 1)[0].strip()
    return hypothesis or None


def _prompt_has_overview(prompt_text: str) -> bool:
    marker = "ADDITIONAL_CANDIDATES:\n"
    start = prompt_text.find(marker)
    if start < 0:
        return False
    remainder = prompt_text[start + len(marker):].lstrip()
    return not remainder.startswith("NONE")


def _increment_overview_usage(state: AgentState, prompt_text: str) -> None:
    if not _prompt_has_overview(prompt_text):
        return
    count = state.metadata.get("overview_usage", 0)
    try:
        count = int(count) + 1
    except Exception:
        count = 1
    state.metadata["overview_usage"] = count


def _resolve_hypothesis_feature(state: AgentState, hypothesis: str | None) -> str | None:
    if not isinstance(hypothesis, str) or not hypothesis:
        return None
    lowered = hypothesis.casefold()
    candidates = list(dict.fromkeys(
        [str(feature) for feature in state.evidence_by_feature.keys()] +
        [str(feature) for feature in state.available_features]
    ))
    matches = [
        feature for feature in candidates if feature and feature.casefold() in lowered]
    if not matches:
        return None
    return sorted(matches, key=lambda feature: (-len(feature), feature))[0]


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
) -> int | None:
    evidence_index: int | None = None
    evidence_block = tool_result.get("evidence")
    if isinstance(evidence_block, dict):
        evidence_index = add_evidence(state, feature_name, evidence_block)

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
    }
    update_analyzed_feature(state, feature_name, evidence)

    ranked_features = sorted(
        state.analyzed_features.items(),
        key=lambda item: (
            len(item[1].get("tools_used", [])),
            item[0],
        ),
        reverse=True,
    )
    set_promising_features(state, [name for name, _ in ranked_features])
    return evidence_index


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
    total_parse_failures = 0
    consecutive_parse_failures = 0
    high_end_model = _is_high_end_model(model_name)

    while state.current_step < state.max_steps:
        step_id = state.current_step + 1
        prompt_text = build_prompt(state, tool_names)
        _increment_overview_usage(state, prompt_text)

        try:
            raw_model_output = llm_callable(prompt_text)
        except Exception as exc:  # noqa: BLE001
            observation = {
                "ok": False,
                "error_code": "LLM_ERROR",
                "error_message": str(exc),
            }
            if trace:
                _print_trace_step(step_id, None, None, None,
                                  observation, "LLM_ERROR")
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
            status = parsed.get("error_code", "PARSE_ERROR")
            if not _is_parse_failure_status(status):
                status = "PARSE_ERROR"
            observation = {
                "ok": False,
                "error_code": status,
                "error_message": parsed.get("error_message", "Parser failure."),
            }
            if trace:
                _print_trace_step(
                    step_id,
                    "The model output did not follow the expected format.",
                    None,
                    None,
                    observation,
                    status,
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
                status=status,
            )
            total_parse_failures += 1
            consecutive_parse_failures += 1
            advance_step(state)
            if high_end_model and (
                total_parse_failures >= MAX_TOTAL_PARSE_ERRORS
                or consecutive_parse_failures >= MAX_CONSECUTIVE_PARSE_ERRORS
            ):
                _mark_parse_error_termination(
                    state,
                    model_name=model_name,
                    step_id=step_id,
                )
                break
            continue

        consecutive_parse_failures = 0

        action = parsed["action"]
        action_input = parsed["action_input"]
        thought = parsed["thought"]
        result = execute_action(
            action=action,
            action_input=action_input,
            dataset_path=dataset_path,
            dataset_config=dataset_config,
            state=state,
            dataset_frame=dataset_frame,
            valid_numeric_features=valid_numeric_features,
            step=step_id,
        )

        status = "OK"
        result_feature_name: str | None = None
        evidence_index: int | None = None
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
            result_feature_name = result.get("feature_name")
            if not isinstance(result_feature_name, str) or not result_feature_name:
                result_feature_name = action_input.get(
                    "feature_name", "__dataset__")
            evidence_index = _update_state_after_tool(
                state, action, result_feature_name, result)

        hypothesis = _extract_hypothesis(thought)
        if hypothesis:
            previous_hypothesis = get_last_hypothesis(state)
            if previous_hypothesis and previous_hypothesis != hypothesis:
                contradiction_feature = _resolve_hypothesis_feature(
                    state, previous_hypothesis) or result_feature_name or action_input.get(
                    "feature_name", "__dataset__")
                contradiction_refs = None
                contradiction_evidence = state.evidence_by_feature.get(
                    contradiction_feature, [])
                if contradiction_evidence:
                    contradiction_refs = [len(contradiction_evidence) - 1]
                    update_feature_status(
                        state,
                        contradiction_feature,
                        "weakened",
                        reason=(
                            f"Hypothesis revised from '{previous_hypothesis}' to '{hypothesis}'."
                        ),
                    )
                record_contradiction(
                    state,
                    contradiction_feature,
                    reason=(
                        f"Hypothesis revised from '{previous_hypothesis}' to '{hypothesis}'."
                    ),
                    evidence_refs=contradiction_refs,
                )
            record_hypothesis_if_changed(state, hypothesis)

        if trace:
            _print_trace_step(step_id, thought, action,
                              action_input, result, status)

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
