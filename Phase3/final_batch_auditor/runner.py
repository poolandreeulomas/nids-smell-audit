"""Execution wrapper for the Phase 3A Final Batch Auditor component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from final_batch_auditor.contracts import SCHEMA_VERSION, build_debugging_audit_report
from final_batch_auditor.input_resolver import build_final_batch_audit_context
from final_batch_auditor.parser import parse_final_batch_auditor_response
from final_batch_auditor.prompt_builder import (
    PROMPT_VERSION,
    build_final_batch_auditor_prompt,
)
from final_batch_auditor.runtime_artifacts import (
    build_final_batch_auditor_artifact_paths,
    save_final_batch_auditor_artifacts,
)
from final_batch_auditor.validator import (
    validate_debugging_audit_report,
    validate_final_batch_audit_input,
)
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception


FinalBatchAuditorCallable = Callable[[str], str]


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
                "message": "Final Batch Auditor requires a validation-ok State Manager source bundle.",
            }
        )
    if not bool(component_run.get("state_committed", False)):
        errors.append(
            {
                "field": "component_run.state_committed",
                "message": "Final Batch Auditor requires a committed State Manager source bundle.",
            }
        )
    if not updated_batch_state:
        errors.append(
            {
                "field": "updated_batch_state",
                "message": "Final Batch Auditor requires the committed updated_batch_state artifact.",
            }
        )

    return {"ok": not errors, "errors": errors, "warnings": []}


def _build_terminal_gate(is_final_batch: bool) -> dict[str, Any]:
    return {
        "ok": bool(is_final_batch),
        "status": "confirmed_terminal_batch" if is_final_batch else "rejected_non_terminal_batch",
        "message": (
            "Final Batch Auditor execution was allowed because the selected committed state was marked as the terminal batch state."
            if is_final_batch
            else "Final Batch Auditor execution was rejected because the selected committed state was not marked terminal."
        ),
    }


def _build_openai_final_batch_auditor_callable(
    model_name: str,
    temperature: float = 0.0,
) -> FinalBatchAuditorCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run final_batch_auditor."
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


def run_final_batch_auditor(
    state_manager_bundle: dict[str, Any],
    *,
    llm_callable: FinalBatchAuditorCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
    is_final_batch: bool = False,
    batch_component_bundles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_id = f"final_batch_auditor_{uuid4().hex}"
    audit_context = build_final_batch_audit_context(
        state_manager_bundle if isinstance(state_manager_bundle, dict) else {},
        batch_component_bundles=batch_component_bundles,
    )
    known_traceability_refs = set(
        audit_context.pop("known_traceability_refs", []))
    source_state_manager_run_path = str(
        audit_context.pop("source_state_manager_run_path", "") or ""
    )
    final_audit_input = dict(audit_context.get("final_audit_input", {}))
    final_state_summary = dict(audit_context.get("final_state_summary", {}))
    round_history_summary = list(
        audit_context.get("round_history_summary", []))
    process_signal_summary = dict(
        audit_context.get("process_signal_summary", {}))

    batch_id = str(final_audit_input.get("batch_id")
                   or "unknown_batch").strip() or "unknown_batch"
    state_version = int(final_state_summary.get("state_version") or 0)

    input_context_payload = {
        "final_audit_input": final_audit_input,
        "final_state_summary": final_state_summary,
        "round_history_summary": round_history_summary,
        "process_signal_summary": process_signal_summary,
    }
    input_validation = validate_final_batch_audit_input(
        input_context_payload,
        expected_batch_id=batch_id,
    )
    source_state_validation = _validate_state_manager_source_bundle(
        state_manager_bundle if isinstance(state_manager_bundle, dict) else {},
    )
    terminal_gate = _build_terminal_gate(is_final_batch)

    prompt_text = ""
    raw_response_text = ""
    debugging_audit_report: dict[str, Any] = {}
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    report_validation: dict[str, Any] = _report_error(
        "debugging_audit_report",
        "debugging_audit_report was not produced.",
    )

    start_time = perf_counter()
    phase_start("final_batch_auditor", batch_id=batch_id,
                state_version=state_version)
    if input_validation["ok"] and source_state_validation["ok"] and terminal_gate["ok"]:
        prompt_text = build_final_batch_auditor_prompt(
            batch_id=batch_id,
            final_audit_input=final_audit_input,
            final_state_summary=final_state_summary,
            round_history_summary=round_history_summary,
            process_signal_summary=process_signal_summary,
        )
        try:
            callable_to_use = llm_callable or _build_openai_final_batch_auditor_callable(
                model_name,
                temperature,
            )
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_payload = parse_final_batch_auditor_response(
                raw_response_text)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            report_validation = validate_debugging_audit_report(
                parsed_payload,
                expected_batch_id=batch_id,
                known_traceability_refs=known_traceability_refs,
            )
            if report_validation["ok"]:
                debugging_audit_report = build_debugging_audit_report(
                    batch_id=batch_id,
                    trajectory_summary=str(parsed_payload.get(
                        "trajectory_summary", "") or ""),
                    hypothesis_summary=str(parsed_payload.get(
                        "hypothesis_summary", "") or ""),
                    surviving_contradictions=list(
                        parsed_payload.get("surviving_contradictions", [])),
                    open_pressures=list(
                        parsed_payload.get("open_pressures", [])),
                    failure_summary=str(parsed_payload.get(
                        "failure_summary", "") or ""),
                    traceability_refs=list(
                        parsed_payload.get("traceability_refs", [])),
                )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("final_batch_auditor", parse_validation,
                              batch_id=batch_id, state_version=state_version)
        except Exception as exc:  # pragma: no cover
            parse_validation = _report_error("runtime", str(exc))
            exception("final_batch_auditor", exc, round_id=state_version)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": input_validation["ok"]
        and source_state_validation["ok"]
        and terminal_gate["ok"]
        and parse_validation["ok"]
        and report_validation["ok"],
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "terminal_gate": terminal_gate,
        "input_validation": input_validation,
        "source_state_validation": source_state_validation,
        "parse_validation": parse_validation,
        "debugging_audit_report_validation": report_validation,
    }
    status = "ok" if validation_report["ok"] else "error"
    report_committed = bool(debugging_audit_report)
    audit_mode = "replay" if replay_of else "authoritative"
    validation_result("final_batch_auditor", validation_report,
                      batch_id=batch_id, state_version=state_version)
    phase_end("final_batch_auditor", elapsed_s=duration_ms / 1000.0,
              batch_id=batch_id, state_version=state_version)

    runtime_metrics = {
        "request_id": request_id,
        "batch_id": batch_id,
        "state_version": state_version,
        "prompt_version": PROMPT_VERSION,
        "model_name": model_name,
        "temperature": temperature,
        "duration_ms": duration_ms,
        "status": status,
        "terminal_gate_status": terminal_gate["status"],
        "report_committed": report_committed,
        "traceability_ref_count": len(debugging_audit_report.get("traceability_refs", [])),
        "round_ref_count": len(final_audit_input.get("round_artifact_refs", [])),
        "history_ref_count": len(final_audit_input.get("hypothesis_history_refs", [])),
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "audit_mode": audit_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "final_batch_auditor",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "state_version": state_version,
        "status": status,
        "validation_ok": validation_report["ok"],
        "terminal_gate_status": terminal_gate["status"],
        "report_committed": report_committed,
        "traceability_ref_count": len(debugging_audit_report.get("traceability_refs", [])),
        "model_name": model_name,
        "temperature": temperature,
        "source_state_manager_run_path": source_state_manager_run_path,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
        "audit_mode": audit_mode,
    }
    replay_metadata = {
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
        "is_final_batch": bool(is_final_batch),
        "source_state_manager_run_path": source_state_manager_run_path,
        "audit_mode": audit_mode,
    }

    artifact_paths = build_final_batch_auditor_artifact_paths(
        batch_id=batch_id,
        log_dir=log_dir,
    )
    persisted_paths = save_final_batch_auditor_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        final_audit_input=final_audit_input,
        final_state_summary=final_state_summary,
        round_history_summary=round_history_summary,
        process_signal_summary=process_signal_summary,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        debugging_audit_report=debugging_audit_report,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    return {
        "component_run": component_run,
        "final_audit_input": final_audit_input,
        "final_state_summary": final_state_summary,
        "round_history_summary": round_history_summary,
        "process_signal_summary": process_signal_summary,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "debugging_audit_report": debugging_audit_report,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "replay_metadata": replay_metadata,
        "artifact_paths": persisted_paths,
    }
