"""Pure observability adapters for Phase 3A runtime artifact review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkerStepAttemptTrace:
    """One persisted Worker model attempt for a given step."""

    step_index: int
    step_mode: str
    attempt_index: int
    prompt_text: str
    raw_response_text: str
    parsed_output: dict[str, Any]
    validator_output: dict[str, Any]
    decision: str
    reasoning_summary: str
    proposed_actions: list[dict[str, Any]]
    worker_result: dict[str, Any]
    repair_note: str | None = None


@dataclass
class WorkerStepTrace:
    """Structured, step-scoped trace reconstructed from persisted Worker artifacts."""

    step_index: int
    step_mode: str
    attempts: list[WorkerStepAttemptTrace]
    latest_attempt: WorkerStepAttemptTrace
    decision: str
    reasoning_summary: str
    proposed_actions: list[dict[str, Any]]
    executed_actions: list[dict[str, Any]]
    action_results: list[dict[str, Any]]
    execution_history_before_step: list[dict[str, Any]]
    retry_events: list[dict[str, Any]]
    failure_events: list[dict[str, Any]]
    flags: list[str]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _step_attempt_key(record: dict[str, Any], *, fallback_index: int) -> tuple[int, int]:
    return (
        _as_int(record.get("step_index"), default=fallback_index + 1),
        _as_int(record.get("attempt_index"), default=0),
    )


def _extract_actions(parsed_output: dict[str, Any]) -> list[dict[str, Any]]:
    actions = parsed_output.get("actions")
    if isinstance(actions, list):
        return [dict(item) for item in actions if isinstance(item, dict)]

    single_action = parsed_output.get("action")
    if isinstance(single_action, dict):
        return [dict(single_action)]
    return []


def _normalize_messages(items: Any) -> list[str]:
    messages: list[str] = []
    for item in _as_list(items):
        if isinstance(item, dict):
            field_name = _as_string(item.get("field"))
            message = _as_string(item.get("message") or item.get(
                "detail") or item.get("warning"))
            if field_name and message:
                messages.append(f"{field_name}: {message}")
            elif message:
                messages.append(message)
            elif field_name:
                messages.append(field_name)
            continue
        text = _as_string(item)
        if text:
            messages.append(text)
    return messages


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _as_string(value)
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _build_action_result_summary(event: dict[str, Any]) -> dict[str, Any]:
    tool_result = _as_dict(event.get("tool_result"))
    tool_metrics = _as_dict(event.get("tool_metrics"))
    return {
        "call_id": _as_string(event.get("call_id")),
        "tool_name": _as_string(event.get("tool_name")),
        "status": _as_string(tool_result.get("status") or event.get("execution_ok") or event.get("ok")),
        "action": _as_dict(event.get("action")),
        "observations": tool_result.get("observations", {}),
        "limitations": _as_list(tool_result.get("limitations")),
        "error_message": _as_string(event.get("error_message")),
        "evidence_refs": _as_list(tool_result.get("evidence_refs") or event.get("evidence_refs")),
        "tool_metrics": tool_metrics,
    }


def _build_execution_history_entry(event: dict[str, Any]) -> dict[str, Any]:
    tool_result = _as_dict(event.get("tool_result"))
    tool_metrics = _as_dict(event.get("tool_metrics"))
    observations = _as_dict(tool_result.get("observations"))
    observation_preview = ""
    for key in ("feature_name", "related_feature_name", "feature", "value"):
        if observations.get(key) is not None:
            observation_preview = f"{key}={observations.get(key)}"
            break

    return {
        "step_index": _as_int(event.get("step_index"), default=0),
        "call_id": _as_string(event.get("call_id")),
        "tool_name": _as_string(event.get("tool_name")),
        "status": _as_string(tool_result.get("status") or event.get("execution_ok") or event.get("ok")),
        "action": _as_dict(event.get("action")),
        "observation_preview": observation_preview,
        "tool_metrics": tool_metrics,
    }


def _build_retry_flag(event: dict[str, Any]) -> str:
    reason = _as_string(event.get("reason") or event.get(
        "retry_reason") or event.get("kind"))
    message = _as_string(event.get("message") or event.get(
        "detail") or event.get("error_message"))
    if reason and message:
        return f"retry: {reason} - {message}"
    if reason:
        return f"retry: {reason}"
    return message


def _build_failure_flag(event: dict[str, Any]) -> str:
    kind = _as_string(event.get("failure_kind") or event.get(
        "kind") or event.get("failure_type"))
    message = _as_string(event.get("message") or event.get(
        "detail") or event.get("error_message"))
    if kind and message:
        return f"{kind}: {message}"
    if kind:
        return kind
    return message


def build_worker_step_traces(
    *,
    prompt_snapshots: list[dict[str, Any]],
    raw_model_responses: list[dict[str, Any]],
    parsed_steps: list[dict[str, Any]],
    tool_events: list[dict[str, Any]],
    retry_events: list[dict[str, Any]],
    failure_events: list[dict[str, Any]],
) -> list[WorkerStepTrace]:
    """Reconstruct step-local Worker traces from persisted artifact lists."""

    prompt_map = {
        _step_attempt_key(_as_dict(item), fallback_index=index): _as_dict(item)
        for index, item in enumerate(prompt_snapshots)
    }
    response_map = {
        _step_attempt_key(_as_dict(item), fallback_index=index): _as_dict(item)
        for index, item in enumerate(raw_model_responses)
    }
    parsed_map = {
        _step_attempt_key(_as_dict(item), fallback_index=index): _as_dict(item)
        for index, item in enumerate(parsed_steps)
    }

    all_attempt_keys = sorted(
        set(prompt_map) | set(response_map) | set(parsed_map))
    grouped_attempt_keys: dict[int, list[tuple[int, int]]] = {}
    for key in all_attempt_keys:
        grouped_attempt_keys.setdefault(key[0], []).append(key)

    tool_events_by_step: dict[int, list[dict[str, Any]]] = {}
    for raw_event in tool_events:
        event = _as_dict(raw_event)
        step_index = _as_int(event.get("step_index"), default=0)
        tool_events_by_step.setdefault(step_index, []).append(event)

    retry_events_by_step: dict[int, list[dict[str, Any]]] = {}
    for raw_event in retry_events:
        event = _as_dict(raw_event)
        step_index = _as_int(event.get("step_index"), default=0)
        retry_events_by_step.setdefault(step_index, []).append(event)

    failure_events_by_step: dict[int, list[dict[str, Any]]] = {}
    for raw_event in failure_events:
        event = _as_dict(raw_event)
        step_index = _as_int(event.get("step_index"), default=0)
        failure_events_by_step.setdefault(step_index, []).append(event)

    traces: list[WorkerStepTrace] = []
    all_tool_history = sorted(
        [_as_dict(item) for item in tool_events],
        key=lambda event: (
            _as_int(event.get("step_index"), default=0),
            _as_int(event.get("action_index"), default=0),
        ),
    )

    for step_index in sorted(grouped_attempt_keys):
        attempts: list[WorkerStepAttemptTrace] = []
        for key in sorted(grouped_attempt_keys[step_index], key=lambda item: item[1]):
            prompt_snapshot = prompt_map.get(key, {})
            raw_response = response_map.get(key, {})
            parsed_step_record = parsed_map.get(key, {})
            parsed_output = _as_dict(parsed_step_record.get("parsed_step"))
            validator_output = _as_dict(parsed_step_record.get("validation"))
            step_mode = _as_string(
                prompt_snapshot.get("step_mode")
                or raw_response.get("step_mode")
                or parsed_step_record.get("step_mode")
            )
            attempts.append(
                WorkerStepAttemptTrace(
                    step_index=step_index,
                    step_mode=step_mode or "unknown",
                    attempt_index=key[1],
                    prompt_text=_as_string(prompt_snapshot.get("prompt_text")),
                    raw_response_text=_as_string(
                        raw_response.get("raw_response_text")),
                    parsed_output=parsed_output,
                    validator_output=validator_output,
                    decision=_as_string(parsed_output.get("decision")),
                    reasoning_summary=_as_string(
                        parsed_output.get("reasoning")),
                    proposed_actions=_extract_actions(parsed_output),
                    worker_result=_as_dict(parsed_output.get("worker_result")),
                    repair_note=_as_string(
                        prompt_snapshot.get("repair_note")) or None,
                )
            )

        latest_attempt = attempts[-1]
        step_tool_events = sorted(
            tool_events_by_step.get(step_index, []),
            key=lambda event: _as_int(event.get("action_index"), default=0),
        )
        step_retry_events = retry_events_by_step.get(step_index, [])
        step_failure_events = failure_events_by_step.get(step_index, [])
        flags: list[str] = []
        for attempt in attempts:
            flags.extend(_normalize_messages(
                attempt.validator_output.get("warnings")))
            flags.extend(_normalize_messages(
                attempt.validator_output.get("errors")))
        for event in step_tool_events:
            flags.extend(_normalize_messages(
                _as_dict(event.get("request_validation")).get("warnings")))
            flags.extend(_normalize_messages(
                _as_dict(event.get("request_validation")).get("errors")))
            flags.extend(_normalize_messages(
                _as_dict(event.get("result_validation")).get("warnings")))
            flags.extend(_normalize_messages(
                _as_dict(event.get("result_validation")).get("errors")))
            error_message = _as_string(event.get("error_message"))
            if error_message:
                flags.append(error_message)
        flags.extend(filter(None, (_build_retry_flag(event)
                     for event in step_retry_events)))
        flags.extend(filter(None, (_build_failure_flag(event)
                     for event in step_failure_events)))

        traces.append(
            WorkerStepTrace(
                step_index=step_index,
                step_mode=latest_attempt.step_mode,
                attempts=attempts,
                latest_attempt=latest_attempt,
                decision=latest_attempt.decision,
                reasoning_summary=latest_attempt.reasoning_summary,
                proposed_actions=list(latest_attempt.proposed_actions),
                executed_actions=[_as_dict(event.get("action"))
                                  for event in step_tool_events],
                action_results=[_build_action_result_summary(
                    event) for event in step_tool_events],
                execution_history_before_step=[
                    _build_execution_history_entry(event)
                    for event in all_tool_history
                    if _as_int(event.get("step_index"), default=0) < step_index
                ],
                retry_events=[dict(event) for event in step_retry_events],
                failure_events=[dict(event) for event in step_failure_events],
                flags=_dedupe_preserve_order(flags),
            )
        )

    return traces
