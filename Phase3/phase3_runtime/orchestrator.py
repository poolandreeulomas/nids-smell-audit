"""Authoritative Phase 3A batch orchestrator."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
import threading
from typing import Any, Callable

from final_batch_auditor.runner import run_final_batch_auditor
from instrumentation import (
    exception,
    phase_end,
    phase_message,
    phase_start,
    register_listener,
    unregister_listener,
)
from investigation_analysis.runner import run_investigation_analysis
from phase3_runtime.context_builder import (
    DEFAULT_SELECTION_BUDGET,
    build_initial_analysis_context,
    build_initial_semantic_inputs,
    build_phase3a_batch_id,
)
from phase3_runtime.contracts import SCHEMA_VERSION
from phase3_runtime.ledger import BatchLedger, FinalizationRecord
from phase3_runtime.round_executor import execute_round
from phase3_runtime.runtime_artifacts import (
    build_phase3a_runtime_artifact_paths,
    save_phase3a_runtime_artifacts,
)
from semantic_extraction.runner import run_semantic_extraction
from state.store import init_canonical_batch_state
from utils.run_logging import write_json


ComponentCallableMap = dict[str, Callable[[str], str]]
VALID_EXECUTION_MODES = {
    "full_batch",
    "full_round",
    "cognitive_only",
    "cognitive_workers",
}


def _artifact_path(bundle: dict[str, Any], key: str = "component_run_path") -> str:
    artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
    return str(artifact_paths.get(key, "") or "").strip()


def _require_component_ok(
    component_name: str,
    bundle: dict[str, Any],
    *,
    predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> None:
    component_run = dict(bundle.get("component_run", {}) or {})
    if not bool(component_run.get("validation_ok", False)):
        raise RuntimeError(
            f"{component_name} returned a non-authoritative bundle.")
    if predicate is not None and not predicate(bundle):
        raise RuntimeError(
            f"{component_name} did not commit the expected runtime artifact.")


def _llm_callable_for(
    llm_callables: ComponentCallableMap | None,
    component_name: str,
) -> Callable[[str], str] | None:
    if not isinstance(llm_callables, dict):
        return None
    candidate = llm_callables.get(component_name)
    if callable(candidate):
        return candidate
    return None


class _RuntimeTraceRecorder:
    def __init__(
        self,
        *,
        batch_id: str,
        event_stream_path: Path,
        terminal_log_path: Path,
    ) -> None:
        self._batch_id = batch_id
        self._event_stream_path = event_stream_path
        self._terminal_log_path = terminal_log_path
        self._lock = threading.Lock()

    def _append_event(self, event: dict[str, Any]) -> None:
        self._event_stream_path.parent.mkdir(parents=True, exist_ok=True)
        with self._event_stream_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def _append_terminal_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        self._terminal_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._terminal_log_path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(f"{line}\n")

    def record(self, event_type: str, **payload: Any) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "runtime",
            "event_type": event_type,
            "batch_id": self._batch_id,
            **payload,
        }
        with self._lock:
            self._append_event(event)

    def handle_instrumentation_event(self, event: dict[str, Any]) -> None:
        payload = dict(event.get("payload", {}) or {})
        terminal_lines = [
            str(line)
            for line in list(event.get("terminal_lines", []) or [])
            if str(line)
        ]
        persisted_event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "instrumentation",
            "batch_id": self._batch_id,
            "event_type": str(event.get("event_type") or "UNKNOWN"),
            "component": str(event.get("component") or "unknown"),
            "payload": payload,
            "terminal_lines": terminal_lines,
        }
        with self._lock:
            self._append_event(persisted_event)
            self._append_terminal_lines(terminal_lines)


def run_phase3a_batch(
    dataset_path: str | Path,
    *,
    batch_id: str | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    max_rounds: int = 3,
    selection_budget: int = DEFAULT_SELECTION_BUDGET,
    max_worker_steps: int = 8,
    max_worker_retries: int = 1,
    max_tasks_per_hypothesis: int = 4,
    max_concurrent_workers: int | None = None,
    max_concurrent_hypotheses: int | None = None,
    execution_mode: str = "full_batch",
    enable_critic: bool = False,
    log_dir: str | Path | None = None,
    caller_mode: str = "phase3a_runtime",
    llm_callables: ComponentCallableMap | None = None,
    component_model_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_dataset_path = Path(dataset_path)
    if not normalized_dataset_path.is_file():
        raise FileNotFoundError(
            f"Phase 3A dataset path does not exist: {normalized_dataset_path}")

    normalized_batch_id = str(batch_id or build_phase3a_batch_id(
        normalized_dataset_path)).strip()
    normalized_component_model_names = {
        str(component_name): str(target_model)
        for component_name, target_model in dict(component_model_names or {}).items()
        if str(component_name).strip() and str(target_model).strip()
    }
    normalized_execution_mode = str(
        execution_mode or "full_batch").strip().lower() or "full_batch"
    if normalized_execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError(
            f"execution_mode must be one of {sorted(VALID_EXECUTION_MODES)}"
        )

    effective_max_rounds = 1 if normalized_execution_mode != "full_batch" else max_rounds
    stop_after_phase = {
        "cognitive_only": "router",
        "cognitive_workers": "aggregation",
    }.get(normalized_execution_mode)
    critic_enabled = bool(enable_critic and normalized_execution_mode in {
        "full_batch",
        "full_round",
    })
    artifact_paths = build_phase3a_runtime_artifact_paths(
        batch_id=normalized_batch_id,
        log_dir=log_dir,
    )
    trace_recorder = _RuntimeTraceRecorder(
        batch_id=normalized_batch_id,
        event_stream_path=artifact_paths["event_stream_path"],
        terminal_log_path=artifact_paths["terminal_log_path"],
    )
    register_listener(trace_recorder.handle_instrumentation_event)
    created_at = datetime.now(UTC).isoformat()
    batch_start_time = perf_counter()
    phase_start("batch", batch_id=normalized_batch_id)
    initial_runtime_context = {
        "batch_id": normalized_batch_id,
        "dataset_path": str(normalized_dataset_path),
        "model_name": model_name,
        "temperature": temperature,
        "max_rounds": effective_max_rounds,
        "selection_budget": selection_budget,
        "max_worker_steps": max_worker_steps,
        "max_worker_retries": max_worker_retries,
        "max_tasks_per_hypothesis": max_tasks_per_hypothesis,
        "max_concurrent_workers": max_concurrent_workers,
        "max_concurrent_hypotheses": max_concurrent_hypotheses,
        "execution_mode": normalized_execution_mode,
        "critic_enabled": critic_enabled,
        "component_model_names": normalized_component_model_names,
        "schema_version": SCHEMA_VERSION,
    }

    start_time = perf_counter()
    initial_state: dict[str, Any] = {
        "batch_id": normalized_batch_id,
        "state_version": 0,
    }
    semantic_bundle: dict[str, Any] = {}
    initial_hypothesis_bundle: dict[str, Any] = {}
    final_batch_auditor_bundle: dict[str, Any] = {}
    round_results: list[dict[str, Any]] = []
    all_aggregation_bundles: list[dict[str, Any]] = []
    all_state_manager_bundles: list[dict[str, Any]] = []
    all_critic_bundles: list[dict[str, Any]] = []
    completed_components: list[str] = []
    failed_components: list[str] = []
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    finalization_summary: dict[str, Any] = {}
    runtime_metrics: dict[str, Any] = {}
    runtime_summary: dict[str, Any] = {}
    replay_metadata: dict[str, Any] = {}
    final_state_manager_run_path = ""
    final_batch_auditor_run_path = ""
    final_state_version = 0
    final_status = "completed_without_state_commit"
    terminal_reason = (
        "max_rounds_reached"
        if normalized_execution_mode == "full_batch"
        else f"{normalized_execution_mode}_completed"
    )
    current_component = "bootstrap"
    ledger = BatchLedger(
        batch_id=normalized_batch_id,
        dataset_path=str(normalized_dataset_path),
        model_name=model_name,
        max_rounds=effective_max_rounds,
        critic_enabled=critic_enabled,
        status="running",
        created_at=created_at,
        semantic_extraction_run_path="",
        initial_investigation_analysis_run_path="",
        initial_state_path=str(artifact_paths["initial_state_path"]),
        initial_state_version=0,
    )

    def _emit_event(event_type: str, **payload: Any) -> None:
        trace_recorder.record(event_type, **payload)

    _emit_event(
        "BATCH_START",
        execution_mode=normalized_execution_mode,
        dataset_path=str(normalized_dataset_path),
        status="running",
    )

    try:
        current_component = "semantic_extraction"
        semantic_inputs = build_initial_semantic_inputs(
            normalized_dataset_path, normalized_batch_id)
        semantic_bundle = run_semantic_extraction(
            semantic_inputs["overview_summary_min"],
            semantic_inputs["partition_context"],
            llm_callable=_llm_callable_for(
                llm_callables, "semantic_extraction"),
            model_name=model_name,
            temperature=temperature,
            caller_mode=caller_mode,
        )
        _require_component_ok("semantic_extraction", semantic_bundle)
        ledger.semantic_extraction_run_path = _artifact_path(semantic_bundle)
        completed_components.append(current_component)
        _emit_event(
            "SEMANTIC_EXTRACTION_COMPLETE",
            component_run_path=ledger.semantic_extraction_run_path,
            status="completed",
        )

        current_component = "investigation_analysis"
        analysis_context_min = build_initial_analysis_context(
            normalized_dataset_path)
        initial_hypothesis_bundle = run_investigation_analysis(
            dict(semantic_bundle.get("parsed_output", {}) or {}),
            analysis_context_min,
            analysis_iteration_context_min={},
            llm_callable=_llm_callable_for(
                llm_callables, "investigation_analysis"),
            model_name=model_name,
            temperature=temperature,
            caller_mode=caller_mode,
        )
        _require_component_ok("investigation_analysis",
                              initial_hypothesis_bundle)
        ledger.initial_investigation_analysis_run_path = _artifact_path(
            initial_hypothesis_bundle)
        completed_components.append(current_component)
        _emit_event(
            "INVESTIGATION_ANALYSIS_COMPLETE",
            component_run_path=ledger.initial_investigation_analysis_run_path,
            status="completed",
        )

        initial_state = init_canonical_batch_state(
            batch_id=normalized_batch_id,
            structural_substrate=dict(
                semantic_bundle.get("parsed_output", {}) or {}),
            hypothesis_set=dict(initial_hypothesis_bundle.get(
                "parsed_output", {}) or {}),
        ).to_dict()
        write_json(artifact_paths["initial_state_path"], initial_state)
        ledger.initial_state_version = int(
            initial_state.get("state_version") or 0)

        current_state = dict(initial_state)
        previous_round_manifest = None
        terminal_reason = (
            "max_rounds_reached"
            if normalized_execution_mode == "full_batch"
            else f"{normalized_execution_mode}_completed"
        )

        for round_index in range(1, effective_max_rounds + 1):
            round_id = f"round-{round_index:03d}"
            analysis_mode = "initial" if round_index == 1 else "refresh"
            is_final_round = round_index == effective_max_rounds

            current_component = round_id
            round_result = execute_round(
                batch_id=normalized_batch_id,
                round_id=round_id,
                round_index=round_index,
                dataset_path=normalized_dataset_path,
                semantic_bundle=semantic_bundle,
                initial_hypothesis_bundle=initial_hypothesis_bundle,
                analysis_context_min=analysis_context_min,
                canonical_batch_state=current_state,
                model_name=model_name,
                temperature=temperature,
                selection_budget=selection_budget,
                max_worker_steps=max_worker_steps,
                max_worker_retries=max_worker_retries,
                max_tasks_per_hypothesis=max_tasks_per_hypothesis,
                max_concurrent_workers=max_concurrent_workers,
                max_concurrent_hypotheses=max_concurrent_hypotheses,
                stop_after_phase=stop_after_phase,
                enable_critic=critic_enabled,
                is_final_round=is_final_round,
                llm_callables=llm_callables,
                caller_mode=caller_mode,
                analysis_mode=analysis_mode,
                previous_round_manifest=previous_round_manifest,
            )
            round_manifest = round_result["round_manifest"]
            snapshot_path = artifact_paths["round_manifests_dir"] / \
                f"{round_id}_snapshot.json"
            write_json(snapshot_path, dict(
                round_result.get("frozen_snapshot", {}) or {}))
            round_manifest.frozen_snapshot_path = str(snapshot_path)

            global_aggregation_bundle = dict(
                round_result.get("global_aggregation_bundle", {}) or {})
            if not str(round_manifest.global_aggregation_path or "").strip() and global_aggregation_bundle:
                global_aggregation_artifact_paths = dict(
                    global_aggregation_bundle.get("artifact_paths", {}) or {})
                round_manifest.global_aggregation_path = str(
                    global_aggregation_artifact_paths.get(
                        "parsed_output_path", "") or ""
                )

            ledger.round_manifests.append(round_manifest)
            round_results.append(round_result)
            previous_round_manifest = round_manifest

            all_aggregation_bundles.extend(
                round_result.get("aggregation_bundles", []))
            all_state_manager_bundles.extend(
                round_result.get("state_manager_bundles", []))
            critic_bundle = dict(round_result.get("critic_bundle", {}) or {})
            if critic_bundle:
                all_critic_bundles.append(critic_bundle)

            if round_result.get("state_manager_bundles"):
                current_state = dict(round_result.get(
                    "updated_batch_state", {}) or current_state)

            round_terminal_reason = str(
                round_result.get("terminal_reason") or "").strip()
            completed_components.append(round_id)
            _emit_event(
                "ROUND_COMPLETE",
                round_id=round_id,
                round_index=round_index,
                status=str(round_manifest.status),
                terminal_reason=round_terminal_reason or "continue",
                hypothesis_count=len(round_manifest.hypothesis_runs),
                worker_count=sum(len(record.worker_run_paths)
                                 for record in round_manifest.hypothesis_runs),
            )
            if round_terminal_reason:
                terminal_reason = round_terminal_reason
                break

        final_state_version = int(current_state.get("state_version") or 0)
        final_status = "completed_without_state_commit"

        if all_state_manager_bundles:
            current_component = "final_batch_auditor"
            final_state_manager_bundle = all_state_manager_bundles[-1]
            final_state_manager_run_path = _artifact_path(
                final_state_manager_bundle)
            final_batch_auditor_bundle = run_final_batch_auditor(
                final_state_manager_bundle,
                llm_callable=_llm_callable_for(
                    llm_callables, "final_batch_auditor"),
                model_name=model_name,
                temperature=temperature,
                caller_mode=caller_mode,
                is_final_batch=True,
                batch_component_bundles={
                    "aggregation": all_aggregation_bundles,
                    "critic": all_critic_bundles,
                    "state_manager": all_state_manager_bundles,
                },
            )
            _require_component_ok(
                "final_batch_auditor",
                final_batch_auditor_bundle,
                predicate=lambda payload: bool(
                    dict(payload.get("component_run", {}) or {}).get(
                        "report_committed", False)
                ),
            )
            final_batch_auditor_run_path = _artifact_path(
                final_batch_auditor_bundle)
            final_status = "completed"
            completed_components.append(current_component)
            _emit_event(
                "FINAL_BATCH_AUDITOR_COMPLETE",
                component_run_path=final_batch_auditor_run_path,
                status="completed",
            )
        elif normalized_execution_mode in {"cognitive_only", "cognitive_workers"}:
            final_status = "completed_partial_runtime"

        completed_at = datetime.now(UTC).isoformat()
        ledger.status = "completed"
        ledger.completed_at = completed_at
        ledger.finalization = FinalizationRecord(
            terminal_reason=terminal_reason,
            final_state_manager_run_path=final_state_manager_run_path,
            final_batch_auditor_run_path=final_batch_auditor_run_path,
            final_state_version=final_state_version,
            final_status=final_status,
        )
        finalization_summary = ledger.finalization.to_dict()

        runtime_metrics = {
            "batch_id": normalized_batch_id,
            "model_name": model_name,
            "duration_ms": round((perf_counter() - start_time) * 1000.0, 3),
            "round_count": len(ledger.round_manifests),
            "analysis_refresh_count": len(
                [manifest for manifest in ledger.round_manifests if manifest.analysis_mode == "refresh"]
            ),
            "execution_mode": normalized_execution_mode,
            "final_state_version": final_state_version,
            "critic_run_count": len(all_critic_bundles),
            "final_audit_committed": bool(final_batch_auditor_bundle),
            "status": ledger.status,
            "terminal_reason": terminal_reason,
            "completed_component_count": len(completed_components),
            "failed_component_count": len(failed_components),
            "warning_count": len(warnings),
            "error_count": len(errors),
            "schema_version": SCHEMA_VERSION,
        }
        component_run = {
            "component": "phase3a_runtime",
            "created_at": created_at,
            "completed_at": completed_at,
            "schema_version": SCHEMA_VERSION,
            "batch_id": normalized_batch_id,
            "status": ledger.status,
            "final_status": final_status,
            "terminal_reason": terminal_reason,
            "validation_ok": True,
            "execution_mode": normalized_execution_mode,
            "final_state_version": final_state_version,
            "round_count": len(ledger.round_manifests),
            "model_name": model_name,
            "critic_enabled": critic_enabled,
            "caller_mode": caller_mode,
            "completed_components": completed_components,
            "failed_components": failed_components,
            "warnings": warnings,
            "errors": errors,
        }
        replay_metadata = {
            "fresh_execution": True,
            "schema_version": SCHEMA_VERSION,
        }
        runtime_summary = {
            "run_id": Path(str(artifact_paths["run_dir"])).name,
            "batch_id": normalized_batch_id,
            "mode": normalized_execution_mode,
            "status": ledger.status,
            "final_status": final_status,
            "terminal_reason": terminal_reason,
            "completed_components": list(completed_components),
            "failed_components": list(failed_components),
            "warnings": list(warnings),
            "errors": list(errors),
            "round_count": len(ledger.round_manifests),
            "final_state_version": final_state_version,
        }
        run_manifest = {
            "run_id": Path(str(artifact_paths["run_dir"])).name,
            "batch_id": normalized_batch_id,
            "mode": normalized_execution_mode,
            "status": ledger.status,
            "start_time": created_at,
            "end_time": completed_at,
            "dataset": str(normalized_dataset_path),
            "completed_components": list(completed_components),
            "failed_components": list(failed_components),
            "warnings": list(warnings),
            "errors": list(errors),
        }
        persisted_paths = save_phase3a_runtime_artifacts(
            artifact_paths=artifact_paths,
            component_run=component_run,
            batch_ledger=ledger,
            initial_runtime_context=initial_runtime_context,
            finalization_summary=finalization_summary,
            runtime_metrics=runtime_metrics,
            replay_metadata=replay_metadata,
            runtime_summary=runtime_summary,
            run_manifest=run_manifest,
        )

        _emit_event(
            "BATCH_COMPLETE",
            status=ledger.status,
            final_status=final_status,
            terminal_reason=terminal_reason,
        )
        phase_message("batch", "COMPLETE", batch_id=normalized_batch_id)
        phase_end("batch", elapsed_s=perf_counter() -
                  batch_start_time, batch_id=normalized_batch_id)

        return {
            "component_run": component_run,
            "artifact_paths": persisted_paths,
            "batch_ledger": ledger,
            "initial_runtime_context": initial_runtime_context,
            "initial_state": initial_state,
            "semantic_extraction_bundle": semantic_bundle,
            "initial_investigation_analysis_bundle": initial_hypothesis_bundle,
            "round_results": round_results,
            "final_batch_auditor_bundle": final_batch_auditor_bundle,
            "finalization_summary": finalization_summary,
            "runtime_metrics": runtime_metrics,
            "runtime_summary": runtime_summary,
            "replay_metadata": replay_metadata,
        }
    except Exception as exc:  # noqa: BLE001
        error_payload = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        errors.append(error_payload)
        if current_component not in failed_components:
            failed_components.append(current_component)

        completed_at = datetime.now(UTC).isoformat()
        ledger.status = "failed"
        ledger.completed_at = completed_at
        ledger.finalization = FinalizationRecord(
            terminal_reason="runtime_error",
            final_state_manager_run_path=final_state_manager_run_path,
            final_batch_auditor_run_path=final_batch_auditor_run_path,
            final_state_version=final_state_version,
            final_status="failed",
        )
        finalization_summary = ledger.finalization.to_dict()

        runtime_metrics = {
            "batch_id": normalized_batch_id,
            "model_name": model_name,
            "duration_ms": round((perf_counter() - start_time) * 1000.0, 3),
            "round_count": len(ledger.round_manifests),
            "analysis_refresh_count": len(
                [manifest for manifest in ledger.round_manifests if manifest.analysis_mode == "refresh"]
            ),
            "execution_mode": normalized_execution_mode,
            "final_state_version": final_state_version,
            "critic_run_count": len(all_critic_bundles),
            "final_audit_committed": bool(final_batch_auditor_bundle),
            "status": ledger.status,
            "terminal_reason": "runtime_error",
            "failed_component": current_component,
            "completed_component_count": len(completed_components),
            "failed_component_count": len(failed_components),
            "warning_count": len(warnings),
            "error_count": len(errors),
            "schema_version": SCHEMA_VERSION,
        }
        component_run = {
            "component": "phase3a_runtime",
            "created_at": created_at,
            "completed_at": completed_at,
            "schema_version": SCHEMA_VERSION,
            "batch_id": normalized_batch_id,
            "status": ledger.status,
            "final_status": "failed",
            "terminal_reason": "runtime_error",
            "validation_ok": False,
            "execution_mode": normalized_execution_mode,
            "final_state_version": final_state_version,
            "round_count": len(ledger.round_manifests),
            "model_name": model_name,
            "critic_enabled": critic_enabled,
            "caller_mode": caller_mode,
            "completed_components": completed_components,
            "failed_components": failed_components,
            "warnings": warnings,
            "errors": errors,
            "error": error_payload,
        }
        replay_metadata = {
            "fresh_execution": True,
            "schema_version": SCHEMA_VERSION,
            "failure": True,
        }
        runtime_summary = {
            "run_id": Path(str(artifact_paths["run_dir"])).name,
            "batch_id": normalized_batch_id,
            "mode": normalized_execution_mode,
            "status": ledger.status,
            "final_status": "failed",
            "terminal_reason": "runtime_error",
            "completed_components": list(completed_components),
            "failed_components": list(failed_components),
            "warnings": list(warnings),
            "errors": list(errors),
            "round_count": len(ledger.round_manifests),
            "final_state_version": final_state_version,
            "error": error_payload,
        }
        run_manifest = {
            "run_id": Path(str(artifact_paths["run_dir"])).name,
            "batch_id": normalized_batch_id,
            "mode": normalized_execution_mode,
            "status": ledger.status,
            "start_time": created_at,
            "end_time": completed_at,
            "dataset": str(normalized_dataset_path),
            "completed_components": list(completed_components),
            "failed_components": list(failed_components),
            "warnings": list(warnings),
            "errors": list(errors),
        }
        persisted_paths = save_phase3a_runtime_artifacts(
            artifact_paths=artifact_paths,
            component_run=component_run,
            batch_ledger=ledger,
            initial_runtime_context=initial_runtime_context,
            finalization_summary=finalization_summary,
            runtime_metrics=runtime_metrics,
            replay_metadata=replay_metadata,
            runtime_summary=runtime_summary,
            run_manifest=run_manifest,
        )

        exception("batch", exc)
        _emit_event(
            "BATCH_FAILED",
            status=ledger.status,
            failed_component=current_component,
            error=error_payload,
        )
        phase_message(
            "batch",
            "FAILED",
            batch_id=normalized_batch_id,
            error=error_payload["message"],
        )
        phase_end("batch", elapsed_s=perf_counter() -
                  batch_start_time, batch_id=normalized_batch_id)

        return {
            "component_run": component_run,
            "artifact_paths": persisted_paths,
            "batch_ledger": ledger,
            "initial_runtime_context": initial_runtime_context,
            "initial_state": initial_state,
            "semantic_extraction_bundle": semantic_bundle,
            "initial_investigation_analysis_bundle": initial_hypothesis_bundle,
            "round_results": round_results,
            "final_batch_auditor_bundle": final_batch_auditor_bundle,
            "finalization_summary": finalization_summary,
            "runtime_metrics": runtime_metrics,
            "runtime_summary": runtime_summary,
            "replay_metadata": replay_metadata,
        }
    finally:
        unregister_listener(trace_recorder.handle_instrumentation_event)
