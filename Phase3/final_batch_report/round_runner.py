"""Execution wrapper for Phase 3A Round-Level Final Reports.

Orchestrates input resolution, prompt building, LLM execution, markdown parsing,
artifact persistence, and regeneration from persisted artifacts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from data.dataset_config import DatasetConfig
from final_batch_report.parser import parse_report
from final_batch_report.round_contracts import (
    ROUND_REPORT_PROMPT_VERSION,
    ROUND_REPORT_SCHEMA_VERSION,
)
from final_batch_report.round_input_resolver import (
    resolve_round_report_context,
)
from final_batch_report.round_prompt_builder import (
    build_round_report_prompt,
)
from final_batch_report.round_runtime_artifacts import (
    build_round_report_artifact_paths,
    save_round_report_artifacts,
)
from instrumentation import phase_end, phase_start
from state.schema import CanonicalBatchState
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from utils.run_logging import load_json

RoundReportCallable = Callable[[str], str]


def _build_openai_round_report_callable(
    model_name: str,
    temperature: float = 0.0,
) -> RoundReportCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run round_report."
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


def run_round_report(
    *,
    round_manifest: RoundManifest | dict[str, Any],
    frozen_snapshot: dict[str, Any] | None = None,
    canonical_state: CanonicalBatchState | dict[str, Any] | None = None,
    dataset_path: str | Path | None = None,
    dataset_config: DatasetConfig | None = None,
    round_bundles: dict[str, Any] | None = None,
    round_manifest_path: str | Path | None = None,
    llm_callable: RoundReportCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a single-round Final Audit Report.

    Args:
        round_manifest: RoundManifest instance or dict.
        frozen_snapshot: Optional round snapshot dict.
        canonical_state: Optional post-round CanonicalBatchState.
        dataset_path: Optional path to dataset partition.
        dataset_config: Optional DatasetConfig.
        round_bundles: Optional dictionary of in-memory round execution bundles.
        round_manifest_path: Optional path to persisted round manifest file on disk.
        llm_callable: Optional custom LLM callable.
        model_name: Target model name (default: gpt-4.1-mini).
        temperature: Sampling temperature (default: 0.0).
        log_dir: Directory override for artifact persistence.

    Returns:
        Dict with report_markdown, runtime_metrics, artifact_paths, component_run, context.
    """
    manifest_dict = (
        round_manifest.to_dict()
        if hasattr(round_manifest, "to_dict")
        else dict(round_manifest or {})
    )
    round_id = str(manifest_dict.get("round_id") or "round-001").strip()
    status = str(manifest_dict.get("status") or "unknown").strip()

    # Rule: Incomplete or failed rounds cannot produce a successful final report
    if status not in {"completed", "ok"}:
        raise ValueError(
            f"Cannot generate Final Report for round '{round_id}' with status '{status}'. "
            "Only completed rounds are eligible for reporting."
        )

    request_id = f"round_report_{uuid4().hex}"

    # Step 1: Resolve structured round context
    report_context = resolve_round_report_context(
        round_manifest=manifest_dict,
        frozen_snapshot=frozen_snapshot,
        canonical_state=canonical_state,
        dataset_path=dataset_path,
        dataset_config=dataset_config,
        round_bundles=round_bundles,
    )

    batch_id = report_context["execution_identity"]["batch_id"]

    # Step 2: Build LLM prompt
    prompt_text = build_round_report_prompt(report_context)

    report_markdown = ""
    raw_response_text = ""

    start_time = perf_counter()
    phase_start(
        "round_report",
        batch_id=batch_id,
        round_id=round_id,
    )

    try:
        callable_to_use = llm_callable or _build_openai_round_report_callable(
            model_name,
            temperature,
        )
        raw_response_text = str(callable_to_use(prompt_text) or "")
        parsed = parse_report(raw_response_text)
        report_markdown = parsed["report_markdown"]
    except Exception as exc:
        raw_response_text = f"Error: {exc}"
        report_markdown = f"# Round Report Generation Failed\n\nError: {exc}"
        raise RuntimeError(f"Round report generation failed: {exc}") from exc
    finally:
        duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
        phase_end(
            "round_report",
            elapsed_s=duration_ms / 1000.0,
            batch_id=batch_id,
            round_id=round_id,
        )

    # Step 3: Build runtime metrics
    runtime_metrics = {
        "request_id": request_id,
        "batch_id": batch_id,
        "round_id": round_id,
        "prompt_version": ROUND_REPORT_PROMPT_VERSION,
        "schema_version": ROUND_REPORT_SCHEMA_VERSION,
        "model_name": model_name,
        "temperature": temperature,
        "duration_ms": duration_ms,
        "status": "ok",
        "worker_findings_count": len(report_context["round_evidence"]["worker_findings"]),
        "tool_executions_count": len(report_context["round_evidence"]["tool_executions"]),
        "updated_hypotheses_count": len(report_context["state_transitions"]["updated_hypotheses"]),
        "report_length_chars": len(report_markdown),
    }

    # Step 4: Build component run metadata
    component_run = {
        "component": "round_report",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "prompt_version": ROUND_REPORT_PROMPT_VERSION,
        "schema_version": ROUND_REPORT_SCHEMA_VERSION,
        "batch_id": batch_id,
        "round_id": round_id,
        "status": "ok",
        "model_name": model_name,
        "temperature": temperature,
    }

    # Step 5: Persist artifacts and link
    artifact_paths = build_round_report_artifact_paths(
        batch_id=batch_id,
        round_id=round_id,
        log_dir=log_dir,
    )
    persisted_paths = save_round_report_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        report_markdown=report_markdown,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        runtime_metrics=runtime_metrics,
        round_manifest_path=round_manifest_path,
    )

    return {
        "report_markdown": report_markdown,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
        "component_run": component_run,
        "context": report_context,
    }


def regenerate_round_report(
    *,
    round_manifest_path: str | Path,
    dataset_path: str | Path | None = None,
    dataset_config: DatasetConfig | None = None,
    llm_callable: RoundReportCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Regenerate a single-round Final Report from persisted artifacts on disk.

    Does NOT re-execute workers, tools, or investigation steps.
    """
    manifest_file = Path(round_manifest_path)
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Round manifest file not found: {round_manifest_path}")

    raw_manifest = load_json(manifest_file)
    if not isinstance(raw_manifest, dict):
        raise ValueError(f"Invalid round manifest at {round_manifest_path}")

    snapshot_path = str(raw_manifest.get("frozen_snapshot_path") or "").strip()
    frozen_snapshot = load_json(Path(snapshot_path)) if snapshot_path and Path(snapshot_path).is_file() else None

    # Load canonical state from state manager run if available
    canonical_state = None
    hypothesis_runs = list(raw_manifest.get("hypothesis_runs", []) or [])
    for rec in reversed(hypothesis_runs):
        sm_path = str(rec.get("state_manager_run_path", "") or "").strip()
        if sm_path and Path(sm_path).is_file():
            sm_data = load_json(Path(sm_path))
            if isinstance(sm_data, dict):
                st = sm_data.get("updated_batch_state")
                if isinstance(st, dict):
                    canonical_state = CanonicalBatchState.from_dict(st)
                    break

    return run_round_report(
        round_manifest=raw_manifest,
        frozen_snapshot=frozen_snapshot,
        canonical_state=canonical_state,
        dataset_path=dataset_path,
        dataset_config=dataset_config,
        round_manifest_path=str(manifest_file),
        llm_callable=llm_callable,
        model_name=model_name,
        temperature=temperature,
        log_dir=log_dir,
    )
