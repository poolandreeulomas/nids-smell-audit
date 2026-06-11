"""Execution wrapper for the Phase 3 Final Partition Audit Report Generator."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from state.schema import CanonicalBatchState

from final_batch_report.contracts import SCHEMA_VERSION
from final_batch_report.input_resolver import resolve_report_context
from final_batch_report.parser import parse_report
from final_batch_report.prompt_builder import (
    PROMPT_VERSION,
    build_final_batch_report_prompt,
)
from final_batch_report.runtime_artifacts import (
    build_final_batch_report_artifact_paths,
    save_final_batch_report_artifacts,
)
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end


FinalBatchReportCallable = Callable[[str], str]


def _build_openai_final_batch_report_callable(
    model_name: str,
    temperature: float = 0.0,
) -> FinalBatchReportCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run final_batch_report."
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


def run_final_batch_report(
    final_state: CanonicalBatchState,
    partition_name: str,
    *,
    llm_callable: FinalBatchReportCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
) -> dict[str, Any]:
    """Generate a Final Partition Audit Report from the Final Updated State.

    Flow:
        Load Final Updated State
            â
        Resolve Report Context
            â
        Build Prompt
            â
        Call LLM
            â
        Capture Markdown
            â
        Persist Artifacts
            â
        Return Results

    Args:
        final_state: CanonicalBatchState (the Final Updated State).
        partition_name: Human-readable partition name.
        llm_callable: Optional custom LLM callable.
        model_name: OpenAI model name (default: gpt-4.1-mini).
        temperature: LLM temperature (default: 0.0).
        log_dir: Optional log directory override.

    Returns:
        Dict with report_markdown, runtime_metrics, artifact_paths.
    """
    request_id = f"final_batch_report_{uuid4().hex}"
    batch_id = final_state.batch_id or "unknown_batch"
    state_version = final_state.state_version

    # Step 1: Resolve Report Context
    report_context = resolve_report_context(final_state, partition_name)

    partition_audit_context = report_context["partition_audit_context"]
    intended_behavioral_scenario = report_context["intended_behavioral_scenario"]
    researcher_audit_context = report_context["researcher_audit_context"]
    investigated_findings = report_context["investigated_findings"]
    additional_findings = report_context["additional_findings"]

    # Step 2: Build Prompt
    prompt_text = build_final_batch_report_prompt(
        partition_name=partition_name,
        partition_audit_context=partition_audit_context,
        intended_behavioral_scenario=intended_behavioral_scenario,
        researcher_audit_context=researcher_audit_context,
        investigated_findings=investigated_findings,
        additional_findings=additional_findings,
    )

    report_markdown = ""
    raw_response_text = ""

    start_time = perf_counter()
    phase_start(
        "final_batch_report",
        batch_id=batch_id,
        state_version=state_version,
    )

    try:
        callable_to_use = llm_callable or _build_openai_final_batch_report_callable(
            model_name,
            temperature,
        )
        raw_response_text = str(callable_to_use(prompt_text) or "")
        parsed = parse_report(raw_response_text)
        report_markdown = parsed["report_markdown"]
    except Exception as exc:
        raw_response_text = f"Error: {exc}"
        report_markdown = f"Report generation failed: {exc}"

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    status = "ok" if report_markdown else "error"

    phase_end(
        "final_batch_report",
        elapsed_s=duration_ms / 1000.0,
        batch_id=batch_id,
        state_version=state_version,
    )

    # Step 3: Build runtime metrics
    runtime_metrics = {
        "request_id": request_id,
        "batch_id": batch_id,
        "state_version": state_version,
        "prompt_version": PROMPT_VERSION,
        "model_name": model_name,
        "temperature": temperature,
        "duration_ms": duration_ms,
        "status": status,
        "investigated_findings_count": len(investigated_findings),
        "additional_findings_count": len(additional_findings),
        "report_length_chars": len(report_markdown),
        "schema_version": SCHEMA_VERSION,
    }

    # Step 4: Build component run metadata
    component_run = {
        "component": "final_batch_report",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "state_version": state_version,
        "status": status,
        "model_name": model_name,
        "temperature": temperature,
        "investigated_findings_count": len(investigated_findings),
        "additional_findings_count": len(additional_findings),
    }

    # Step 5: Persist artifacts
    artifact_paths = build_final_batch_report_artifact_paths(
        batch_id=batch_id,
        log_dir=log_dir,
    )
    persisted_paths = save_final_batch_report_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        report_markdown=report_markdown,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        runtime_metrics=runtime_metrics,
    )

    return {
        "report_markdown": report_markdown,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }