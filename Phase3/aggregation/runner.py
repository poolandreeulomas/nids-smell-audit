"""Execution wrapper for the Phase 3A Aggregation component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from aggregation.contracts import SCHEMA_VERSION
from aggregation.input_resolver import build_normalized_inputs
from aggregation.parser import parse_aggregation_response
from aggregation.prompt_builder import build_aggregation_prompt
from aggregation.runtime_artifacts import build_aggregation_artifact_paths, save_aggregation_artifacts
from aggregation.validator import repair_aggregation_handoff, validate_aggregation_handoff, validate_worker_result_set
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, barrier_status, exception


AggregationCallable = Callable[[str], str]


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_aggregation_callable(
    model_name: str,
    temperature: float = 0.0,
) -> AggregationCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run aggregation."
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


def run_aggregation(
    worker_result_set: dict[str, Any],
    *,
    expected_task_ids: list[str] | None = None,
    llm_callable: AggregationCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
    source_run_dirs: list[str] | None = None,
) -> dict[str, Any]:
    raw_worker_result_set = worker_result_set if isinstance(
        worker_result_set, dict) else {}
    normalized_batch_id = str(raw_worker_result_set.get(
        "batch_id") or "unknown_batch").strip() or "unknown_batch"
    normalized_round_id = str(raw_worker_result_set.get(
        "round_id") or "unknown_round").strip() or "unknown_round"
    normalized_hypothesis_id = str(raw_worker_result_set.get(
        "hypothesis_id") or "unknown_hypothesis").strip() or "unknown_hypothesis"
    expected_task_id_set = set(expected_task_ids or [])

    worker_result_set_validation = validate_worker_result_set(
        raw_worker_result_set,
        expected_task_ids=expected_task_id_set,
    )
    normalized_inputs = build_normalized_inputs(
        raw_worker_result_set,
        expected_task_ids=sorted(expected_task_id_set),
        source_run_dirs=source_run_dirs,
    )
    overlap_diagnostics = list(
        normalized_inputs.get("overlap_diagnostics", []))
    known_evidence_refs = set(
        normalized_inputs.get("source_evidence_refs", []))
    source_contradictions = normalized_inputs.get("source_contradictions", [])
    source_contradiction_ids = {
        c["id"] for c in source_contradictions if isinstance(c, dict) and "id" in c
    }
    source_contradiction_lookup = normalized_inputs.get("source_contradiction_lookup", {})
    source_gap_signal_count = len(normalized_inputs.get("source_limitations", [])) + int(
        normalized_inputs.get("non_success_count", 0)
    )
    source_finding_count = int(
        normalized_inputs.get("source_finding_count", 0) or 0)

    prompt_text = ""
    raw_response_text = ""
    parsed_output: dict[str, Any] = {}
    aggregation_handoff: dict[str, Any] = {}
    repair_attempts: list[dict[str, Any]] = []
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    handoff_validation: dict[str, Any] = _report_error(
        "aggregation_handoff",
        "aggregation_handoff was not produced.",
    )
    initial_handoff_validation: dict[str, Any] = handoff_validation

    start_time = perf_counter()
    phase_start("aggregation", batch_id=normalized_batch_id,
                round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)
    if worker_result_set_validation["ok"]:
        prompt_text = build_aggregation_prompt(
            batch_id=normalized_batch_id,
            round_id=normalized_round_id,
            hypothesis_id=normalized_hypothesis_id,
            normalized_inputs=normalized_inputs,
        )
        try:
            callable_to_use = llm_callable or _build_openai_aggregation_callable(
                model_name, temperature)
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_output = parse_aggregation_response(raw_response_text)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            initial_handoff_validation = validate_aggregation_handoff(
                parsed_output,
                expected_batch_id=normalized_batch_id,
                expected_round_id=normalized_round_id,
                expected_hypothesis_id=normalized_hypothesis_id,
                known_evidence_refs=known_evidence_refs,
                source_contradictions=source_contradictions,
                source_contradiction_ids=source_contradiction_ids,
                source_gap_signal_count=source_gap_signal_count,
                source_finding_count=source_finding_count,
            )
            handoff_validation = dict(initial_handoff_validation)
            if handoff_validation["ok"]:
                # Reconstruct preserved_contradictions text from IDs
                handoff_text = {
                    "batch_id": parsed_output.get("batch_id"),
                    "round_id": parsed_output.get("round_id"),
                    "hypothesis_id": parsed_output.get("hypothesis_id"),
                    "merged_findings": parsed_output.get("merged_findings", []),
                    "evidence_refs": parsed_output.get("evidence_refs", []),
                    "preserved_contradictions": [
                        source_contradiction_lookup[cid]
                        for cid in parsed_output.get("preserved_contradiction_ids", [])
                        if cid in source_contradiction_lookup
                    ],
                    "open_gaps": parsed_output.get("open_gaps", []),
                    "update_focus": parsed_output.get("update_focus", ""),
                }
                aggregation_handoff = dict(parsed_output)
                aggregation_handoff["preserved_contradictions"] = handoff_text["preserved_contradictions"]
            elif handoff_validation.get("repairable"):
                repair_result = repair_aggregation_handoff(parsed_output)
                repaired_output = dict(
                    repair_result.get("repaired_output", {}))
                repaired_validation = validate_aggregation_handoff(
                    repaired_output,
                    expected_batch_id=normalized_batch_id,
                    expected_round_id=normalized_round_id,
                    expected_hypothesis_id=normalized_hypothesis_id,
                    known_evidence_refs=known_evidence_refs,
                    source_contradictions=source_contradictions,
                    source_contradiction_ids=source_contradiction_ids,
                    source_gap_signal_count=source_gap_signal_count,
                    source_finding_count=source_finding_count,
                )
                repair_attempts.append(
                    {
                        "kind": "aggregation_handoff_repair",
                        "original_validation_report": initial_handoff_validation,
                        "repair_action": {
                            "name": "normalize_and_truncate_update_focus",
                            "field": "update_focus",
                            "max_chars": 160,
                        },
                        "repair_details": repair_result.get("repair_actions", []),
                        "repaired_output": repaired_output,
                        "post_repair_validation_result": repaired_validation,
                        "final_authoritative_status": bool(repaired_validation.get("ok", False)),
                    }
                )
                handoff_validation = {
                    **repaired_validation,
                    "original_validation_report": initial_handoff_validation,
                    "repair_actions": repair_result.get("repair_actions", []),
                    "repaired_output": repaired_output,
                }
                if repaired_validation["ok"]:
                    aggregation_handoff = repaired_output
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("aggregation", parse_validation, batch_id=normalized_batch_id,
                              round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)
        except Exception as exc:  # pragma: no cover
            parse_validation = _report_error("runtime", str(exc))
            exception("aggregation", exc, round_id=normalized_round_id,
                      hypothesis_id=normalized_hypothesis_id)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": worker_result_set_validation["ok"] and parse_validation["ok"] and handoff_validation["ok"],
        "schema_version": SCHEMA_VERSION,
        "worker_result_set_validation": worker_result_set_validation,
        "parse_validation": parse_validation,
        "aggregation_handoff_validation": handoff_validation,
        "initial_aggregation_handoff_validation": initial_handoff_validation,
        "repair_attempts": repair_attempts,
        "authoritative": worker_result_set_validation["ok"] and parse_validation["ok"] and handoff_validation["ok"],
    }
    status = "ok" if validation_report["ok"] else "error"
    handoff_committed = bool(aggregation_handoff)

    runtime_metrics = {
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "hypothesis_id": normalized_hypothesis_id,
        "model_name": model_name,
        "duration_ms": duration_ms,
        "status": status,
        "worker_result_count": normalized_inputs.get("worker_result_count", 0),
        "overlap_group_count": len(overlap_diagnostics),
        "source_contradiction_count": len(source_contradictions),
        "handoff_committed": handoff_committed,
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "aggregation",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "hypothesis_id": normalized_hypothesis_id,
        "status": status,
        "validation_ok": validation_report["ok"],
        "handoff_committed": handoff_committed,
        "model_name": model_name,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }
    replay_metadata = {
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
    }

    artifact_paths = build_aggregation_artifact_paths(
        hypothesis_id=normalized_hypothesis_id,
        log_dir=log_dir,
    )
    persisted_paths = save_aggregation_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        worker_result_set=raw_worker_result_set,
        normalized_inputs=normalized_inputs,
        overlap_diagnostics=overlap_diagnostics,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        parsed_output=parsed_output,
        aggregation_handoff=aggregation_handoff,
        repair_attempts=repair_attempts,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    # Barrier / synchronization visibility: expected vs found
    barrier_status("hypothesis", expected=len(expected_task_id_set) if expected_task_id_set else None, completed=normalized_inputs.get(
        "worker_result_count", 0), waiting_for=[], batch_id=normalized_batch_id, round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)
    validation_result("aggregation", validation_report, batch_id=normalized_batch_id,
                      round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)
    phase_end("aggregation", elapsed_s=duration_ms / 1000.0, batch_id=normalized_batch_id,
              round_id=normalized_round_id, hypothesis_id=normalized_hypothesis_id)

    return {
        "component_run": component_run,
        "worker_result_set": raw_worker_result_set,
        "normalized_inputs": normalized_inputs,
        "overlap_diagnostics": overlap_diagnostics,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "parsed_output": parsed_output,
        "aggregation_handoff": aggregation_handoff,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }
