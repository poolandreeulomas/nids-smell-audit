"""Execution wrapper for the Phase 3A Critic component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from critic.contracts import SCHEMA_VERSION, build_critic_feedback_payload
from critic.input_resolver import build_critic_context
from critic.parser import parse_critic_response
from critic.prompt_builder import PROMPT_VERSION, build_critic_prompt
from critic.runtime_artifacts import build_critic_artifact_paths, save_critic_artifacts
from critic.validator import validate_critic_feedback_payload, validate_critic_input_bundle
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception


CriticCallable = Callable[[str], str]


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _validate_state_manager_source_bundle(
    state_manager_bundle: dict[str, Any],
) -> dict[str, Any]:
    raw = state_manager_bundle if isinstance(
        state_manager_bundle, dict) else {}
    component_run = dict(raw.get("component_run", {}) or {})
    updated_batch_state = dict(raw.get("updated_batch_state", {}) or {})
    errors: list[dict[str, str]] = []

    if not isinstance(state_manager_bundle, dict):
        errors.append({"field": "state_manager_bundle",
                      "message": "state_manager_bundle must be an object."})
    if not bool(component_run.get("validation_ok", False)):
        errors.append(
            {
                "field": "component_run.validation_ok",
                "message": "Critic requires a validation-ok State Manager source bundle.",
            }
        )
    if not bool(component_run.get("state_committed", False)):
        errors.append(
            {
                "field": "component_run.state_committed",
                "message": "Critic requires a committed State Manager source bundle.",
            }
        )
    if not updated_batch_state:
        errors.append(
            {
                "field": "updated_batch_state",
                "message": "Critic requires the committed updated_batch_state artifact.",
            }
        )

    return {"ok": not errors, "errors": errors, "warnings": []}


def _build_openai_critic_callable(
    model_name: str,
    temperature: float = 0.0,
) -> CriticCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run critic."
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


def run_critic(
    state_manager_bundle: dict[str, Any],
    *,
    llm_callable: CriticCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
    is_final_round: bool = False,
    round_component_bundles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_id = f"critic_{uuid4().hex}"
    critic_context = build_critic_context(
        state_manager_bundle if isinstance(state_manager_bundle, dict) else {},
        is_final_round=is_final_round,
        round_component_bundles=round_component_bundles,
    )
    known_evidence_refs = set(critic_context.pop("known_evidence_refs", []))
    source_state_manager_run_path = str(
        critic_context.pop("source_state_manager_run_path", "") or ""
    )
    observed_modules = {
        str(module_name).strip()
        for module_name in critic_context.pop("observed_modules", [])
        if str(module_name).strip()
    }
    critic_input_min = dict(critic_context.get("critic_input_min", {}))
    refined_state_summary = dict(
        critic_context.get("refined_state_summary", {}))
    module_behavior_summaries = list(
        critic_context.get("module_behavior_summaries", []))
    process_signal_summary = dict(
        critic_context.get("process_signal_summary", {}))

    batch_id = str(critic_input_min.get("batch_id")
                   or "unknown_batch").strip() or "unknown_batch"
    round_id = str(critic_input_min.get("round_id")
                   or "unknown_round").strip() or "unknown_round"

    critic_context_payload = {
        "critic_input_min": critic_input_min,
        "refined_state_summary": refined_state_summary,
        "module_behavior_summaries": module_behavior_summaries,
        "process_signal_summary": process_signal_summary,
    }
    input_validation = validate_critic_input_bundle(
        critic_context_payload,
        expected_batch_id=batch_id,
        expected_round_id=round_id,
    )
    source_state_validation = _validate_state_manager_source_bundle(
        state_manager_bundle if isinstance(state_manager_bundle, dict) else {},
    )

    prompt_text = ""
    raw_response_text = ""
    critic_feedback_payload: dict[str, Any] = {}
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    feedback_validation: dict[str, Any] = _report_error(
        "critic_feedback_payload",
        "critic_feedback_payload was not produced.",
    )

    start_time = perf_counter()
    phase_start("critic", batch_id=batch_id, round_id=round_id)
    if input_validation["ok"] and source_state_validation["ok"] and not is_final_round:
        prompt_text = build_critic_prompt(
            batch_id=batch_id,
            round_id=round_id,
            critic_input_min=critic_input_min,
            refined_state_summary=refined_state_summary,
            module_behavior_summaries=module_behavior_summaries,
            process_signal_summary=process_signal_summary,
        )
        try:
            callable_to_use = llm_callable or _build_openai_critic_callable(
                model_name, temperature)
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_payload = parse_critic_response(raw_response_text)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            feedback_validation = validate_critic_feedback_payload(
                parsed_payload,
                expected_batch_id=batch_id,
                expected_round_id=round_id,
                known_evidence_refs=known_evidence_refs,
                allowed_module_names=observed_modules,
            )
            if feedback_validation["ok"]:
                critic_feedback_payload = build_critic_feedback_payload(
                    batch_id=batch_id,
                    round_id=round_id,
                    module_feedback=list(
                        parsed_payload.get("module_feedback", [])),
                )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("critic", parse_validation,
                              batch_id=batch_id, round_id=round_id)
        except Exception as exc:  # pragma: no cover
            parse_validation = _report_error("runtime", str(exc))
            exception("critic", exc, round_id=round_id)
    elif input_validation["ok"] and is_final_round:
        parse_validation = {"ok": True, "errors": [], "warnings": []}
        feedback_validation = {
            "ok": True,
            "errors": [],
            "warnings": [],
            "stats": {
                "module_feedback_count": 0,
                "average_suggestion_length": 0.0,
            },
        }

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    final_round_gate = {
        "ok": True,
        "skipped": bool(is_final_round),
        "status": "skipped_final_round" if is_final_round else "allowed_non_final_round",
        "message": (
            "Critic execution was skipped because the selected round was marked final."
            if is_final_round
            else "Critic execution was allowed because the selected round was marked non-final."
        ),
    }
    validation_report = {
        "ok": input_validation["ok"]
        and source_state_validation["ok"]
        and final_round_gate["ok"]
        and parse_validation["ok"]
        and feedback_validation["ok"],
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "final_round_gate": final_round_gate,
        "input_validation": input_validation,
        "source_state_validation": source_state_validation,
        "parse_validation": parse_validation,
        "critic_feedback_validation": feedback_validation,
    }
    status = "skipped" if is_final_round and input_validation["ok"] else (
        "ok" if validation_report["ok"] else "error")
    feedback_committed = bool(critic_feedback_payload)
    module_feedback_count = len(
        critic_feedback_payload.get("module_feedback", []))

    runtime_metrics = {
        "request_id": request_id,
        "batch_id": batch_id,
        "round_id": round_id,
        "prompt_version": PROMPT_VERSION,
        "model_name": model_name,
        "temperature": temperature,
        "duration_ms": duration_ms,
        "status": status,
        "final_round_gate_status": final_round_gate["status"],
        "module_feedback_count": module_feedback_count,
        "feedback_committed": feedback_committed,
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "critic",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "round_id": round_id,
        "status": status,
        "validation_ok": validation_report["ok"],
        "final_round_gate_status": final_round_gate["status"],
        "module_feedback_count": module_feedback_count,
        "feedback_committed": feedback_committed,
        "model_name": model_name,
        "temperature": temperature,
        "source_state_manager_run_path": source_state_manager_run_path,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }
    replay_metadata = {
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
        "is_final_round": bool(is_final_round),
        "source_state_manager_run_path": source_state_manager_run_path,
    }

    artifact_paths = build_critic_artifact_paths(
        round_id=round_id,
        log_dir=log_dir,
    )
    persisted_paths = save_critic_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        critic_input_min=critic_input_min,
        refined_state_summary=refined_state_summary,
        module_behavior_summaries=module_behavior_summaries,
        process_signal_summary=process_signal_summary,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        critic_feedback_payload=critic_feedback_payload,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    validation_result("critic", validation_report,
                      batch_id=batch_id, round_id=round_id)
    phase_end("critic", batch_id=batch_id, round_id=round_id)

    return {
        "component_run": component_run,
        "critic_input_min": critic_input_min,
        "refined_state_summary": refined_state_summary,
        "module_behavior_summaries": module_behavior_summaries,
        "process_signal_summary": process_signal_summary,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "critic_feedback_payload": critic_feedback_payload,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "replay_metadata": replay_metadata,
        "artifact_paths": persisted_paths,
    }
