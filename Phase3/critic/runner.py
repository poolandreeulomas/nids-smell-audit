"""Execution wrapper for the Phase 3A Critic component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from critic.contracts import SCHEMA_VERSION, build_critic_observations_payload
from critic.input_resolver import build_critic_context
from critic.parser import parse_critic_response
from critic.prompt_builder import PROMPT_VERSION, build_critic_prompt
from critic.runtime_artifacts import build_critic_artifact_paths, save_critic_artifacts
from critic.validator import (
    validate_critic_input_bundle,
    validate_critic_observations_payload,
)
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


def _known_hypothesis_ids(state_manager_bundle: dict[str, Any]) -> set[str]:
    raw = state_manager_bundle if isinstance(
        state_manager_bundle, dict) else {}
    updated_batch_state = dict(raw.get("updated_batch_state", {}) or {})
    hypotheses = updated_batch_state.get("interpretive_hypotheses", [])
    known_ids: set[str] = set()
    if isinstance(hypotheses, list):
        for item in hypotheses:
            if isinstance(item, dict):
                hypothesis_id = str(
                    item.get("hypothesis_id", "") or "").strip()
                if hypothesis_id:
                    known_ids.add(hypothesis_id)
    return known_ids


def _normalize_observations_payload(parsed_payload: dict[str, Any]) -> dict[str, Any]:
    observations = parsed_payload.get("critic_observations", [])
    if isinstance(observations, list):
        normalized_observations = [
            dict(item) for item in observations if isinstance(item, dict)]
    else:
        normalized_observations = []
    return {
        "batch_id": str(parsed_payload.get("batch_id", "unknown_batch") or "unknown_batch").strip() or "unknown_batch",
        "round_id": str(parsed_payload.get("round_id", "unknown_round") or "unknown_round").strip() or "unknown_round",
        "critic_observations": normalized_observations,
    }


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
    critic_input_min = dict(critic_context.get("critic_input_min", {}))
    semantic_landscape_summary = dict(
        critic_context.get("semantic_landscape_summary", {}))
    hypothesis_universe = list(
        critic_context.get("hypothesis_universe", []))
    investigation_history = list(
        critic_context.get("investigation_history", []))
    ranking_history = list(
        critic_context.get("ranking_history", []))
    investigation_outcomes = list(
        critic_context.get("investigation_outcomes", []))
    active_hypothesis_gaps = list(
        critic_context.get("active_hypothesis_gaps", []))

    batch_id = str(critic_input_min.get("batch_id")
                   or "unknown_batch").strip() or "unknown_batch"
    round_id = str(critic_input_min.get("round_id")
                   or "unknown_round").strip() or "unknown_round"

    critic_context_payload = {
        "critic_input_min": critic_input_min,
        "semantic_landscape_summary": semantic_landscape_summary,
        "hypothesis_universe": hypothesis_universe,
        "investigation_history": investigation_history,
        "ranking_history": ranking_history,
        "investigation_outcomes": investigation_outcomes,
        "active_hypothesis_gaps": active_hypothesis_gaps,
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
    critic_observations_payload: dict[str, Any] = {}
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    observations_validation: dict[str, Any] = _report_error(
        "critic_observations_payload",
        "critic_observations_payload was not produced.",
    )
    known_hypothesis_ids = _known_hypothesis_ids(state_manager_bundle)

    start_time = perf_counter()
    phase_start("critic", batch_id=batch_id, round_id=round_id)
    if input_validation["ok"] and source_state_validation["ok"] and not is_final_round:
        prompt_text = build_critic_prompt(
            batch_id=batch_id,
            round_id=round_id,
            critic_input_min=critic_input_min,
            semantic_landscape_summary=semantic_landscape_summary,
            hypothesis_universe=hypothesis_universe,
            investigation_history=investigation_history,
            ranking_history=ranking_history,
            investigation_outcomes=investigation_outcomes,
            active_hypothesis_gaps=active_hypothesis_gaps,
        )
        try:
            callable_to_use = llm_callable or _build_openai_critic_callable(
                model_name, temperature)
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_payload = parse_critic_response(raw_response_text)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            critic_observations_payload = _normalize_observations_payload(
                parsed_payload)
            observations_validation = validate_critic_observations_payload(
                critic_observations_payload,
                expected_batch_id=batch_id,
                expected_round_id=round_id,
                known_hypothesis_ids=known_hypothesis_ids,
                allowed_target_modules=set(),
            )
            if observations_validation["ok"]:
                critic_observations_payload = build_critic_observations_payload(
                    batch_id=batch_id,
                    round_id=round_id,
                    critic_observations=list(
                        critic_observations_payload.get("critic_observations", [])),
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
        observations_validation = {
            "ok": True,
            "errors": [],
            "warnings": [],
            "stats": {
                "observation_count": 0,
                "observations_committed": True,
                "average_prompt_snippet_length": 0.0,
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
        and observations_validation["ok"],
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "final_round_gate": final_round_gate,
        "input_validation": input_validation,
        "source_state_validation": source_state_validation,
        "parse_validation": parse_validation,
        "critic_observations_validation": observations_validation,
        "critic_feedback_validation": observations_validation,
    }
    status = "skipped" if is_final_round and input_validation["ok"] else (
        "ok" if validation_report["ok"] else "error")
    observations_committed = bool(critic_observations_payload)
    observation_count = len(
        critic_observations_payload.get("critic_observations", []))

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
        "observation_count": observation_count,
        "observations_committed": observations_committed,
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
        "observation_count": observation_count,
        "observations_committed": observations_committed,
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
        semantic_landscape_summary=semantic_landscape_summary,
        hypothesis_universe=hypothesis_universe,
        investigation_history=investigation_history,
        ranking_history=ranking_history,
        investigation_outcomes=investigation_outcomes,
        active_hypothesis_gaps=active_hypothesis_gaps,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        critic_observations_payload=critic_observations_payload,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    validation_result("critic", validation_report,
                      batch_id=batch_id, round_id=round_id)
    phase_end("critic", batch_id=batch_id, round_id=round_id)

    refined_state_summary = semantic_landscape_summary
    module_behavior_summaries = hypothesis_universe
    process_signal_summary = {
        "batch_id": batch_id,
        "round_id": round_id,
        "investigation_history": investigation_history,
        "ranking_history": ranking_history,
        "investigation_outcomes": investigation_outcomes,
        "active_hypothesis_gaps": active_hypothesis_gaps,
    }

    return {
        "component_run": component_run,
        "critic_input_min": critic_input_min,
        "semantic_landscape_summary": semantic_landscape_summary,
        "hypothesis_universe": hypothesis_universe,
        "investigation_history": investigation_history,
        "ranking_history": ranking_history,
        "investigation_outcomes": investigation_outcomes,
        "active_hypothesis_gaps": active_hypothesis_gaps,
        "refined_state_summary": refined_state_summary,
        "module_behavior_summaries": module_behavior_summaries,
        "process_signal_summary": process_signal_summary,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "critic_observations_payload": critic_observations_payload,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "replay_metadata": replay_metadata,
        "artifact_paths": persisted_paths,
    }