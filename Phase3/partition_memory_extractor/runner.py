"""Execution wrapper for the Phase 3B Partition Memory Extractor.

Flow:

    Final Batch Report run directory
        ↓ (load_final_batch_report_bundle)
    Bundle with report_markdown, component_run, runtime_metrics
        ↓
    Build Prompt
        ↓
    Call LLM
        ↓
    Parse Partition Memory
        ↓
    Persist Artifacts
        ↓
    Return Results
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from final_batch_report.runtime_artifacts import load_final_batch_report_bundle
from instrumentation import phase_start, phase_end
from partition_memory_extractor.contracts import SCHEMA_VERSION
from partition_memory_extractor.parser import parse_partition_memory
from partition_memory_extractor.prompt_builder import (
    PROMPT_VERSION,
    build_partition_memory_prompt,
)
from partition_memory_extractor.runtime_artifacts import (
    build_partition_memory_artifact_paths,
    save_partition_memory_artifacts,
)
from utils.openai_response import build_responses_create_kwargs, extract_response_text


PartitionMemoryCallable = Callable[[str], str]


def _build_openai_partition_memory_callable(
    model_name: str,
    temperature: float = 0.0,
) -> PartitionMemoryCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI package is not installed. "
                "Install 'openai' to run partition_memory_extractor."
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


def run_partition_memory_extractor(
    final_batch_report_run_dir: str | Path,
    partition_id: str,
    *,
    llm_callable: PartitionMemoryCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
) -> dict[str, Any]:
    """Generate a Partition Memory from a Final Batch Report.

    Flow:
        Load Final Batch Report Bundle
            ↓
        Build Prompt
            ↓
        Call LLM
            ↓
        Parse Partition Memory
            ↓
        Persist Artifacts
            ↓
        Return Results

    Args:
        final_batch_report_run_dir: Directory of a Final Batch Report run.
        partition_id: Human-readable partition identifier.
        llm_callable: Optional custom LLM callable.
        model_name: OpenAI model name (default: gpt-4.1-mini).
        temperature: LLM temperature (default: 0.0).
        log_dir: Optional log directory override.

    Returns:
        Dict with partition_memory, runtime_metrics, artifact_paths.
    """
    request_id = f"partition_memory_extractor_{uuid4().hex}"

    # Step 1: Load Final Batch Report bundle
    bundle = load_final_batch_report_bundle(str(final_batch_report_run_dir))
    report_markdown = bundle["report_markdown"]
    component_run = bundle["component_run"]
    runtime_metrics_in = bundle["runtime_metrics"]

    batch_id = component_run.get("batch_id") or "unknown_batch"
    state_version = component_run.get("state_version") or "unknown"

    # Step 2: Build Prompt
    prompt_text = build_partition_memory_prompt(
        partition_id=partition_id,
        report_markdown=report_markdown,
        component_run=component_run,
        runtime_metrics=runtime_metrics_in,
    )

    partition_memory: dict[str, Any] = {}
    raw_response_text = ""

    start_time = perf_counter()
    phase_start(
        "partition_memory_extractor",
        batch_id=batch_id,
        state_version=state_version,
    )

    try:
        callable_to_use = (
            llm_callable
            or _build_openai_partition_memory_callable(
                model_name,
                temperature,
            )
        )
        raw_response_text = str(callable_to_use(prompt_text) or "")
        parsed = parse_partition_memory(raw_response_text)
        partition_memory = dict(parsed)
    except Exception as exc:
        raw_response_text = f"Error: {exc}"
        partition_memory = {"error": str(exc)}

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    status = "ok" if partition_memory and "error" not in partition_memory else "error"

    phase_end(
        "partition_memory_extractor",
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
        "partition_id": partition_id,
        "schema_version": SCHEMA_VERSION,
    }

    # Step 4: Build component run metadata
    component_run_out = {
        "component": "partition_memory_extractor",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "state_version": state_version,
        "status": status,
        "model_name": model_name,
        "temperature": temperature,
        "partition_id": partition_id,
    }

    # Step 5: Persist artifacts
    artifact_paths = build_partition_memory_artifact_paths(
        batch_id=batch_id,
        log_dir=log_dir,
    )
    persisted_paths = save_partition_memory_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run_out,
        partition_memory=partition_memory,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        runtime_metrics=runtime_metrics,
    )

    return {
        "partition_memory": partition_memory,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }