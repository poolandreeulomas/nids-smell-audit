"""Deterministic round execution for the authoritative Phase 3A runtime."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from aggregation.contracts import build_worker_result_set
from aggregation.runner import run_aggregation
from critic.runner import run_critic
from hypothesis_ranking.runner import run_hypothesis_ranking
from investigation_analysis.runner import run_investigation_analysis
from planner.context_resolver import resolve_selected_hypothesis_context
from planner.runner import run_planner
from phase3_runtime.inter_hypothesis_aggregation import run_inter_hypothesis_aggregation
from phase3_runtime.context_builder import (
    DEFAULT_SELECTION_BUDGET,
    build_critic_guidance_context,
    build_analysis_iteration_context,
    build_planner_context,
    build_round_ranking_state,
    build_round_snapshot,
    build_router_context,
    build_worker_runtime_refs,
    overlay_hypothesis_current_status,
)
from phase3_runtime.ledger import HypothesisExecutionRecord, RoundManifest
from phase3_runtime.state_manager_adapter import build_state_manager_projections
from router.runner import run_router
from state_manager.runner import run_state_manager
from worker.runner import run_worker
from instrumentation import barrier_status, phase_start, phase_end, exception, phase_message, validation_result


ComponentCallableMap = dict[str, Callable[[str], str]]


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


def _resolve_pool_size(requested_size: int | None, *, fallback_size: int) -> int:
    if requested_size is None:
        return max(1, fallback_size)
    try:
        return max(1, min(int(requested_size), fallback_size))
    except Exception:
        return max(1, fallback_size)


def _build_global_aggregation_summary(
    *,
    batch_id: str,
    round_id: str,
    selected_hypothesis_ids: list[str],
    aggregation_bundles: list[dict[str, Any]],
) -> dict[str, Any]:
    synthesis_records: list[dict[str, Any]] = []
    merged_findings: list[str] = []
    preserved_contradictions: set[str] = set()
    open_gaps: set[str] = set()
    evidence_refs: set[str] = set()
    missing_hypothesis_ids: list[str] = []

    aggregation_by_hypothesis_id = {
        str(dict(bundle.get("component_run", {}) or {}).get("hypothesis_id") or "").strip(): bundle
        for bundle in aggregation_bundles
        if str(dict(bundle.get("component_run", {}) or {}).get("hypothesis_id") or "").strip()
    }

    for hypothesis_id in selected_hypothesis_ids:
        bundle = aggregation_by_hypothesis_id.get(hypothesis_id, {})
        handoff = dict(bundle.get("aggregation_handoff", {}) or {})
        artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
        if not artifact_paths.get("component_run_path"):
            missing_hypothesis_ids.append(hypothesis_id)
        finding_lines = [str(item).strip() for item in (
            handoff.get("merged_findings") or []) if str(item).strip()]
        contradiction_lines = [str(item).strip() for item in (
            handoff.get("preserved_contradictions") or []) if str(item).strip()]
        gap_lines = [str(item).strip() for item in (
            handoff.get("open_gaps") or []) if str(item).strip()]
        evidence_lines = [str(item).strip() for item in (
            handoff.get("evidence_refs") or []) if str(item).strip()]

        synthesis_records.append(
            {
                "hypothesis_id": hypothesis_id,
                "aggregation_run_path": str(artifact_paths.get("component_run_path", "") or ""),
                "update_focus": str(handoff.get("update_focus") or "").strip(),
                "merged_findings": finding_lines,
                "preserved_contradictions": contradiction_lines,
                "open_gaps": gap_lines,
                "evidence_refs": evidence_lines,
            }
        )
        merged_findings.extend(
            f"{hypothesis_id}: {finding}" for finding in finding_lines)
        preserved_contradictions.update(contradiction_lines)
        open_gaps.update(gap_lines)
        evidence_refs.update(evidence_lines)

    validation_report = {
        "ok": not missing_hypothesis_ids,
        "errors": [
            {
                "field": "selected_hypothesis_ids",
                "message": f"missing aggregation run for hypothesis_id={hypothesis_id}",
            }
            for hypothesis_id in missing_hypothesis_ids
        ],
        "warnings": [],
    }
    status = "ok" if validation_report["ok"] else "error"
    summary_payload = {
        "batch_id": batch_id,
        "round_id": round_id,
        "selected_hypothesis_ids": list(selected_hypothesis_ids),
        "hypothesis_syntheses": synthesis_records,
        "cross_hypothesis_findings": merged_findings,
        "preserved_contradictions": sorted(preserved_contradictions),
        "remaining_open_gaps": sorted(open_gaps),
        "evidence_refs": sorted(evidence_refs),
        "state_update_order": list(selected_hypothesis_ids),
    }
    return {
        **summary_payload,
        "prompt_text": "",
        "raw_response_text": "",
        "parsed_output": dict(summary_payload),
        "component_run": {
            "component": "inter_hypothesis_aggregation",
            "batch_id": batch_id,
            "round_id": round_id,
            "status": status,
            "validation_ok": validation_report["ok"],
            "authoritative_status": validation_report["ok"],
            "selected_hypothesis_count": len(selected_hypothesis_ids),
            "source_aggregation_count": len(synthesis_records),
        },
        "inputs": {
            "selected_hypothesis_ids": list(selected_hypothesis_ids),
            "source_aggregation_runs": [
                {
                    "hypothesis_id": record["hypothesis_id"],
                    "aggregation_run_path": record["aggregation_run_path"],
                }
                for record in synthesis_records
            ],
        },
        "validation_report": validation_report,
        "runtime_metrics": {
            "selected_hypothesis_count": len(selected_hypothesis_ids),
            "source_aggregation_count": len(synthesis_records),
            "cross_hypothesis_finding_count": len(merged_findings),
            "contradiction_count": len(preserved_contradictions),
            "open_gap_count": len(open_gaps),
            "evidence_ref_count": len(evidence_refs),
        },
        "replay_metadata": {
            "fresh_execution": True,
            "deterministic": True,
        },
    }


def _await_workers_and_run_aggregation(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    task_ids: list[str],
    worker_futures: list[Future[dict[str, Any]]],
    llm_callables: ComponentCallableMap | None,
    model_name: str,
    temperature: float,
    caller_mode: str,
) -> dict[str, Any]:
    worker_bundles: list[dict[str, Any]] = []
    worker_results: list[dict[str, Any]] = []
    source_run_dirs: list[str] = []
    # Barrier: report expected workers before awaiting
    phase_message("hypothesis", f"WAITING FOR {len(task_ids)} WORKERS",
                  hypothesis_id=hypothesis_id, round_id=round_id)
    barrier_status("hypothesis_aggregator", expected=len(task_ids), completed=0,
                   waiting_for=task_ids, batch_id=batch_id, round_id=round_id, hypothesis_id=hypothesis_id)

    for worker_future in worker_futures:
        worker_bundle = worker_future.result()
        _require_component_ok(
            "worker",
            worker_bundle,
            predicate=lambda payload: bool(
                dict(payload.get("component_run", {}) or {}).get(
                    "result_committed", False)
            ),
        )
        worker_bundles.append(worker_bundle)
        worker_results.append(
            dict(worker_bundle.get("worker_result", {}) or {}))
        worker_run_path = _artifact_path(worker_bundle)
        if worker_run_path:
            source_run_dirs.append(str(Path(worker_run_path).parent))

    worker_result_set = build_worker_result_set(
        batch_id=batch_id,
        round_id=round_id,
        hypothesis_id=hypothesis_id,
        worker_results=worker_results,
    )
    aggregation_bundle = run_aggregation(
        worker_result_set,
        expected_task_ids=task_ids,
        source_run_dirs=source_run_dirs,
        llm_callable=_llm_callable_for(llm_callables, "aggregation"),
        model_name=model_name,
        temperature=temperature,
        caller_mode=caller_mode,
    )
    _require_component_ok(
        "aggregation",
        aggregation_bundle,
        predicate=lambda payload: bool(
            dict(payload.get("component_run", {}) or {}).get(
                "handoff_committed", False)
        ),
    )
    phase_message("hypothesis", "ALL WORKERS COMPLETE",
                  hypothesis_id=hypothesis_id, round_id=round_id)
    return {
        "worker_bundles": worker_bundles,
        "aggregation_bundle": aggregation_bundle,
    }


def execute_round(
    *,
    batch_id: str,
    round_id: str,
    round_index: int,
    dataset_path: str | Path,
    semantic_bundle: dict[str, Any],
    initial_hypothesis_bundle: dict[str, Any],
    analysis_context_min: dict[str, Any],
    canonical_batch_state: dict[str, Any],
    model_name: str,
    temperature: float,
    selection_budget: int = DEFAULT_SELECTION_BUDGET,
    max_worker_steps: int = 8,
    max_worker_retries: int = 1,
    max_tasks_per_hypothesis: int = 4,
    max_concurrent_workers: int | None = None,
    max_concurrent_hypotheses: int | None = None,
    stop_after_phase: str | None = None,
    enable_critic: bool = False,
    is_final_round: bool = False,
    llm_callables: ComponentCallableMap | None = None,
    caller_mode: str = "phase3a_runtime",
    analysis_mode: str = "initial",
    previous_round_manifest: RoundManifest | dict[str, Any] | None = None,
) -> dict[str, Any]:
    round_start_time = perf_counter()
    phase_start("round", batch_id=batch_id, round_id=round_id)
    semantic_substrate = dict(semantic_bundle.get("parsed_output", {}) or {})
    frozen_snapshot = build_round_snapshot(
        batch_id=batch_id,
        round_id=round_id,
        round_index=round_index,
        analysis_mode=analysis_mode,
        canonical_batch_state=canonical_batch_state,
        initial_hypothesis_set=dict(
            initial_hypothesis_bundle.get("parsed_output", {}) or {}),
    )
    current_state = dict(canonical_batch_state or {})
    critic_guidance_context = build_critic_guidance_context(
        previous_round_manifest)
    critic_guidance_by_module = dict(
        critic_guidance_context.get("per_module", {}) or {})

    def _critic_snippets_for(module_name: str) -> list[str]:
        module_bucket = critic_guidance_by_module.get(module_name, {})
        if not isinstance(module_bucket, dict):
            return []
        return list(module_bucket.get("prompt_snippets", []) or [])

    analysis_bundle = initial_hypothesis_bundle
    if analysis_mode != "initial":
        analysis_iteration_context = build_analysis_iteration_context(
            dict(initial_hypothesis_bundle.get("parsed_output", {}) or {}),
            current_state,
            critic_guidance=_critic_snippets_for("investigation_analysis"),
        )
        analysis_bundle = run_investigation_analysis(
            semantic_substrate,
            analysis_context_min,
            analysis_iteration_context_min=analysis_iteration_context,
            llm_callable=_llm_callable_for(
                llm_callables, "investigation_analysis"),
            model_name=model_name,
            temperature=temperature,
            caller_mode=caller_mode,
        )
        _require_component_ok("investigation_analysis", analysis_bundle)

    candidate_hypothesis_set = overlay_hypothesis_current_status(
        dict(analysis_bundle.get("parsed_output", {}) or {}),
        current_state,
    )
    ranking_state_min = build_round_ranking_state(
        current_state,
        round_id=round_id,
        selection_budget=selection_budget,
        critic_guidance=_critic_snippets_for("hypothesis_ranking"),
    )
    ranking_bundle = run_hypothesis_ranking(
        candidate_hypothesis_set,
        ranking_state_min,
        llm_callable=_llm_callable_for(llm_callables, "hypothesis_ranking"),
        model_name=model_name,
        temperature=temperature,
        caller_mode=caller_mode,
    )
    _require_component_ok("hypothesis_ranking", ranking_bundle)

    ranking_output = dict(
        ranking_bundle.get("parsed_output")
        or ranking_bundle.get("ranking_decision")
        or {}
    )
    selected_hypothesis_ids = [
        str(item).strip()
        for item in (ranking_output.get("selected_hypothesis_ids") or [])
        if str(item).strip()
    ]
    deferred_hypothesis_ids = [
        str(item).strip()
        for item in (ranking_output.get("deferred_hypothesis_ids") or [])
        if str(item).strip()
    ]
    manifest = RoundManifest(
        round_id=round_id,
        round_index=round_index,
        analysis_mode=analysis_mode,
        analysis_run_path=_artifact_path(analysis_bundle),
        ranking_run_path=_artifact_path(ranking_bundle),
        selected_hypothesis_ids=selected_hypothesis_ids,
        deferred_hypothesis_ids=deferred_hypothesis_ids,
        start_state_version=int(current_state.get("state_version") or 0),
    )
    if not selected_hypothesis_ids:
        manifest.status = "terminated"
        manifest.terminal_reason = "no_selected_hypotheses"
        manifest.end_state_version = manifest.start_state_version
        return {
            "analysis_bundle": analysis_bundle,
            "ranking_bundle": ranking_bundle,
            "planner_bundle": {},
            "router_bundles": [],
            "worker_bundles": [],
            "aggregation_bundles": [],
            "state_manager_bundles": [],
            "critic_bundle": {},
            "global_aggregation_summary": {},
            "updated_batch_state": current_state,
            "frozen_snapshot": frozen_snapshot,
            "round_manifest": manifest,
            "terminal_reason": manifest.terminal_reason,
        }

    selected_hypothesis_context = resolve_selected_hypothesis_context(
        ranking_decision_min=ranking_output,
        investigation_hypothesis_set=candidate_hypothesis_set,
    )
    planner_round_context = build_planner_context(
        selected_hypothesis_context,
        round_id,
        critic_guidance=_critic_snippets_for("planner"),
    )
    planner_bundle = run_planner(
        {
            "batch_id": batch_id,
            "round_id": round_id,
            "selected_hypothesis_ids": selected_hypothesis_ids,
        },
        selected_hypothesis_context,
        planner_round_context,
        llm_callable=_llm_callable_for(llm_callables, "planner"),
        model_name=model_name,
        temperature=temperature,
        caller_mode=caller_mode,
    )
    _require_component_ok("planner", planner_bundle)
    manifest.planner_run_path = _artifact_path(planner_bundle)

    router_bundles: list[dict[str, Any]] = []
    worker_bundles: list[dict[str, Any]] = []
    aggregation_bundles: list[dict[str, Any]] = []
    state_manager_bundles: list[dict[str, Any]] = []
    critic_bundle: dict[str, Any] = {}
    aggregation_by_hypothesis_id: dict[str, dict[str, Any]] = {}
    worker_by_hypothesis_id: dict[str, list[dict[str, Any]]] = {}

    planner_strategies = [
        dict(item)
        for item in (planner_bundle.get("parsed_output", {}).get("planner_strategies") or [])
        if isinstance(item, dict)
    ]
    if not planner_strategies:
        manifest.status = "terminated"
        manifest.terminal_reason = "no_planner_strategies"
        manifest.end_state_version = manifest.start_state_version
        return {
            "analysis_bundle": analysis_bundle,
            "ranking_bundle": ranking_bundle,
            "planner_bundle": planner_bundle,
            "router_bundles": [],
            "worker_bundles": [],
            "aggregation_bundles": [],
            "state_manager_bundles": [],
            "critic_bundle": {},
            "global_aggregation_summary": {},
            "updated_batch_state": current_state,
            "frozen_snapshot": frozen_snapshot,
            "round_manifest": manifest,
            "terminal_reason": manifest.terminal_reason,
        }

    if stop_after_phase == "router":
        for planner_strategy in planner_strategies:
            hypothesis_id = str(planner_strategy.get(
                "hypothesis_id") or "").strip()
            execution_record = HypothesisExecutionRecord(
                hypothesis_id=hypothesis_id,
                planner_strategy_id=str(
                    planner_strategy.get("strategy_id") or "").strip(),
                start_state_version=manifest.start_state_version,
            )
            router_context_min = build_router_context(
                planner_round_context=planner_round_context,
                selected_hypothesis_context=selected_hypothesis_context,
                planner_strategy=planner_strategy,
                max_worker_steps=max_worker_steps,
                max_worker_retries=max_worker_retries,
                max_tasks_per_hypothesis=max_tasks_per_hypothesis,
            )
            router_bundle = run_router(
                planner_strategy,
                router_context_min,
                batch_id=batch_id,
                round_id=round_id,
                llm_callable=_llm_callable_for(llm_callables, "router"),
                model_name=model_name,
                temperature=temperature,
                caller_mode=caller_mode,
            )
            _require_component_ok("router", router_bundle)
            router_bundles.append(router_bundle)
            worker_tasks = [
                dict(item)
                for item in (router_bundle.get("parsed_output", {}).get("worker_tasks") or [])
                if isinstance(item, dict)
            ]
            execution_record.router_run_path = _artifact_path(router_bundle)
            execution_record.task_ids = [
                str(item.get("task_id") or "").strip()
                for item in worker_tasks
                if str(item.get("task_id") or "").strip()
            ]
            execution_record.end_state_version = execution_record.start_state_version
            execution_record.status = "routed"
            manifest.hypothesis_runs.append(execution_record)

        manifest.status = "completed"
        manifest.terminal_reason = "stopped_after_router"
        manifest.end_state_version = manifest.start_state_version
        return {
            "analysis_bundle": analysis_bundle,
            "ranking_bundle": ranking_bundle,
            "planner_bundle": planner_bundle,
            "router_bundles": router_bundles,
            "worker_bundles": [],
            "aggregation_bundles": [],
            "state_manager_bundles": [],
            "critic_bundle": {},
            "global_aggregation_summary": {},
            "updated_batch_state": current_state,
            "frozen_snapshot": frozen_snapshot,
            "round_manifest": manifest,
            "terminal_reason": manifest.terminal_reason,
        }

    hypothesis_records: dict[str, HypothesisExecutionRecord] = {}
    hypothesis_future_order: list[str] = []
    hypothesis_aggregation_futures: dict[str, Future[dict[str, Any]]] = {}
    total_worker_capacity = max(
        1, len(planner_strategies) * max(1, max_tasks_per_hypothesis))
    worker_pool_size = _resolve_pool_size(
        max_concurrent_workers, fallback_size=total_worker_capacity)
    hypothesis_pool_size = _resolve_pool_size(
        max_concurrent_hypotheses, fallback_size=max(1, len(planner_strategies)))

    with ThreadPoolExecutor(max_workers=worker_pool_size, thread_name_prefix="phase3a-worker") as worker_executor, ThreadPoolExecutor(max_workers=hypothesis_pool_size, thread_name_prefix="phase3a-hypothesis") as hypothesis_executor:
        for planner_strategy in planner_strategies:
            hypothesis_id = str(planner_strategy.get(
                "hypothesis_id") or "").strip()
            execution_record = HypothesisExecutionRecord(
                hypothesis_id=hypothesis_id,
                planner_strategy_id=str(
                    planner_strategy.get("strategy_id") or "").strip(),
                start_state_version=manifest.start_state_version,
            )

            router_context_min = build_router_context(
                planner_round_context=planner_round_context,
                selected_hypothesis_context=selected_hypothesis_context,
                planner_strategy=planner_strategy,
                max_worker_steps=max_worker_steps,
                max_worker_retries=max_worker_retries,
                max_tasks_per_hypothesis=max_tasks_per_hypothesis,
            )
            router_bundle = run_router(
                planner_strategy,
                router_context_min,
                batch_id=batch_id,
                round_id=round_id,
                llm_callable=_llm_callable_for(llm_callables, "router"),
                model_name=model_name,
                temperature=temperature,
                caller_mode=caller_mode,
            )
            _require_component_ok("router", router_bundle)
            router_bundles.append(router_bundle)
            execution_record.router_run_path = _artifact_path(router_bundle)

            worker_tasks = [
                dict(item)
                for item in (router_bundle.get("parsed_output", {}).get("worker_tasks") or [])
                if isinstance(item, dict)
            ]
            execution_record.task_ids = [
                str(item.get("task_id") or "").strip()
                for item in worker_tasks
                if str(item.get("task_id") or "").strip()
            ]
            hypothesis_records[hypothesis_id] = execution_record
            hypothesis_future_order.append(hypothesis_id)

            if not worker_tasks:
                execution_record.end_state_version = execution_record.start_state_version
                execution_record.status = "no_tasks"
                continue

            worker_futures: list[Future[dict[str, Any]]] = []
            for worker_task in worker_tasks:
                worker_runtime_refs = build_worker_runtime_refs(
                    router_context_min=router_context_min,
                    semantic_substrate=semantic_substrate,
                    dataset_path=dataset_path,
                )
                worker_future = worker_executor.submit(
                    run_worker,
                    worker_task,
                    worker_runtime_refs,
                    batch_id=batch_id,
                    round_id=round_id,
                    llm_callable=_llm_callable_for(llm_callables, "worker"),
                    model_name=model_name,
                    temperature=temperature,
                    caller_mode=caller_mode,
                )
                worker_futures.append(worker_future)

            hypothesis_aggregation_futures[hypothesis_id] = hypothesis_executor.submit(
                _await_workers_and_run_aggregation,
                batch_id=batch_id,
                round_id=round_id,
                hypothesis_id=hypothesis_id,
                task_ids=execution_record.task_ids,
                worker_futures=worker_futures,
                llm_callables=llm_callables,
                model_name=model_name,
                temperature=temperature,
                caller_mode=caller_mode,
            )

        barrier_status(
            "round",
            expected=len(hypothesis_future_order),
            completed=0,
            waiting_for=list(hypothesis_future_order),
            batch_id=batch_id,
            round_id=round_id,
        )
        phase_message(
            "round", f"WAITING FOR {len(hypothesis_future_order)} HYPOTHESIS AGGREGATIONS", batch_id=batch_id, round_id=round_id)

        for hypothesis_id in hypothesis_future_order:
            execution_record = hypothesis_records[hypothesis_id]
            aggregation_future = hypothesis_aggregation_futures.get(
                hypothesis_id)
            if aggregation_future is None:
                manifest.hypothesis_runs.append(execution_record)
                continue

            aggregation_result = aggregation_future.result()
            hypothesis_worker_bundles = list(
                aggregation_result.get("worker_bundles", []))
            aggregation_bundle = dict(
                aggregation_result.get("aggregation_bundle", {}) or {})
            worker_bundles.extend(hypothesis_worker_bundles)
            worker_by_hypothesis_id[hypothesis_id] = hypothesis_worker_bundles
            aggregation_bundles.append(aggregation_bundle)
            aggregation_by_hypothesis_id[hypothesis_id] = aggregation_bundle
            execution_record.worker_run_paths = [
                _artifact_path(worker_bundle)
                for worker_bundle in hypothesis_worker_bundles
                if _artifact_path(worker_bundle)
            ]
            execution_record.aggregation_run_path = _artifact_path(
                aggregation_bundle)
            execution_record.status = "aggregated"
            manifest.hypothesis_runs.append(execution_record)

        barrier_status(
            "round",
            expected=len(hypothesis_future_order),
            completed=len(
                [record for record in manifest.hypothesis_runs if record.status != "no_tasks"]),
            waiting_for=[],
            batch_id=batch_id,
            round_id=round_id,
        )
        phase_message("round", "ALL HYPOTHESIS AGGREGATIONS COMPLETE",
                      batch_id=batch_id, round_id=round_id)

    global_aggregation_start = perf_counter()
    phase_start("inter_hypothesis_aggregation",
                batch_id=batch_id, round_id=round_id)
    inter_hypothesis_bundle = run_inter_hypothesis_aggregation(
        batch_id=batch_id,
        round_id=round_id,
        selected_hypothesis_ids=[
            record.hypothesis_id for record in manifest.hypothesis_runs if record.status != "no_tasks"],
        source_aggregation_bundles=aggregation_bundles,
        llm_callable=_llm_callable_for(
            llm_callables, "inter_hypothesis_aggregation"),
        model_name=model_name,
        temperature=temperature,
        caller_mode=caller_mode,
    )
    global_aggregation_summary = dict(
        inter_hypothesis_bundle.get("parsed_output", {}) or {})
    validation_result(
        "inter_hypothesis_aggregation",
        dict(global_aggregation_summary.get("validation_report", {}) or {}),
        batch_id=batch_id,
        round_id=round_id,
    )
    phase_end("inter_hypothesis_aggregation", elapsed_s=perf_counter() -
              global_aggregation_start, batch_id=batch_id, round_id=round_id)

    if inter_hypothesis_bundle.get("artifact_paths"):
        global_aggregation_path = str(
            inter_hypothesis_bundle["artifact_paths"].get(
                "parsed_output_path", "") or ""
        )
    else:
        global_aggregation_path = ""
    if global_aggregation_path:
        manifest.global_aggregation_path = global_aggregation_path

    state_manager_projections = build_state_manager_projections(
        global_aggregation_summary)
    projection_by_hypothesis_id = {
        str(dict(projection).get("hypothesis_id") or "").strip(): projection
        for projection in state_manager_projections
        if str(dict(projection).get("hypothesis_id") or "").strip()
    }

    if stop_after_phase == "aggregation":
        for execution_record in manifest.hypothesis_runs:
            if execution_record.status != "no_tasks":
                execution_record.end_state_version = execution_record.start_state_version
                execution_record.status = "aggregated"
        manifest.status = "completed"
        manifest.terminal_reason = "stopped_after_aggregation"
        manifest.end_state_version = manifest.start_state_version
        return {
            "analysis_bundle": analysis_bundle,
            "ranking_bundle": ranking_bundle,
            "planner_bundle": planner_bundle,
            "router_bundles": router_bundles,
            "worker_bundles": worker_bundles,
            "aggregation_bundles": aggregation_bundles,
            "state_manager_bundles": [],
            "critic_bundle": {},
            "global_aggregation_summary": global_aggregation_summary,
            "updated_batch_state": current_state,
            "frozen_snapshot": frozen_snapshot,
            "round_manifest": manifest,
            "terminal_reason": manifest.terminal_reason,
        }

    for execution_record in manifest.hypothesis_runs:
        if execution_record.status == "no_tasks":
            continue

        state_manager_projection = dict(
            projection_by_hypothesis_id.get(execution_record.hypothesis_id, {})
        )
        state_manager_bundle = run_state_manager(
            current_state,
            state_manager_projection,
            llm_callable=_llm_callable_for(llm_callables, "state_manager"),
            model_name=model_name,
            temperature=temperature,
            caller_mode=caller_mode,
            expected_prior_state_version=int(
                current_state.get("state_version") or 0),
            prior_state_origin="phase3a_runtime_round",
            prior_state_source={
                "batch_id": batch_id,
                "round_id": round_id,
                "round_index": round_index,
                "analysis_mode": analysis_mode,
                "global_aggregation_summary": global_aggregation_summary,
            },
        )
        _require_component_ok(
            "state_manager",
            state_manager_bundle,
            predicate=lambda payload: bool(
                dict(payload.get("component_run", {}) or {}).get(
                    "state_committed", False)
            ),
        )
        state_manager_bundles.append(state_manager_bundle)
        execution_record.state_manager_run_path = _artifact_path(
            state_manager_bundle)
        current_state = dict(state_manager_bundle.get(
            "updated_batch_state", {}) or {})
        execution_record.end_state_version = int(
            current_state.get("state_version") or 0)
        execution_record.status = "completed"

    if not state_manager_bundles:
        manifest.status = "terminated"
        manifest.terminal_reason = "no_state_updates"
        manifest.end_state_version = manifest.start_state_version
        return {
            "analysis_bundle": analysis_bundle,
            "ranking_bundle": ranking_bundle,
            "planner_bundle": planner_bundle,
            "router_bundles": router_bundles,
            "worker_bundles": worker_bundles,
            "aggregation_bundles": aggregation_bundles,
            "state_manager_bundles": state_manager_bundles,
            "critic_bundle": {},
            "global_aggregation_summary": global_aggregation_summary,
            "updated_batch_state": current_state,
            "frozen_snapshot": frozen_snapshot,
            "round_manifest": manifest,
            "terminal_reason": manifest.terminal_reason,
        }

    if enable_critic:
        selected_state_manager_bundle = state_manager_bundles[-1]
        selected_hypothesis_id = str(
            dict(selected_state_manager_bundle.get(
                "component_run", {}) or {}).get("hypothesis_id") or ""
        ).strip()
        critic_bundle = run_critic(
            selected_state_manager_bundle,
            llm_callable=_llm_callable_for(llm_callables, "critic"),
            model_name=model_name,
            temperature=temperature,
            caller_mode=caller_mode,
            is_final_round=is_final_round,
            round_component_bundles={
                "semantic_extraction": semantic_bundle,
                "investigation_analysis": analysis_bundle,
                "hypothesis_ranking": ranking_bundle,
                "planner": planner_bundle,
                "router": router_bundles,
                "aggregation": aggregation_bundles,
                "worker": worker_bundles,
            },
        )
        _require_component_ok("critic", critic_bundle)
        manifest.critic_run_path = _artifact_path(critic_bundle)

    manifest.status = "completed"
    manifest.end_state_version = int(current_state.get("state_version") or 0)
    phase_end("round", elapsed_s=perf_counter() - round_start_time,
              batch_id=batch_id, round_id=round_id)
    return {
        "analysis_bundle": analysis_bundle,
        "ranking_bundle": ranking_bundle,
        "planner_bundle": planner_bundle,
        "router_bundles": router_bundles,
        "worker_bundles": worker_bundles,
        "aggregation_bundles": aggregation_bundles,
        "state_manager_bundles": state_manager_bundles,
        "critic_bundle": critic_bundle,
        "global_aggregation_summary": global_aggregation_summary,
        "global_aggregation_bundle": inter_hypothesis_bundle,
        "updated_batch_state": current_state,
        "frozen_snapshot": frozen_snapshot,
        "round_manifest": manifest,
        "terminal_reason": "",
    }
