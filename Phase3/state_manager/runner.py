"""Execution wrapper for the Phase 3A State Manager component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from state.store import apply_interpretive_hypothesis_patch, get_interpretive_hypothesis
from state_manager.contracts import SCHEMA_VERSION, build_state_update_result
from state_manager.parser import parse_state_manager_response
from state_manager.prompt_builder import PROMPT_VERSION, build_state_manager_prompt
from state_manager.runtime_artifacts import (
    build_state_manager_artifact_paths,
    save_state_manager_artifacts,
)
from state_manager.state_loader import build_state_manager_context, load_canonical_batch_state
from state_manager.validator import (
    validate_aggregation_handoff_input,
    validate_canonical_batch_state,
    validate_state_delta_record,
)
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception


StateManagerCallable = Callable[[str], str]


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_state_manager_callable(
    model_name: str,
    temperature: float = 0.0,
) -> StateManagerCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run state manager."
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


def run_state_manager(
    canonical_batch_state: dict[str, Any],
    aggregation_handoff: dict[str, Any],
    *,
    llm_callable: StateManagerCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
    expected_prior_state_version: int | None = None,
    prior_state_origin: str | None = None,
    prior_state_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_state = load_canonical_batch_state(canonical_batch_state)
    prior_state = normalized_state.to_dict()
    raw_handoff = aggregation_handoff if isinstance(
        aggregation_handoff, dict) else {}
    request_id = f"state_manager_{uuid4().hex}"

    normalized_batch_id = str(prior_state.get("batch_id") or raw_handoff.get(
        "batch_id") or "unknown_batch").strip() or "unknown_batch"
    normalized_round_id = str(raw_handoff.get(
        "round_id") or "unknown_round").strip() or "unknown_round"
    normalized_hypothesis_id = str(raw_handoff.get(
        "hypothesis_id") or "unknown_hypothesis").strip() or "unknown_hypothesis"
    previous_state_version = int(prior_state.get("state_version") or 0)

    state_input_validation = validate_canonical_batch_state(
        prior_state,
        expected_batch_id=normalized_batch_id,
        expected_hypothesis_id=normalized_hypothesis_id,
        expected_state_version=expected_prior_state_version,
    )
    handoff_input_validation = validate_aggregation_handoff_input(
        raw_handoff,
        expected_batch_id=normalized_batch_id,
        expected_round_id=normalized_round_id,
        expected_hypothesis_id=normalized_hypothesis_id,
    )

    state_manager_context = build_state_manager_context(
        normalized_state, raw_handoff)
    prompt_text = ""
    raw_response_text = ""
    state_delta_record: dict[str, Any] = {}
    updated_batch_state: dict[str, Any] = {}
    state_update_result: dict[str, Any] = {}
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    delta_validation: dict[str, Any] = _report_error(
        "state_delta_record",
        "state_delta_record was not produced.",
    )

    start_time = perf_counter()
    phase_start("state_manager", batch_id=normalized_batch_id,
                round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)
    if state_input_validation["ok"] and handoff_input_validation["ok"]:
        prompt_text = build_state_manager_prompt(
            batch_id=normalized_batch_id,
            round_id=normalized_round_id,
            hypothesis_id=normalized_hypothesis_id,
            state_manager_context=state_manager_context,
        )
        try:
            callable_to_use = llm_callable or _build_openai_state_manager_callable(
                model_name, temperature)
            raw_response_text = str(callable_to_use(prompt_text) or "")
            state_delta_record = parse_state_manager_response(
                raw_response_text)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            delta_validation = validate_state_delta_record(
                state_delta_record,
                current_hypothesis=state_manager_context.get(
                    "target_hypothesis", {}),
                aggregation_handoff=raw_handoff,
                known_evidence_refs=set(
                    state_manager_context.get("known_evidence_refs", [])),
            )
            if delta_validation["ok"]:
                updated_state_obj = apply_interpretive_hypothesis_patch(
                    normalized_state,
                    round_id=normalized_round_id,
                    hypothesis_id=normalized_hypothesis_id,
                    summary=state_delta_record.get("summary"),
                    status=state_delta_record.get("status"),
                    evidence_refs=list(
                        state_delta_record.get("evidence_refs", [])),
                    preserved_contradictions=list(
                        state_delta_record.get("preserved_contradictions", [])
                    ),
                    open_gaps=list(state_delta_record.get("open_gaps", [])),
                    merged_findings=list(
                        state_delta_record.get("merged_findings", [])),
                    update_focus=state_delta_record.get("update_focus"),
                    applied_updates=list(
                        state_delta_record.get("applied_updates", [])),
                )
                updated_batch_state = updated_state_obj.to_dict()
                updated_hypothesis = get_interpretive_hypothesis(
                    updated_state_obj,
                    normalized_hypothesis_id,
                )
                state_update_result = build_state_update_result(
                    batch_id=normalized_batch_id,
                    round_id=normalized_round_id,
                    previous_state_version=previous_state_version,
                    new_state_version=updated_state_obj.state_version,
                    applied_updates=updated_state_obj.revision_log[-1].applied_updates,
                    remaining_open_gaps=(
                        updated_hypothesis.open_gaps if updated_hypothesis else []),
                )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("state_manager", parse_validation, batch_id=normalized_batch_id,
                              round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)
        except Exception as exc:  # pragma: no cover
            parse_validation = _report_error("runtime", str(exc))
            exception("state_manager", exc, round_id=normalized_round_id,
                      hypothesis_id=normalized_hypothesis_id)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": state_input_validation["ok"]
        and handoff_input_validation["ok"]
        and parse_validation["ok"]
        and delta_validation["ok"],
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "state_input_validation": state_input_validation,
        "handoff_input_validation": handoff_input_validation,
        "parse_validation": parse_validation,
        "state_delta_validation": delta_validation,
    }
    status = "ok" if validation_report["ok"] else "error"
    state_committed = bool(updated_batch_state)
    new_state_version = updated_batch_state.get(
        "state_version") if state_committed else None

    runtime_metrics = {
        "request_id": request_id,
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "hypothesis_id": normalized_hypothesis_id,
        "prompt_version": PROMPT_VERSION,
        "model_name": model_name,
        "temperature": temperature,
        "duration_ms": duration_ms,
        "status": status,
        "previous_state_version": previous_state_version,
        "new_state_version": new_state_version,
        "applied_update_count": len(state_update_result.get("applied_updates", [])),
        "remaining_open_gap_count": len(state_update_result.get("remaining_open_gaps", [])),
        "state_committed": state_committed,
        "prior_state_origin": prior_state_origin,
        "prompt_chars": len(prompt_text),
        "raw_response_chars": len(raw_response_text),
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "state_manager",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "hypothesis_id": normalized_hypothesis_id,
        "previous_state_version": previous_state_version,
        "new_state_version": new_state_version,
        "status": status,
        "validation_ok": validation_report["ok"],
        "state_committed": state_committed,
        "model_name": model_name,
        "temperature": temperature,
        "prior_state_origin": prior_state_origin,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }
    replay_metadata = {
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
        "expected_prior_state_version": expected_prior_state_version,
        "prior_state_source": dict(prior_state_source or {}),
    }

    artifact_paths = build_state_manager_artifact_paths(
        hypothesis_id=normalized_hypothesis_id,
        log_dir=log_dir,
    )
    persisted_paths = save_state_manager_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        prior_state=prior_state,
        aggregation_handoff=raw_handoff,
        state_manager_context=state_manager_context,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        state_delta_record=state_delta_record,
        updated_batch_state=updated_batch_state,
        state_update_result=state_update_result,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    validation_result("state_manager", validation_report, batch_id=normalized_batch_id,
                      round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)
    phase_end("state_manager", elapsed_s=duration_ms / 1000.0, batch_id=normalized_batch_id,
              round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)

    return {
        "component_run": component_run,
        "prior_state": prior_state,
        "aggregation_handoff": raw_handoff,
        "state_manager_context": state_manager_context,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "state_delta_record": state_delta_record,
        "updated_batch_state": updated_batch_state,
        "state_update_result": state_update_result,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "replay_metadata": replay_metadata,
        "artifact_paths": persisted_paths,
    }
