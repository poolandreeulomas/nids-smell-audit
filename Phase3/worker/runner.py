"""Execution wrapper for the Phase 3A Worker component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from tools.registry import get_tool_capability_records
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from worker.contracts import SCHEMA_VERSION, build_worker_output
from worker.context_resolver import build_local_context_records
from worker.execution_adapter import build_action_tool_map, execute_worker_action, prepare_worker_dataset
from worker.prompt_builder import build_worker_prompt
from worker.parser import parse_worker_step_response
from worker.runtime_artifacts import build_worker_artifact_paths, save_worker_artifacts
from worker.validator import (
    validate_worker_output,
    validate_worker_result,
    validate_worker_runtime_refs,
    validate_worker_step_decision,
    validate_worker_task,
)
from instrumentation import phase_start, phase_end, validation_result, worker_step, exception, phase_message


WorkerCallable = Callable[[str], str]


def _step_mode(current_step: int, max_steps: int) -> str:
    if current_step >= max_steps:
        return "final_synthesis"
    if current_step in {1, 2}:
        return "reasoning_only"
    if current_step % 2 == 1:
        return "action_window"
    return "reasoning_only"


def _allowed_decisions_for_step(current_step: int, max_steps: int) -> set[str]:
    step_mode = _step_mode(current_step, max_steps)
    if step_mode == "reasoning_only":
        return {"continue"}
    if step_mode == "action_window":
        return {"continue", "action"}
    return {"finish"}


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_worker_callable(
    model_name: str,
    temperature: float = 0.0,
) -> WorkerCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run worker."
            ) from exc

        client = OpenAI()
        response = client.responses.create(
            **build_responses_create_kwargs(
                model_name=model_name,
                prompt_text=prompt_text,
                temperature=temperature,
            )
        )
        return extract_response_text(response)

    return _call_llm


def _build_action_guidance(
    allowed_actions: list[str],
    capability_records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    guidance: list[dict[str, Any]] = []
    for tool_name, record in capability_records.items():
        action_class = str(record.get("epistemic_role") or "").strip()
        if action_class not in allowed_actions:
            continue
        guidance.append(
            {
                "action_class": action_class,
                "supported_scopes": list(record.get("supported_scopes") or []),
                "required_inputs": list(record.get("required_inputs") or []),
                "boundedness_notes": str(record.get("boundedness_notes") or ""),
            }
        )
    guidance.sort(key=lambda item: item["action_class"])
    return guidance


def _build_runtime_local_context_index(local_context_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(record.get("context_ref") or "").strip(): dict(record)
        for record in local_context_records
        if isinstance(record, dict) and str(record.get("context_ref") or "").strip()
    }


def run_worker(
    worker_task: dict[str, Any],
    worker_runtime_refs: dict[str, Any],
    *,
    batch_id: str,
    round_id: str,
    llm_callable: WorkerCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
    investigation_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_worker_task = worker_task if isinstance(worker_task, dict) else {}
    raw_worker_runtime_refs = worker_runtime_refs if isinstance(
        worker_runtime_refs, dict) else {}
    normalized_batch_id = str(
        batch_id or "unknown_batch").strip() or "unknown_batch"
    normalized_round_id = str(
        round_id or "unknown_round").strip() or "unknown_round"
    task_id = str(raw_worker_task.get("task_id")
                  or "unknown_task").strip() or "unknown_task"
    hypothesis_id = str(raw_worker_task.get("hypothesis_id")
                        or "unknown_hypothesis").strip() or "unknown_hypothesis"

    capability_records = get_tool_capability_records()
    known_action_classes = {
        str(record.get("epistemic_role") or "").strip()
        for record in capability_records.values()
        if str(record.get("epistemic_role") or "").strip()
    }
    task_validation = validate_worker_task(
        raw_worker_task, known_action_classes=known_action_classes)
    runtime_refs_validation = validate_worker_runtime_refs(
        raw_worker_runtime_refs,
        expected_local_context_refs=set(
            raw_worker_task.get("local_context_refs") or []),
    )
    action_map_validation = build_action_tool_map(
        list(raw_worker_task.get("allowed_actions") or []),
        capability_records,
    )

    prompt_snapshots: list[dict[str, Any]] = []
    raw_model_responses: list[dict[str, Any]] = []
    parsed_steps: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    retry_events: list[dict[str, Any]] = []
    failure_events: list[dict[str, Any]] = []
    final_result_validation: dict[str, Any] = _report_error(
        "worker_result", "worker_result was not produced.")
    output_validation: dict[str, Any] = _report_error(
        "worker_output", "worker_output was not produced.")

    dataset_handles = raw_worker_runtime_refs.get(
        "dataset_handles") if isinstance(raw_worker_runtime_refs, dict) else {}
    semantic_substrate = {}
    if isinstance(dataset_handles, dict) and isinstance(dataset_handles.get("semantic_substrate"), dict):
        semantic_substrate = dict(
            dataset_handles.get("semantic_substrate") or {})
    local_context_records = build_local_context_records(
        semantic_substrate,
        list(raw_worker_task.get("local_context_refs") or []),
    )
    budget_rules = dict(raw_worker_runtime_refs.get("budget_rules") or {
    }) if isinstance(raw_worker_runtime_refs, dict) else {}
    local_context_index = _build_runtime_local_context_index(
        local_context_records)
    action_guidance = _build_action_guidance(
        list(raw_worker_task.get("allowed_actions") or []), capability_records)
    worker_result: dict[str, Any] = {}
    worker_output: dict[str, Any] = {}
    runtime_dataset: dict[str, Any] | None = None
    termination_cause = "validation_failed"
    steps_used = 0
    retries_used = 0

    start_time = perf_counter()
    phase_start("worker", batch_id=normalized_batch_id,
                round_id=normalized_round_id, task_id=task_id, hypothesis_id=hypothesis_id)
    if task_validation["ok"] and runtime_refs_validation["ok"] and action_map_validation["ok"]:
        dataset_path = str(raw_worker_runtime_refs.get(
            "dataset_handles", {}).get("dataset_path") or "")
        try:
            runtime_dataset = prepare_worker_dataset(dataset_path)
            callable_to_use = llm_callable or _build_openai_worker_callable(
                model_name, temperature)
            max_steps = int(budget_rules.get("max_steps", 0) or 0)
            max_retries = int(budget_rules.get("max_retries", 0) or 0)
            final_result_ready = False

            for step_index in range(1, max_steps + 1):
                steps_used = step_index
                attempt_index = 0
                repair_note: str | None = None
                step_mode = _step_mode(step_index, max_steps)
                allowed_decisions = _allowed_decisions_for_step(
                    step_index, max_steps)

                # Instrument worker step start
                worker_step("worker", task_id=task_id, step=step_index,
                            mode=step_mode, attempt=attempt_index)

                while True:
                    prompt_text = build_worker_prompt(
                        batch_id=normalized_batch_id,
                        round_id=normalized_round_id,
                        worker_task=raw_worker_task,
                        local_context_records=local_context_records,
                        action_guidance=action_guidance,
                        tool_events=tool_events,
                        budget_rules=budget_rules,
                        current_step=step_index,
                        repair_note=repair_note,
                        investigation_memory=investigation_memory,
                    )
                    prompt_snapshots.append(
                        {
                            "step_index": step_index,
                            "step_mode": step_mode,
                            "attempt_index": attempt_index,
                            "repair_note": repair_note,
                            "prompt_text": prompt_text,
                        }
                    )
                    raw_response_text = str(callable_to_use(prompt_text) or "")
                    raw_model_responses.append(
                        {
                            "step_index": step_index,
                            "step_mode": step_mode,
                            "attempt_index": attempt_index,
                            "raw_response_text": raw_response_text,
                        }
                    )

                    try:
                        parsed_step = parse_worker_step_response(
                            raw_response_text)
                    except ValueError as exc:
                        message = str(exc)
                        failure_events.append(
                            {
                                "step_index": step_index,
                                "attempt_index": attempt_index,
                                "failure_kind": "parse_error",
                                "message": message,
                            }
                        )
                        # Instrument parse validation failure
                        validation_result("worker", {"ok": False, "errors": [{"field": "raw_response", "message": message}]},
                                          batch_id=normalized_batch_id, round_id=normalized_round_id, task_id=task_id, hypothesis_id=hypothesis_id)
                        if attempt_index < max_retries:
                            attempt_index += 1
                            retries_used += 1
                            repair_note = message
                            retry_events.append(
                                {
                                    "step_index": step_index,
                                    "attempt_index": attempt_index,
                                    "reason": message,
                                    "retry_kind": "parse_repair",
                                }
                            )
                            continue
                        termination_cause = "parse_failure"
                        break

                    step_validation = validate_worker_step_decision(
                        parsed_step,
                        allowed_actions=set(
                            raw_worker_task.get("allowed_actions") or []),
                        known_context_refs=set(local_context_index.keys()),
                        allowed_decisions=allowed_decisions,
                        require_reasoning=step_mode != "final_synthesis",
                    )
                    step_actions = [dict(item) for item in (
                        parsed_step.get("actions") or []) if isinstance(item, dict)]
                    worker_step(
                        "worker",
                        task_id=task_id,
                        step=step_index,
                        mode=step_mode,
                        attempt=attempt_index,
                        decision=str(parsed_step.get("decision") or "unknown"),
                        actions=len(step_actions),
                    )
                    parsed_steps.append(
                        {
                            "step_index": step_index,
                            "step_mode": step_mode,
                            "attempt_index": attempt_index,
                            "parsed_step": parsed_step,
                            "validation": step_validation,
                        }
                    )
                    # Instrument per-step validation
                    validation_result("worker", step_validation, batch_id=normalized_batch_id,
                                      round_id=normalized_round_id, task_id=task_id, hypothesis_id=hypothesis_id, step=step_index)
                    if not step_validation["ok"]:
                        message = step_validation["errors"][0]["message"]
                        failure_events.append(
                            {
                                "step_index": step_index,
                                "attempt_index": attempt_index,
                                "failure_kind": "step_validation_error",
                                "message": message,
                            }
                        )
                        if attempt_index < max_retries:
                            attempt_index += 1
                            retries_used += 1
                            repair_note = message
                            retry_events.append(
                                {
                                    "step_index": step_index,
                                    "attempt_index": attempt_index,
                                    "reason": message,
                                    "retry_kind": "step_repair",
                                }
                            )
                            continue
                        termination_cause = "invalid_step"
                        break

                    if parsed_step["decision"] == "continue":
                        termination_cause = "reasoning_step_completed"
                        break

                    if parsed_step["decision"] == "action":
                        pending_tool_events: list[dict[str, Any]] = []
                        repair_reason = ""
                        needs_repair = False
                        for action_index, action_payload in enumerate(step_actions, start=1):
                            tool_event = execute_worker_action(
                                action_payload,
                                task_id=task_id,
                                step_index=step_index,
                                action_index=action_index,
                                action_count=len(step_actions),
                                action_tool_map=action_map_validation["action_tool_map"],
                                capability_records=capability_records,
                                runtime_dataset=runtime_dataset,
                                local_context_index=local_context_index,
                            )
                            tool_event["step_index"] = step_index
                            tool_event["action_index"] = action_index
                            pending_tool_events.append(tool_event)
                            # Instrument action execution result
                            print(
                                f"[WORKER] ACTION_EXEC task_id={task_id} step={step_index} action_index={action_index} ok={tool_event.get('ok')} execution_ok={tool_event.get('execution_ok')} call_id={tool_event.get('call_id')}")
                            if not tool_event["ok"] or not tool_event["execution_ok"]:
                                failure_events.append(
                                    {
                                        "step_index": step_index,
                                        "attempt_index": attempt_index,
                                        "failure_kind": "tool_execution_error",
                                        "message": tool_event.get("error_message") or "Worker tool execution failed.",
                                        "call_id": tool_event.get("call_id"),
                                    }
                                )
                                invalid_request = not tool_event.get(
                                    "request_validation", {}).get("ok", False)
                                if invalid_request and attempt_index < max_retries:
                                    needs_repair = True
                                    repair_reason = tool_event.get(
                                        "error_message") or "Choose a valid in-scope action."
                                    break
                        if needs_repair:
                            attempt_index += 1
                            retries_used += 1
                            repair_note = repair_reason
                            retry_events.append(
                                {
                                    "step_index": step_index,
                                    "attempt_index": attempt_index,
                                    "reason": repair_reason,
                                    "retry_kind": "action_repair",
                                }
                            )
                            continue
                        tool_events.extend(pending_tool_events)
                        termination_cause = "action_window_completed"
                        break

                    candidate_worker_result = dict(
                        parsed_step.get("worker_result", {}))
                    final_result_validation = validate_worker_result(
                        candidate_worker_result,
                        expected_task_id=task_id,
                        expected_hypothesis_id=hypothesis_id,
                        known_evidence_refs={event["call_id"]
                                             for event in tool_events},
                    )
                    # Instrument final result validation
                    validation_result("worker", final_result_validation, batch_id=normalized_batch_id,
                                      round_id=normalized_round_id, task_id=task_id, hypothesis_id=hypothesis_id)
                    if final_result_validation["ok"]:
                        worker_result = candidate_worker_result
                        worker_output = build_worker_output(
                            batch_id=normalized_batch_id,
                            round_id=normalized_round_id,
                            worker_result=worker_result,
                        )
                        output_validation = validate_worker_output(
                            worker_output,
                            expected_batch_id=normalized_batch_id,
                            expected_round_id=normalized_round_id,
                        )
                        if output_validation["ok"]:
                            termination_cause = "model_finish"
                            final_result_ready = True
                            break

                    message = final_result_validation["errors"][0]["message"] if final_result_validation[
                        "errors"] else "worker_result validation failed."
                    failure_events.append(
                        {
                            "step_index": step_index,
                            "attempt_index": attempt_index,
                            "failure_kind": "worker_result_validation_error",
                            "message": message,
                        }
                    )
                    if attempt_index < max_retries:
                        attempt_index += 1
                        retries_used += 1
                        repair_note = message
                        retry_events.append(
                            {
                                "step_index": step_index,
                                "attempt_index": attempt_index,
                                "reason": message,
                                "retry_kind": "result_repair",
                            }
                        )
                        continue
                    termination_cause = "invalid_result"
                    break

                if final_result_ready:
                    break
                if termination_cause in {"parse_failure", "invalid_step", "invalid_result"}:
                    break
            if not worker_result and termination_cause in {"step_completed", "action_window_completed", "reasoning_step_completed"}:
                termination_cause = "budget_exhausted"
        except Exception as exc:  # pragma: no cover
            failure_events.append(
                {
                    "step_index": steps_used,
                    "attempt_index": 0,
                    "failure_kind": "runtime_error",
                    "message": str(exc),
                }
            )
            termination_cause = "runtime_error"
            exception("worker", exc, round_id=normalized_round_id,
                      hypothesis_id=hypothesis_id, task_id=task_id)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    result_committed = bool(output_validation["ok"])

    operational_trace = {
        "task_id": task_id,
        "action_sequence": [
            {
                "step_index": event.get("step_index", index),
                "action_index": event.get("action_index", 1),
                "action_class": event.get("action", {}).get("action_class"),
                "context_ref": event.get("action", {}).get("context_ref"),
                "feature_name": event.get("action", {}).get("feature_name"),
                "related_feature_name": event.get("action", {}).get("related_feature_name"),
                "call_id": event.get("call_id"),
                "status": event.get("tool_result", {}).get("status"),
            }
            for index, event in enumerate(tool_events, start=1)
        ],
        "tool_events": tool_events,
        "retry_events": retry_events,
        "failure_events": failure_events,
        "budget_consumption": {
            "max_steps": budget_rules.get("max_steps"),
            "max_retries": budget_rules.get("max_retries"),
            "steps_used": steps_used,
            "retries_used": retries_used,
            "termination_cause": termination_cause,
            "result_committed": result_committed,
        },
    }

    validation_report = {
        "ok": (
            task_validation["ok"]
            and runtime_refs_validation["ok"]
            and action_map_validation["ok"]
            and final_result_validation["ok"]
            and output_validation["ok"]
        ),
        "schema_version": SCHEMA_VERSION,
        "task_validation": task_validation,
        "runtime_refs_validation": runtime_refs_validation,
        "action_map_validation": {
            "ok": action_map_validation["ok"],
            "errors": action_map_validation["errors"],
            "warnings": [],
        },
        "worker_result_validation": final_result_validation,
        "worker_output_validation": output_validation,
    }

    component_status = "ok" if validation_report["ok"] else "error"
    runtime_metrics = {
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "task_id": task_id,
        "hypothesis_id": hypothesis_id,
        "model_name": model_name,
        "duration_ms": duration_ms,
        "status": component_status,
        "worker_status": worker_result.get("status", "unavailable"),
        "steps_used": steps_used,
        "retries_used": retries_used,
        "prompt_count": len(prompt_snapshots),
        "tool_event_count": len(tool_events),
        "failure_event_count": len(failure_events),
        "termination_cause": termination_cause,
        "result_committed": result_committed,
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "worker",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "task_id": task_id,
        "hypothesis_id": hypothesis_id,
        "status": component_status,
        "worker_status": worker_result.get("status", "unavailable"),
        "validation_ok": validation_report["ok"],
        "result_committed": result_committed,
        "model_name": model_name,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }
    replay_metadata = {
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
    }

    artifact_paths = build_worker_artifact_paths(
        task_id=task_id, log_dir=log_dir)
    persisted_paths = save_worker_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        worker_task=raw_worker_task,
        worker_runtime_refs=raw_worker_runtime_refs,
        prompt_snapshots=prompt_snapshots,
        raw_model_responses=raw_model_responses,
        parsed_steps=parsed_steps,
        tool_events=tool_events,
        retry_events=retry_events,
        failure_events=failure_events,
        worker_result=worker_result,
        worker_output=worker_output,
        operational_trace=operational_trace,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    # Instrument phase end and final validation
    validation_result("worker", validation_report, batch_id=normalized_batch_id,
                      round_id=normalized_round_id, task_id=task_id, hypothesis_id=hypothesis_id)
    phase_end("worker", elapsed_s=duration_ms / 1000.0, batch_id=normalized_batch_id,
              round_id=normalized_round_id, task_id=task_id, hypothesis_id=hypothesis_id)

    return {
        "component_run": component_run,
        "worker_task": raw_worker_task,
        "worker_runtime_refs": raw_worker_runtime_refs,
        "prompt_snapshots": prompt_snapshots,
        "raw_model_responses": raw_model_responses,
        "parsed_steps": parsed_steps,
        "tool_events": tool_events,
        "retry_events": retry_events,
        "failure_events": failure_events,
        "worker_result": worker_result,
        "worker_output": worker_output,
        "operational_trace": operational_trace,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }
