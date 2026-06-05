"""Execution wrapper for the Phase 3A Investigation Analysis component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from investigation_analysis.contracts import SCHEMA_VERSION
from investigation_analysis.parser import parse_investigation_analysis_response
from investigation_analysis.prompt_builder import build_investigation_analysis_prompt
from investigation_analysis.runtime_artifacts import (
    build_investigation_analysis_artifact_paths,
    save_investigation_analysis_artifacts,
)
from investigation_analysis.substrate_loader import (
    build_hypothesis_index,
    collect_valid_evidence_ids,
    project_analysis_context_min,
    project_analysis_iteration_context_min,
    project_semantic_substrate,
)
from investigation_analysis.validator import (
    validate_analysis_context_min,
    validate_analysis_iteration_context_min,
    validate_hypothesis_set,
)
from semantic_extraction.validator import validate_semantic_substrate
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception


InvestigationAnalysisCallable = Callable[[str], str]


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_investigation_analysis_callable(
    model_name: str,
    temperature: float = 0.0,
) -> InvestigationAnalysisCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run investigation analysis."
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


def run_investigation_analysis(
    semantic_substrate: dict[str, Any],
    analysis_context_min: dict[str, Any],
    *,
    analysis_iteration_context_min: dict[str, Any] | None = None,
    llm_callable: InvestigationAnalysisCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
) -> dict[str, Any]:
    raw_substrate = semantic_substrate if isinstance(
        semantic_substrate, dict) else {}
    raw_analysis_context = analysis_context_min if isinstance(
        analysis_context_min, dict) else {}
    raw_iteration_context = (
        analysis_iteration_context_min if isinstance(
            analysis_iteration_context_min, dict) else {}
    )

    source_substrate_id = str(raw_substrate.get(
        "substrate_id") or "unknown_substrate").strip() or "unknown_substrate"
    batch_id = str(raw_substrate.get("batch_id")
                   or "unknown_batch").strip() or "unknown_batch"

    substrate_validation = validate_semantic_substrate(raw_substrate)
    analysis_context_validation = validate_analysis_context_min(
        analysis_context_min)
    iteration_context_validation = validate_analysis_iteration_context_min(
        analysis_iteration_context_min)

    projected_substrate = project_semantic_substrate(raw_substrate)
    projected_analysis_context = project_analysis_context_min(
        raw_analysis_context)
    projected_iteration_context = project_analysis_iteration_context_min(
        analysis_iteration_context_min)
    valid_evidence_ids = collect_valid_evidence_ids(raw_substrate)

    prompt_text = ""
    raw_response_text = ""
    parsed_output: dict[str, Any] = {}
    hypothesis_index: dict[str, Any] = build_hypothesis_index(parsed_output)
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    output_validation: dict[str, Any] = _report_error(
        "parsed_output", "Parsed hypothesis set was not produced.")

    start_time = perf_counter()
    phase_start("semantic_hypothesis_generation",
                batch_id=batch_id, analysis_id=source_substrate_id)
    if substrate_validation["ok"] and analysis_context_validation["ok"] and iteration_context_validation["ok"]:
        prompt_text = build_investigation_analysis_prompt(
            batch_id=batch_id,
            projected_substrate=projected_substrate,
            projected_analysis_context=projected_analysis_context,
            projected_iteration_context=projected_iteration_context,
            critic_guidance=raw_iteration_context.get("critic_guidance") if isinstance(
                raw_iteration_context.get("critic_guidance"), list) else None,
        )
        try:
            callable_to_use = llm_callable or _build_openai_investigation_analysis_callable(
                model_name,
                temperature,
            )
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_output = parse_investigation_analysis_response(
                raw_response_text)
            hypothesis_index = build_hypothesis_index(parsed_output)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            output_validation = validate_hypothesis_set(
                parsed_output,
                valid_evidence_ids=valid_evidence_ids,
                expected_batch_id=batch_id,
            )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("semantic_hypothesis_generation", parse_validation,
                              batch_id=batch_id, analysis_id=source_substrate_id)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            parse_validation = _report_error("runtime", str(exc))
            exception("semantic_hypothesis_generation", exc,
                      hypothesis_id=parsed_output.get("analysis_id"), round_id=None)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": (
            substrate_validation["ok"]
            and analysis_context_validation["ok"]
            and iteration_context_validation["ok"]
            and parse_validation["ok"]
            and output_validation["ok"]
        ),
        "schema_version": SCHEMA_VERSION,
        "substrate_validation": substrate_validation,
        "analysis_context_validation": analysis_context_validation,
        "analysis_iteration_context_validation": iteration_context_validation,
        "parse_validation": parse_validation,
        "output_validation": output_validation,
    }
    status = "ok" if validation_report["ok"] else "error"
    validation_result("semantic_hypothesis_generation", validation_report,
                      batch_id=batch_id, analysis_id=source_substrate_id)
    phase_end("semantic_hypothesis_generation", elapsed_s=duration_ms /
              1000.0, batch_id=batch_id, analysis_id=source_substrate_id)

    output_stats = output_validation.get(
        "stats", {}) if isinstance(output_validation, dict) else {}
    runtime_metrics = {
        "batch_id": batch_id,
        "source_substrate_id": source_substrate_id,
        "analysis_id": parsed_output.get("analysis_id", ""),
        "model_name": model_name,
        "duration_ms": duration_ms,
        "status": status,
        "prompt_chars": len(prompt_text),
        "raw_response_chars": len(raw_response_text),
        "hypothesis_count": output_stats.get("hypothesis_count", hypothesis_index.get("hypothesis_count", 0)),
        "overlap_count": output_stats.get("overlap_pair_count", len(hypothesis_index.get("overlap_pairs", []))),
        "open_question_count": output_stats.get("open_question_count", 0),
        "distinct_evidence_ref_count": output_stats.get(
            "distinct_evidence_ref_count",
            len(hypothesis_index.get("evidence_ref_coverage", [])),
        ),
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "investigation_analysis",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "source_substrate_id": source_substrate_id,
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

    artifact_paths = build_investigation_analysis_artifact_paths(
        batch_id=batch_id, log_dir=log_dir)
    persisted_paths = save_investigation_analysis_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        semantic_substrate=raw_substrate,
        analysis_context_min=raw_analysis_context,
        analysis_iteration_context_min=raw_iteration_context,
        projected_substrate=projected_substrate,
        projected_analysis_context=projected_analysis_context,
        projected_iteration_context=projected_iteration_context,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        parsed_output=parsed_output,
        hypothesis_index=hypothesis_index,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    return {
        "component_run": component_run,
        "semantic_substrate_input": raw_substrate,
        "analysis_context_min": raw_analysis_context,
        "analysis_iteration_context_min": raw_iteration_context,
        "projected_substrate": projected_substrate,
        "projected_analysis_context": projected_analysis_context,
        "projected_iteration_context": projected_iteration_context,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "hypothesis_set": parsed_output,
        "parsed_output": parsed_output,
        "hypothesis_index": hypothesis_index,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }
