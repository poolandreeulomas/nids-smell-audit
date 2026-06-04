"""Execution wrapper for the Phase 3A Semantic Extraction component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from semantic_extraction.contracts import SCHEMA_VERSION
from semantic_extraction.evidence_projector import (
    collect_valid_evidence_ids,
    normalize_partition_context,
    project_overview_evidence,
)
from semantic_extraction.parser import parse_semantic_extraction_response
from semantic_extraction.prompt_builder import build_semantic_extraction_prompt
from semantic_extraction.runtime_artifacts import (
    build_semantic_extraction_artifact_paths,
    save_semantic_extraction_artifacts,
)
from semantic_extraction.validator import (
    validate_overview_summary_min,
    validate_partition_context,
    validate_semantic_substrate,
)
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception


SemanticExtractionCallable = Callable[[str], str]


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_semantic_extraction_callable(
    model_name: str,
    temperature: float = 0.0,
) -> SemanticExtractionCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run semantic extraction."
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


def run_semantic_extraction(
    overview_summary_min: dict[str, Any],
    partition_context: dict[str, Any],
    *,
    llm_callable: SemanticExtractionCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
) -> dict[str, Any]:
    normalized_overview = dict(overview_summary_min or {})
    normalized_partition_context = normalize_partition_context(
        partition_context)
    projected_evidence = project_overview_evidence(normalized_overview)
    valid_evidence_ids = collect_valid_evidence_ids(projected_evidence)
    batch_id = str(normalized_overview.get("batch_id")
                   or "unknown_batch").strip() or "unknown_batch"

    overview_validation = validate_overview_summary_min(normalized_overview)
    partition_validation = validate_partition_context(
        normalized_partition_context)

    prompt_text = ""
    raw_response_text = ""
    parsed_output: dict[str, Any] = {}
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    output_validation: dict[str, Any] = _report_error(
        "parsed_output", "Parsed semantic substrate was not produced.")

    start_time = perf_counter()
    phase_start("semantic_extraction", batch_id=batch_id)
    if overview_validation["ok"] and partition_validation["ok"]:
        prompt_text = build_semantic_extraction_prompt(
            batch_id=batch_id,
            projected_evidence=projected_evidence,
            normalized_partition_context=normalized_partition_context,
        )
        try:
            callable_to_use = llm_callable or _build_openai_semantic_extraction_callable(
                model_name,
                temperature,
            )
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_output = parse_semantic_extraction_response(
                raw_response_text)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            output_validation = validate_semantic_substrate(
                parsed_output,
                valid_evidence_ids=valid_evidence_ids,
            )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("semantic_extraction",
                              parse_validation, batch_id=batch_id)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            parse_validation = _report_error("runtime", str(exc))
            exception("semantic_extraction", exc, batch_id=batch_id)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": overview_validation["ok"] and partition_validation["ok"] and parse_validation["ok"] and output_validation["ok"],
        "schema_version": SCHEMA_VERSION,
        "overview_validation": overview_validation,
        "partition_context_validation": partition_validation,
        "parse_validation": parse_validation,
        "output_validation": output_validation,
    }
    status = "ok" if validation_report["ok"] else "error"
    validation_result("semantic_extraction",
                      validation_report, batch_id=batch_id)
    phase_end("semantic_extraction", elapsed_s=duration_ms /
              1000.0, batch_id=batch_id)

    artifact_paths = build_semantic_extraction_artifact_paths(
        batch_id=batch_id, log_dir=log_dir)
    runtime_metrics = {
        "batch_id": batch_id,
        "model_name": model_name,
        "duration_ms": duration_ms,
        "status": status,
        "prompt_chars": len(prompt_text),
        "raw_response_chars": len(raw_response_text),
        "evidence_count": projected_evidence.get("evidence_count", 0),
        "region_count": len(parsed_output.get("compressed_regions", [])),
        "weak_signal_count": len(parsed_output.get("preserved_weak_signals", [])),
        "contradiction_count": len(parsed_output.get("contradictions", [])),
        "tension_count": len(parsed_output.get("unresolved_tensions", [])),
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "semantic_extraction",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "status": status,
        "validation_ok": validation_report["ok"],
        "model_name": model_name,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }
    replay_metadata = {
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
    }

    persisted_paths = save_semantic_extraction_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        overview_summary_min=normalized_overview,
        partition_context=normalized_partition_context,
        projected_evidence=projected_evidence,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        parsed_output=parsed_output,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    return {
        "component_run": component_run,
        "overview_summary_min": normalized_overview,
        "partition_context": normalized_partition_context,
        "projected_evidence": projected_evidence,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "semantic_substrate": parsed_output,
        "parsed_output": parsed_output,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }
