"""Structured runtime instrumentation helpers for Phase 3A components.

This module provides small, grep-friendly print helpers to emit
deterministic, structured phase/start/end/validation/barrier logs.
These helpers intentionally only print and do not alter runtime state.
"""

from __future__ import annotations

import json
import os
import threading
import traceback
from typing import Any, Callable


InstrumentationListener = Callable[[dict[str, Any]], None]

_LISTENERS: list[InstrumentationListener] = []
_LISTENER_LOCK = threading.Lock()


def _json(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
    except Exception:
        return str(obj)


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def register_listener(listener: InstrumentationListener) -> None:
    with _LISTENER_LOCK:
        if listener not in _LISTENERS:
            _LISTENERS.append(listener)


def unregister_listener(listener: InstrumentationListener) -> None:
    with _LISTENER_LOCK:
        if listener in _LISTENERS:
            _LISTENERS.remove(listener)


def _notify_listeners(event: dict[str, Any]) -> None:
    with _LISTENER_LOCK:
        listeners = list(_LISTENERS)
    for listener in listeners:
        try:
            listener(dict(event))
        except Exception:
            continue


def _emit_event(
    *,
    event_type: str,
    component: str,
    payload: dict[str, Any] | None = None,
    terminal_lines: list[str] | None = None,
) -> None:
    _notify_listeners(
        {
            "event_type": event_type,
            "component": component,
            "payload": dict(payload or {}),
            "terminal_lines": list(terminal_lines or []),
        }
    )


def tracing_enabled() -> bool:
    return _env_flag("PHASE3A_VERBOSE_RUNTIME", True)


def print_validation() -> bool:
    return _env_flag("PHASE3A_PRINT_VALIDATION", tracing_enabled())


def print_timing() -> bool:
    return _env_flag("PHASE3A_PRINT_TIMING", tracing_enabled())


def print_worker_steps() -> bool:
    return _env_flag("PHASE3A_PRINT_WORKER_STEPS", tracing_enabled())


def print_barriers() -> bool:
    return _env_flag("PHASE3A_PRINT_BARRIERS", tracing_enabled())


def print_raw_validation_errors() -> bool:
    return _env_flag("PHASE3A_PRINT_RAW_VALIDATION_ERRORS", tracing_enabled())


def _id_parts(**ids: Any) -> str:
    return " ".join(f"{key}={value}" for key, value in sorted(ids.items()) if value is not None)


def phase_start(component: str, **ids: Any) -> None:
    id_parts = _id_parts(**ids)
    suffix = f" {id_parts}" if id_parts else ""
    line = f"[{component.upper()}] START{suffix}"
    if tracing_enabled():
        print(line)
    _emit_event(
        event_type="PHASE_START",
        component=component,
        payload={"ids": dict(ids)},
        terminal_lines=[line] if tracing_enabled() else [],
    )


def phase_end(component: str, *, elapsed_s: float | None = None, **ids: Any) -> None:
    id_parts = _id_parts(**ids)
    suffix = f" {id_parts}" if id_parts else ""
    elapsed = f" ({elapsed_s:.1f}s)" if elapsed_s is not None and print_timing(
    ) else ""
    line = f"[{component.upper()}] END{elapsed}{suffix}"
    if tracing_enabled():
        print(line)
    _emit_event(
        event_type="PHASE_END",
        component=component,
        payload={"ids": dict(ids), "elapsed_s": elapsed_s},
        terminal_lines=[line] if tracing_enabled() else [],
    )


def validation_result(component: str, validation: dict[str, Any], **ids: Any) -> None:
    status = "OK" if validation.get("ok") else "FAILED"
    id_parts = _id_parts(**ids)
    suffix = f" {id_parts}" if id_parts else ""
    terminal_lines: list[str] = []
    summary_line = f"[{component.upper()}] VALIDATION {status}{suffix}"
    if print_validation():
        print(summary_line)
        terminal_lines.append(summary_line)
        if not validation.get("ok") and print_raw_validation_errors():
            raw_payload = _json(validation)
            print(raw_payload)
            terminal_lines.extend(raw_payload.splitlines())
    _emit_event(
        event_type="VALIDATION_RESULT",
        component=component,
        payload={"ids": dict(ids), "validation": dict(validation or {})},
        terminal_lines=terminal_lines,
    )


def barrier_status(component: str, *, expected: int | None = None, completed: int | None = None, waiting_for: list[str] | None = None, **ids: Any) -> None:
    id_parts = _id_parts(**ids)
    waiting = waiting_for or []
    suffix = f" {id_parts}" if id_parts else ""
    line = f"[{component.upper()}_BARRIER] expected_tasks={expected} completed_tasks={completed} waiting_for={waiting}{suffix}"
    if print_barriers():
        print(line)
    _emit_event(
        event_type="BARRIER_STATUS",
        component=component,
        payload={
            "ids": dict(ids),
            "expected": expected,
            "completed": completed,
            "waiting_for": list(waiting),
        },
        terminal_lines=[line] if print_barriers() else [],
    )


def worker_step(component: str, *, task_id: str | None = None, step: int | None = None, mode: str | None = None, attempt: int | None = None, decision: str | None = None, actions: int | None = None) -> None:
    parts = []
    if task_id is not None:
        parts.append(f"task_id={task_id}")
    if step is not None:
        parts.append(f"step={step}")
    if mode is not None:
        parts.append(f"mode={mode}")
    if attempt is not None:
        parts.append(f"attempt={attempt}")
    if decision is not None:
        parts.append(f"decision={decision}")
    if actions is not None:
        parts.append(f"actions={actions}")
    line = f"[{component.upper()}_STEP] " + " ".join(parts)
    if print_worker_steps():
        print(line)
    _emit_event(
        event_type="WORKER_STEP",
        component=component,
        payload={
            "task_id": task_id,
            "step": step,
            "mode": mode,
            "attempt": attempt,
            "decision": decision,
            "actions": actions,
        },
        terminal_lines=[line] if print_worker_steps() else [],
    )


def phase_message(component: str, message: str, **ids: Any) -> None:
    id_parts = _id_parts(**ids)
    suffix = f" {id_parts}" if id_parts else ""
    line = f"[{component.upper()}]{suffix} {message}"
    if tracing_enabled():
        print(line)
    _emit_event(
        event_type="PHASE_MESSAGE",
        component=component,
        payload={"ids": dict(ids), "message": message},
        terminal_lines=[line] if tracing_enabled() else [],
    )


def exception(component: str, exc: Exception, *, round_id: Any = None, hypothesis_id: Any = None, task_id: Any = None) -> None:
    traceback_lines = traceback.format_exception(
        type(exc), exc, exc.__traceback__)
    header = f"[{component.upper()}] EXCEPTION round_id={round_id} hypothesis_id={hypothesis_id} task_id={task_id}"
    terminal_lines = [header, *[line.rstrip("\n") for line in traceback_lines]]
    if tracing_enabled():
        print(header)
        traceback.print_exception(type(exc), exc, exc.__traceback__)
    _emit_event(
        event_type="EXCEPTION",
        component=component,
        payload={
            "round_id": round_id,
            "hypothesis_id": hypothesis_id,
            "task_id": task_id,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback_lines": [line.rstrip("\n") for line in traceback_lines],
        },
        terminal_lines=terminal_lines if tracing_enabled() else [],
    )
