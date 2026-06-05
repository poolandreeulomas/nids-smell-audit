"""Resolve bounded Critic inputs from committed runtime artifacts."""

from __future__ import annotations

from typing import Any

from state.store import get_interpretive_hypothesis
from state_manager.state_loader import load_canonical_batch_state


_REF_KEYS = {
    "evidence_refs",
    "local_context_refs",
    "related_substrate_refs",
    "task_id",
    "task_ids",
    "context_ref",
    "call_id",
    "strategy_id",
    "planner_strategy_id",
}

_COMPONENT_ARTIFACT_PLAN = {
    "semantic_extraction": {
        "input_refs": [
            ("overview_summary_min_path", "overview_summary_min"),
            ("partition_context_path", "partition_context"),
        ],
        "output_refs": [("parsed_output_path", "semantic_substrate")],
        "signal_refs": [
            ("validation_report_path", "validation_report"),
            ("runtime_metrics_path", "runtime_metrics"),
        ],
    },
    "investigation_analysis": {
        "input_refs": [
            ("semantic_substrate_path", "semantic_substrate"),
            ("analysis_context_min_path", "analysis_context_min"),
            ("analysis_iteration_context_min_path",
             "analysis_iteration_context_min"),
        ],
        "output_refs": [
            ("parsed_output_path", "hypothesis_set"),
            ("hypothesis_index_path", "hypothesis_index"),
        ],
        "signal_refs": [
            ("validation_report_path", "validation_report"),
            ("runtime_metrics_path", "runtime_metrics"),
        ],
    },
    "hypothesis_ranking": {
        "input_refs": [
            ("candidate_hypotheses_path", "candidate_hypotheses"),
            ("ranking_state_snapshot_path", "ranking_state_snapshot"),
        ],
        "output_refs": [
            ("parsed_output_path", "ranking_output"),
            ("selection_index_path", "selection_index"),
        ],
        "signal_refs": [
            ("validation_report_path", "validation_report"),
            ("runtime_metrics_path", "runtime_metrics"),
        ],
    },
    "planner": {
        "input_refs": [
            ("ranking_decision_min_path", "ranking_decision_min"),
            ("selected_hypothesis_context_path", "selected_hypothesis_context"),
            ("planner_round_context_path", "planner_round_context"),
        ],
        "output_refs": [
            ("parsed_output_path", "planner_output"),
            ("strategy_index_path", "strategy_index"),
        ],
        "signal_refs": [
            ("validation_report_path", "validation_report"),
            ("runtime_metrics_path", "runtime_metrics"),
        ],
    },
    "router": {
        "input_refs": [
            ("planner_strategy_path", "planner_strategy"),
            ("router_context_min_path", "router_context_min"),
        ],
        "output_refs": [
            ("parsed_output_path", "router_output"),
            ("task_bundle_index_path", "task_bundle_index"),
        ],
        "signal_refs": [
            ("validation_report_path", "validation_report"),
            ("runtime_metrics_path", "runtime_metrics"),
        ],
    },
    "worker": {
        "input_refs": [
            ("worker_task_path", "worker_task"),
            ("worker_runtime_refs_path", "worker_runtime_refs"),
        ],
        "output_refs": [
            ("worker_result_path", "worker_result"),
            ("worker_output_path", "worker_output"),
        ],
        "signal_refs": [
            ("operational_trace_path", "operational_trace"),
            ("validation_report_path", "validation_report"),
            ("runtime_metrics_path", "runtime_metrics"),
        ],
    },
    "aggregation": {
        "input_refs": [
            ("worker_result_set_path", "worker_result_set"),
            ("normalized_inputs_path", "normalized_inputs"),
        ],
        "output_refs": [("aggregation_handoff_path", "aggregation_handoff")],
        "signal_refs": [
            ("overlap_diagnostics_path", "overlap_diagnostics"),
            ("validation_report_path", "validation_report"),
            ("runtime_metrics_path", "runtime_metrics"),
        ],
    },
}


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return list(dict.fromkeys(normalized))


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _artifact_ref(artifact_paths: dict[str, Any], key: str, fallback: str) -> str:
    value = str(artifact_paths.get(key, "") or "").strip()
    return value or fallback


def _bundle_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [dict(value)]
    return []


def _collect_nested_refs(value: Any, ref_keys: set[str], target: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ref_keys:
                if isinstance(item, str):
                    stripped = item.strip()
                    if stripped:
                        target.add(stripped)
                elif isinstance(item, list):
                    for nested in item:
                        if isinstance(nested, str) and nested.strip():
                            target.add(nested.strip())
            _collect_nested_refs(item, ref_keys, target)
        return

    if isinstance(value, list):
        for item in value:
            _collect_nested_refs(item, ref_keys, target)


def _collect_bundle_refs(*values: Any) -> list[str]:
    target: set[str] = set()
    for value in values:
        _collect_nested_refs(value, _REF_KEYS, target)
    return sorted(target)


def _base_warning_signals(component_run: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    status = str(component_run.get("status", "unknown") or "unknown")
    if status != "ok":
        warnings.append("status_not_ok")
    if not bool(component_run.get("validation_ok", False)):
        warnings.append("validation_failed")
    return warnings


def _build_artifact_ref_records(
    component_name: str,
    bundles: list[dict[str, Any]],
) -> list[dict[str, str]]:
    plan = _COMPONENT_ARTIFACT_PLAN.get(component_name, {})
    refs: list[dict[str, str]] = []
    total = len(bundles)
    for index, bundle in enumerate(bundles, start=1):
        artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
        suffix = f"[{index}]" if total > 1 else ""
        for path_key, artifact_kind in plan.get("input_refs", []):
            refs.append(
                {
                    "module_name": component_name,
                    "artifact_kind": f"input:{artifact_kind}{suffix}",
                    "artifact_ref": _artifact_ref(
                        artifact_paths,
                        path_key,
                        f"{component_name}.input.{artifact_kind}{suffix}",
                    ),
                }
            )
        for path_key, artifact_kind in plan.get("output_refs", []):
            refs.append(
                {
                    "module_name": component_name,
                    "artifact_kind": f"output:{artifact_kind}{suffix}",
                    "artifact_ref": _artifact_ref(
                        artifact_paths,
                        path_key,
                        f"{component_name}.output.{artifact_kind}{suffix}",
                    ),
                }
            )
    return refs


def _build_signal_ref_records(
    component_name: str,
    bundles: list[dict[str, Any]],
) -> list[dict[str, str]]:
    plan = _COMPONENT_ARTIFACT_PLAN.get(component_name, {})
    refs: list[dict[str, str]] = []
    total = len(bundles)
    for index, bundle in enumerate(bundles, start=1):
        artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
        suffix = f"[{index}]" if total > 1 else ""
        for path_key, signal_kind in plan.get("signal_refs", []):
            refs.append(
                {
                    "signal_name": f"{component_name}.{signal_kind}{suffix}",
                    "signal_ref": _artifact_ref(
                        artifact_paths,
                        path_key,
                        f"{component_name}.{signal_kind}{suffix}",
                    ),
                }
            )
    return refs


def _summary_refs(preferred_refs: list[str], fallback_refs: set[str]) -> list[str]:
    if preferred_refs:
        return preferred_refs
    return sorted(fallback_refs)


def _build_summary_entry(
    *,
    module_name: str,
    status: str,
    behavior_summary: str,
    evidence_refs: list[str],
    warning_signals: list[str],
) -> dict[str, Any]:
    return {
        "module_name": module_name,
        "status": status,
        "behavior_summary": behavior_summary,
        "evidence_refs": evidence_refs,
        "warning_signals": warning_signals,
    }


def _summarize_semantic_extraction(bundle: dict[str, Any], fallback_refs: set[str]) -> dict[str, Any]:
    component_run = dict(bundle.get("component_run", {}) or {})
    metrics = dict(bundle.get("runtime_metrics", {}) or {})
    bundle_refs = _collect_bundle_refs(bundle.get(
        "overview_summary_min"), bundle.get("parsed_output"))
    return _build_summary_entry(
        module_name="semantic_extraction",
        status=str(component_run.get("status", "unknown") or "unknown"),
        behavior_summary=(
            "Input: "
            f"{_int_value(metrics.get('evidence_count'))} overview evidence items and partition context. "
            "Output: "
            f"{_int_value(metrics.get('region_count'))} compressed regions, "
            f"{_int_value(metrics.get('weak_signal_count'))} weak signals, "
            f"{_int_value(metrics.get('contradiction_count'))} contradictions, "
            f"and {_int_value(metrics.get('tension_count'))} unresolved tensions."
        ),
        evidence_refs=_summary_refs(bundle_refs, fallback_refs),
        warning_signals=_base_warning_signals(component_run),
    )


def _summarize_investigation_analysis(bundle: dict[str, Any], fallback_refs: set[str]) -> dict[str, Any]:
    component_run = dict(bundle.get("component_run", {}) or {})
    metrics = dict(bundle.get("runtime_metrics", {}) or {})
    bundle_refs = _collect_bundle_refs(
        bundle.get("analysis_context_min"),
        bundle.get("analysis_iteration_context_min"),
        bundle.get("parsed_output"),
    )
    return _build_summary_entry(
        module_name="investigation_analysis",
        status=str(component_run.get("status", "unknown") or "unknown"),
        behavior_summary=(
            "Input: semantic substrate plus analysis context. Output: "
            f"{_int_value(metrics.get('hypothesis_count'))} hypotheses for the current batch interpretation."
        ),
        evidence_refs=_summary_refs(bundle_refs, fallback_refs),
        warning_signals=_base_warning_signals(component_run),
    )


def _summarize_hypothesis_ranking(bundle: dict[str, Any], fallback_refs: set[str]) -> dict[str, Any]:
    component_run = dict(bundle.get("component_run", {}) or {})
    metrics = dict(bundle.get("runtime_metrics", {}) or {})
    bundle_refs = _collect_bundle_refs(
        bundle.get("candidate_hypotheses"),
        bundle.get("parsed_output"),
        bundle.get("selection_index"),
    )
    return _build_summary_entry(
        module_name="hypothesis_ranking",
        status=str(component_run.get("status", "unknown") or "unknown"),
        behavior_summary=(
            "Input: "
            f"{_int_value(metrics.get('candidate_count'))} candidate hypotheses and ranking state. "
            "Output: "
            f"{_int_value(metrics.get('selected_count'))} selected hypotheses for round {component_run.get('round_id', 'unknown')}."
        ),
        evidence_refs=_summary_refs(bundle_refs, fallback_refs),
        warning_signals=_base_warning_signals(component_run),
    )


def _summarize_planner(bundle: dict[str, Any], fallback_refs: set[str]) -> dict[str, Any]:
    component_run = dict(bundle.get("component_run", {}) or {})
    metrics = dict(bundle.get("runtime_metrics", {}) or {})
    bundle_refs = _collect_bundle_refs(
        bundle.get("selected_hypothesis_context"),
        bundle.get("parsed_output"),
        bundle.get("strategy_index"),
    )
    warning_signals = _base_warning_signals(component_run)
    if _int_value(metrics.get("strategy_count")) == 0:
        warning_signals.append("no_strategies_produced")
    return _build_summary_entry(
        module_name="planner",
        status=str(component_run.get("status", "unknown") or "unknown"),
        behavior_summary=(
            "Input: "
            f"{_int_value(metrics.get('selected_count'))} selected hypotheses and "
            f"{_int_value(metrics.get('tool_capability_ref_count'))} tool capability refs. "
            "Output: "
            f"{_int_value(metrics.get('strategy_count'))} planner strategies."
        ),
        evidence_refs=_summary_refs(bundle_refs, fallback_refs),
        warning_signals=warning_signals,
    )


def _summarize_router(bundles: list[dict[str, Any]], fallback_refs: set[str]) -> dict[str, Any]:
    warning_signals: list[str] = []
    task_count = 0
    known_refs: set[str] = set()
    hypothesis_ids: list[str] = []
    status = "ok"

    for bundle in bundles:
        component_run = dict(bundle.get("component_run", {}) or {})
        metrics = dict(bundle.get("runtime_metrics", {}) or {})
        task_count += _int_value(metrics.get("task_count"))
        hypothesis_id = str(component_run.get("hypothesis_id") or "").strip()
        if hypothesis_id:
            hypothesis_ids.append(hypothesis_id)
        bundle_status = str(component_run.get(
            "status", "unknown") or "unknown")
        if bundle_status != "ok":
            status = "mixed"
        warning_signals.extend(_base_warning_signals(component_run))
        if _int_value(metrics.get("task_count")) == 0:
            warning_signals.append("no_worker_tasks_produced")
        known_refs.update(
            _collect_bundle_refs(
                bundle.get("planner_strategy"),
                bundle.get("router_context_min"),
                bundle.get("parsed_output"),
                bundle.get("task_bundle_index"),
            )
        )

    return _build_summary_entry(
        module_name="router",
        status=status,
        behavior_summary=(
            "Input: planner strategies for "
            f"{len(hypothesis_ids)} hypotheses. Output: "
            f"{task_count} worker tasks across hypotheses {', '.join(hypothesis_ids[:4]) or 'none'}."
        ),
        evidence_refs=_summary_refs(sorted(known_refs), fallback_refs),
        warning_signals=sorted(set(warning_signals)),
    )


def _summarize_worker(bundles: list[dict[str, Any]], fallback_refs: set[str]) -> dict[str, Any]:
    component_runs = [dict(bundle.get("component_run", {}) or {})
                      for bundle in bundles]
    metrics_list = [dict(bundle.get("runtime_metrics", {}) or {})
                    for bundle in bundles]
    warning_signals: list[str] = []
    task_ids: list[str] = []
    known_refs: set[str] = set()
    committed_count = 0
    tool_event_count = 0
    failure_event_count = 0
    termination_causes: set[str] = set()

    for bundle, component_run, metrics in zip(bundles, component_runs, metrics_list):
        task_id = str(component_run.get("task_id", "") or "").strip()
        if task_id:
            task_ids.append(task_id)
        if bool(component_run.get("result_committed", False)):
            committed_count += 1
        tool_event_count += _int_value(metrics.get("tool_event_count"))
        failure_event_count += _int_value(metrics.get("failure_event_count"))
        termination_cause = str(metrics.get(
            "termination_cause", "") or "").strip()
        if termination_cause:
            termination_causes.add(termination_cause)
        warning_signals.extend(_base_warning_signals(component_run))
        if _int_value(metrics.get("failure_event_count")) > 0:
            warning_signals.append("failure_events_present")
        if not bool(component_run.get("result_committed", False)):
            warning_signals.append("result_not_committed")
        known_refs.update(
            _collect_bundle_refs(
                bundle.get("worker_task"),
                bundle.get("worker_runtime_refs"),
                bundle.get("worker_result"),
                bundle.get("worker_output"),
                bundle.get("operational_trace"),
            )
        )

    return _build_summary_entry(
        module_name="worker",
        status="ok" if committed_count == len(
            bundles) and bundles else "mixed",
        behavior_summary=(
            "Input: "
            f"{len(bundles)} worker tasks ({', '.join(task_ids[:3]) or 'no task ids'}). "
            "Output: "
            f"{committed_count} committed worker results, {tool_event_count} tool events, "
            f"and {failure_event_count} failure events. "
            f"Termination causes: {', '.join(sorted(termination_causes)[:3]) or 'none'}."
        ),
        evidence_refs=_summary_refs(sorted(known_refs), fallback_refs),
        warning_signals=sorted(set(warning_signals)),
    )


def _summarize_aggregation_bundle(bundles: list[dict[str, Any]], fallback_refs: set[str]) -> dict[str, Any]:
    warning_signals: list[str] = []
    known_refs: set[str] = set()
    total_worker_results = 0
    total_overlap_diagnostics = 0
    total_merged_findings = 0
    total_contradictions = 0
    total_open_gaps = 0
    status = "ok"

    for bundle in bundles:
        component_run = dict(bundle.get("component_run", {}) or {})
        worker_result_set = dict(bundle.get("worker_result_set", {}) or {})
        aggregation_handoff = dict(bundle.get("aggregation_handoff", {}) or {})
        bundle_status = str(component_run.get(
            "status", "unknown") or "unknown")
        if bundle_status != "ok":
            status = "mixed"
        warning_signals.extend(_base_warning_signals(component_run))
        if _string_list(aggregation_handoff.get("preserved_contradictions")):
            warning_signals.append("contradictions_preserved")
        if _string_list(aggregation_handoff.get("open_gaps")):
            warning_signals.append("open_gaps_remain")
        if not bool(component_run.get("handoff_committed", False)):
            warning_signals.append("handoff_not_committed")
        total_worker_results += len(worker_result_set.get("worker_results", []))
        total_overlap_diagnostics += len(bundle.get("overlap_diagnostics", []))
        total_merged_findings += len(_string_list(
            aggregation_handoff.get("merged_findings")))
        total_contradictions += len(_string_list(
            aggregation_handoff.get("preserved_contradictions")))
        total_open_gaps += len(_string_list(aggregation_handoff.get("open_gaps")))
        known_refs.update(
            _collect_bundle_refs(
                worker_result_set,
                aggregation_handoff,
                bundle.get("parsed_output"),
            )
        )

    return _build_summary_entry(
        module_name="aggregation",
        status=status,
        behavior_summary=(
            "Input: "
            f"{total_worker_results} worker results and {total_overlap_diagnostics} overlap diagnostics across hypotheses. "
            "Output: "
            f"{total_merged_findings} merged findings, {total_contradictions} preserved contradictions, "
            f"and {total_open_gaps} open gaps."
        ),
        evidence_refs=_summary_refs(sorted(known_refs), fallback_refs),
        warning_signals=sorted(set(warning_signals)),
    )


def _summarize_aggregation_fallback(
    artifact_paths: dict[str, Any],
    aggregation_handoff: dict[str, Any],
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    fallback_refs: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    warning_signals: list[str] = []
    if _string_list(aggregation_handoff.get("preserved_contradictions")):
        warning_signals.append("contradictions_preserved")
    if _string_list(aggregation_handoff.get("open_gaps")):
        warning_signals.append("open_gaps_remain")
    return (
        [
            {
                "module_name": "aggregation",
                "artifact_kind": "output:aggregation_handoff",
                "artifact_ref": _artifact_ref(
                    artifact_paths,
                    "aggregation_handoff_path",
                    "aggregation.aggregation_handoff",
                ),
            }
        ],
        [
            {
                "signal_name": "aggregation.aggregation_handoff",
                "signal_ref": _artifact_ref(
                    artifact_paths,
                    "aggregation_handoff_path",
                    "aggregation.aggregation_handoff",
                ),
            }
        ],
        _build_summary_entry(
            module_name="aggregation",
            status="ok" if aggregation_handoff else "missing",
            behavior_summary=(
                "Input: committed worker synthesis for the selected hypothesis. Output: "
                f"{len(_string_list(aggregation_handoff.get('merged_findings')))} merged findings, "
                f"{len(_string_list(aggregation_handoff.get('preserved_contradictions')))} preserved contradictions, "
                f"and {len(_string_list(aggregation_handoff.get('open_gaps')))} open gaps for hypothesis {hypothesis_id}."
            ),
            evidence_refs=_summary_refs(
                _collect_bundle_refs(aggregation_handoff),
                fallback_refs,
            ),
            warning_signals=warning_signals,
        ),
    )


def _summarize_state_manager(raw: dict[str, Any], fallback_refs: set[str]) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    artifact_paths = dict(raw.get("artifact_paths", {}) or {})
    component_run = dict(raw.get("component_run", {}) or {})
    state_manager_context = dict(raw.get("state_manager_context", {}) or {})
    state_update_result = dict(raw.get("state_update_result", {}) or {})
    runtime_metrics = dict(raw.get("runtime_metrics", {}) or {})
    prior_state = dict(raw.get("prior_state", {}) or {})

    warning_signals = _base_warning_signals(component_run)
    if not bool(component_run.get("state_committed", False)):
        warning_signals.append("state_not_committed")
    if _int_value(runtime_metrics.get("remaining_open_gap_count")) > 0:
        warning_signals.append("open_gaps_remain")

    artifact_refs = [
        {
            "module_name": "state_manager",
            "artifact_kind": "input:prior_state",
            "artifact_ref": _artifact_ref(
                artifact_paths,
                "prior_state_path",
                "state_manager.prior_state",
            ),
        },
        {
            "module_name": "state_manager",
            "artifact_kind": "input:aggregation_handoff",
            "artifact_ref": _artifact_ref(
                artifact_paths,
                "aggregation_handoff_path",
                "state_manager.aggregation_handoff",
            ),
        },
        {
            "module_name": "state_manager",
            "artifact_kind": "input:state_manager_context",
            "artifact_ref": _artifact_ref(
                artifact_paths,
                "state_manager_context_path",
                "state_manager.state_manager_context",
            ),
        },
        {
            "module_name": "state_manager",
            "artifact_kind": "output:updated_batch_state",
            "artifact_ref": _artifact_ref(
                artifact_paths,
                "updated_batch_state_path",
                "state_manager.updated_batch_state",
            ),
        },
        {
            "module_name": "state_manager",
            "artifact_kind": "output:state_update_result",
            "artifact_ref": _artifact_ref(
                artifact_paths,
                "state_update_result_path",
                "state_manager.state_update_result",
            ),
        },
    ]
    signal_refs = [
        {
            "signal_name": "state_manager.validation_report",
            "signal_ref": _artifact_ref(
                artifact_paths,
                "validation_report_path",
                "state_manager.validation_report",
            ),
        },
        {
            "signal_name": "state_manager.runtime_metrics",
            "signal_ref": _artifact_ref(
                artifact_paths,
                "runtime_metrics_path",
                "state_manager.runtime_metrics",
            ),
        },
        {
            "signal_name": "state_manager.replay_metadata",
            "signal_ref": _artifact_ref(
                artifact_paths,
                "replay_metadata_path",
                "state_manager.replay_metadata",
            ),
        },
    ]
    summary = _build_summary_entry(
        module_name="state_manager",
        status=str(component_run.get("status", "unknown") or "unknown"),
        behavior_summary=(
            "Input: state version "
            f"{prior_state.get('state_version', component_run.get('previous_state_version', 'unknown'))} "
            f"plus aggregation handoff for hypothesis {component_run.get('hypothesis_id', 'unknown')}. "
            "Output: state version "
            f"{component_run.get('previous_state_version', 'unknown')}"
            f"->{component_run.get('new_state_version', 'unknown')}, "
            f"{len(state_update_result.get('applied_updates', []))} applied updates, "
            f"and {len(state_update_result.get('remaining_open_gaps', []))} remaining open gaps."
        ),
        evidence_refs=_summary_refs(
            _collect_bundle_refs(state_manager_context, raw.get(
                "updated_batch_state"), state_update_result),
            fallback_refs,
        ),
        warning_signals=sorted(set(warning_signals)),
    )
    return artifact_refs, signal_refs, summary


# Mirrors semantic_extraction.contracts.VALID_REGION_KINDS
_VALID_REGION_KINDS = {
    "redundancy_region",
    "dependency_region",
    "concentration_region",
    "low_diversity_region",
    "localized_separability_region",
    "representation_sensitive_region",
    "topology_motif_region",
    "mixed_structural_region",
}


def _project_semantic_landscape(structural_substrate: dict[str, Any]) -> dict[str, Any]:
    """Return compressed regions only: region_id, kind, status."""
    raw = structural_substrate if isinstance(structural_substrate, dict) else {}
    compressed: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in raw.get("compressed_regions", []):
        if not isinstance(item, dict):
            continue
        region_id = str(item.get("region_id", "") or "").strip()
        if not region_id or region_id in seen_ids:
            continue
        seen_ids.add(region_id)
        kind = str(item.get("region_kind", "") or "").strip()
        if kind not in _VALID_REGION_KINDS:
            kind = "mixed_structural_region"
        status = str(item.get("status", "") or "").strip() or "unresolved"
        compressed.append({
            "region_id": region_id,
            "kind": kind,
            "status": status,
        })
    return {"regions": compressed}


def _earliest_revision_round(state: Any, hypothesis_id: str) -> str:
    if not hasattr(state, "revision_log"):
        return ""
    for entry in getattr(state, "revision_log", []) or []:
        if getattr(entry, "hypothesis_id", "") == hypothesis_id and getattr(entry, "round_id", ""):
            return str(getattr(entry, "round_id", "") or "")
    return ""


def _ranking_snapshot(
    round_id: str,
    round_component_bundles: dict[str, Any] | None,
    fallback_ids: list[str],
) -> tuple[list[str], list[str]]:
    raw = round_component_bundles if isinstance(
        round_component_bundles, dict) else {}
    ranking_bundle = raw.get("hypothesis_ranking", {}) if isinstance(
        raw.get("hypothesis_ranking", {}), dict) else {}
    candidate_source = ranking_bundle.get("candidate_hypotheses", {}) if isinstance(
        ranking_bundle.get("candidate_hypotheses", {}), dict) else {}
    parsed_output = ranking_bundle.get("parsed_output", {}) if isinstance(
        ranking_bundle.get("parsed_output", {}), dict) else {}
    selection_index = ranking_bundle.get("selection_index", {}) if isinstance(
        ranking_bundle.get("selection_index", {}), dict) else {}

    candidate_hypothesis_ids = [
        str(item.get("hypothesis_id", "") or "").strip()
        for item in candidate_source.get("candidate_hypotheses", [])
        if isinstance(item, dict) and str(item.get("hypothesis_id", "") or "").strip()
    ]
    if not candidate_hypothesis_ids:
        candidate_hypothesis_ids = [
            hypothesis_id for hypothesis_id in fallback_ids if hypothesis_id]

    selected_hypothesis_ids = [
        str(item.get("hypothesis_id", "") or "").strip()
        for item in parsed_output.get("selected_hypotheses", [])
        if isinstance(item, dict) and str(item.get("hypothesis_id", "") or "").strip()
    ]
    if not selected_hypothesis_ids:
        selected_hypothesis_ids = _string_list(
            parsed_output.get("selected_hypothesis_ids"))
    if not selected_hypothesis_ids:
        selected_hypothesis_ids = _string_list(
            selection_index.get("selected_hypothesis_ids"))
    if not selected_hypothesis_ids:
        selected_hypothesis_ids = [
            hypothesis_id for hypothesis_id in candidate_hypothesis_ids[:1]]

    return candidate_hypothesis_ids, selected_hypothesis_ids


def _truncate_summary(summary: str, max_chars: int = 200) -> str:
    stripped = str(summary or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars - 1].rsplit(" ", 1)[0] + "…"


def _build_hypothesis_universe(
    state: Any,
    batch_id: str,
) -> list[dict[str, Any]]:
    """Lightweight registry: hypothesis_id, status, one_line_summary only."""
    hypotheses: list[dict[str, Any]] = []
    if not hasattr(state, "interpretive_hypotheses"):
        return hypotheses

    for hypothesis in getattr(state, "interpretive_hypotheses", []) or []:
        if not hasattr(hypothesis, "to_dict"):
            continue
        hypothesis_dict = hypothesis.to_dict()
        hypothesis_id = str(hypothesis_dict.get("hypothesis_id", "") or "").strip()
        if not hypothesis_id:
            continue
        hypotheses.append({
            "hypothesis_id": hypothesis_id,
            "status": str(hypothesis_dict.get("status", "unresolved") or "unresolved"),
            "one_line_summary": _truncate_summary(
                str(hypothesis_dict.get("summary", "") or ""), 200),
        })
    return hypotheses


def _build_active_hypothesis_gaps(state: Any) -> list[dict[str, Any]]:
    """Only hypothesis_id + open_gaps for active (non-resolved) hypotheses."""
    active_gaps: list[dict[str, Any]] = []
    if not hasattr(state, "interpretive_hypotheses"):
        return active_gaps

    for hypothesis in getattr(state, "interpretive_hypotheses", []) or []:
        if not hasattr(hypothesis, "to_dict"):
            continue
        hypothesis_dict = hypothesis.to_dict()
        hypothesis_id = str(hypothesis_dict.get("hypothesis_id", "") or "").strip()
        if not hypothesis_id:
            continue
        status = str(hypothesis_dict.get("status", "") or "").lower().strip()
        # Only include gaps for non-resolved hypotheses
        if status in ("resolved", "confirmed", "refuted", "dismissed", "closed"):
            continue
        open_gaps = _string_list(hypothesis_dict.get("open_gaps"))
        if not open_gaps:
            continue
        active_gaps.append({
            "hypothesis_id": hypothesis_id,
            "open_gaps": open_gaps,
        })
    return active_gaps


def _build_investigation_history(
    *,
    round_id: str,
    selected_hypothesis_ids: list[str],
    state_manager_bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    component_run = dict(state_manager_bundle.get("component_run", {}) or {})
    start_state_version = _int_value(
        component_run.get("previous_state_version"), default=0)
    end_state_version = _int_value(
        component_run.get("new_state_version"), default=0)
    if end_state_version == 0:
        end_state_version = _int_value(dict(state_manager_bundle.get(
            "updated_batch_state", {}) or {}).get("state_version"), default=0)
    return [
        {
            "round_id": round_id,
            "selected_hypothesis_ids": list(selected_hypothesis_ids),
            "state_version_start": start_state_version,
            "state_version_end": end_state_version,
        }
    ]


def _build_investigation_outcomes(
    *,
    round_id: str,
    selected_hypothesis_ids: list[str],
    state: Any,
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    if not hasattr(state, "interpretive_hypotheses"):
        return outcomes

    by_id = {
        str(hypothesis.to_dict().get("hypothesis_id", "") or "").strip(): hypothesis.to_dict()
        for hypothesis in getattr(state, "interpretive_hypotheses", []) or []
        if hasattr(hypothesis, "to_dict") and str(hypothesis.to_dict().get("hypothesis_id", "") or "").strip()
    }
    for hypothesis_id in selected_hypothesis_ids:
        hypothesis_dict = by_id.get(hypothesis_id, {})
        if not hypothesis_dict:
            continue
        outcomes.append(
            {
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "revision_delta": _int_value(hypothesis_dict.get("revision_count"), default=0),
                "new_findings_count": len(_string_list(hypothesis_dict.get("merged_findings"))),
                "resolved_gaps_count": 0,
                "state_change_summary": str(hypothesis_dict.get("summary", "") or ""),
            }
        )
    return outcomes


def build_critic_context(
    state_manager_bundle: dict[str, Any],
    *,
    is_final_round: bool = False,
    round_component_bundles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = state_manager_bundle if isinstance(
        state_manager_bundle, dict) else {}
    artifact_paths = dict(raw.get("artifact_paths", {}) or {})
    component_run = dict(raw.get("component_run", {}) or {})
    aggregation_handoff = dict(raw.get("aggregation_handoff", {}) or {})
    state_manager_context = dict(raw.get("state_manager_context", {}) or {})
    updated_batch_state = dict(raw.get("updated_batch_state", {}) or {})
    state_update_result = dict(raw.get("state_update_result", {}) or {})
    runtime_metrics = dict(raw.get("runtime_metrics", {}) or {})

    batch_id = str(
        component_run.get("batch_id")
        or updated_batch_state.get("batch_id")
        or aggregation_handoff.get("batch_id")
        or "unknown_batch"
    ).strip() or "unknown_batch"
    round_id = str(
        component_run.get("round_id")
        or aggregation_handoff.get("round_id")
        or "unknown_round"
    ).strip() or "unknown_round"
    hypothesis_id = str(
        component_run.get("hypothesis_id")
        or state_update_result.get("hypothesis_id")
        or aggregation_handoff.get("hypothesis_id")
        or "unknown_hypothesis"
    ).strip() or "unknown_hypothesis"

    target_hypothesis: dict[str, Any] = dict(
        state_manager_context.get("target_hypothesis", {}) or {})
    state_version = _int_value(
        updated_batch_state.get("state_version"), default=0)
    canonical_state = None
    if updated_batch_state:
        try:
            canonical_state = load_canonical_batch_state(updated_batch_state)
            state_version = canonical_state.state_version
            resolved_hypothesis = get_interpretive_hypothesis(
                canonical_state, hypothesis_id)
            if resolved_hypothesis is not None:
                target_hypothesis = resolved_hypothesis.to_dict()
        except Exception:
            pass
    if canonical_state is None:
        try:
            canonical_state = load_canonical_batch_state(
                raw.get("updated_batch_state", {}))
        except Exception:
            canonical_state = None

    known_evidence_refs = set(_string_list(
        target_hypothesis.get("evidence_refs")))
    known_evidence_refs.update(_string_list(
        aggregation_handoff.get("evidence_refs")))

    normalized_component_bundles: dict[str, list[dict[str, Any]]] = {}
    raw_component_bundles = round_component_bundles if isinstance(
        round_component_bundles, dict) else {}
    for component_name, value in raw_component_bundles.items():
        bundles = _bundle_list(value)
        if bundles:
            normalized_component_bundles[str(component_name).strip()] = bundles

    for component_name, bundles in normalized_component_bundles.items():
        for bundle in bundles:
            known_evidence_refs.update(_collect_bundle_refs(bundle))

    module_artifact_refs: list[dict[str, str]] = []
    process_signal_refs: list[dict[str, str]] = []
    module_behavior_summaries: list[dict[str, Any]] = []
    warning_codes: set[str] = set()

    summary_builders = [
        ("semantic_extraction", _summarize_semantic_extraction),
        ("investigation_analysis", _summarize_investigation_analysis),
        ("hypothesis_ranking", _summarize_hypothesis_ranking),
        ("planner", _summarize_planner),
        ("router", _summarize_router),
    ]
    for component_name, builder in summary_builders:
        bundles = normalized_component_bundles.get(component_name, [])
        if not bundles:
            continue
        module_artifact_refs.extend(
            _build_artifact_ref_records(component_name, bundles))
        process_signal_refs.extend(
            _build_signal_ref_records(component_name, bundles))
        summary = builder(bundles, known_evidence_refs) if component_name == "router" else builder(
            bundles[0], known_evidence_refs)
        module_behavior_summaries.append(summary)
        warning_codes.update(summary.get("warning_signals", []))

    worker_bundles = normalized_component_bundles.get("worker", [])
    if worker_bundles:
        module_artifact_refs.extend(
            _build_artifact_ref_records("worker", worker_bundles))
        process_signal_refs.extend(
            _build_signal_ref_records("worker", worker_bundles))
        worker_summary = _summarize_worker(worker_bundles, known_evidence_refs)
        module_behavior_summaries.append(worker_summary)
        warning_codes.update(worker_summary.get("warning_signals", []))

    aggregation_bundles = normalized_component_bundles.get("aggregation", [])
    if aggregation_bundles:
        module_artifact_refs.extend(_build_artifact_ref_records(
            "aggregation", aggregation_bundles))
        process_signal_refs.extend(_build_signal_ref_records(
            "aggregation", aggregation_bundles))
        aggregation_summary = _summarize_aggregation_bundle(
            aggregation_bundles, known_evidence_refs)
        module_behavior_summaries.append(aggregation_summary)
        warning_codes.update(aggregation_summary.get("warning_signals", []))
    else:
        fallback_artifact_refs, fallback_signal_refs, fallback_summary = _summarize_aggregation_fallback(
            artifact_paths,
            aggregation_handoff,
            batch_id,
            round_id,
            hypothesis_id,
            known_evidence_refs,
        )
        module_artifact_refs.extend(fallback_artifact_refs)
        process_signal_refs.extend(fallback_signal_refs)
        module_behavior_summaries.append(fallback_summary)
        warning_codes.update(fallback_summary.get("warning_signals", []))

    state_manager_artifact_refs, state_manager_signal_refs, state_manager_summary = _summarize_state_manager(
        raw,
        known_evidence_refs,
    )
    module_artifact_refs.extend(state_manager_artifact_refs)
    process_signal_refs.extend(state_manager_signal_refs)
    module_behavior_summaries.append(state_manager_summary)
    warning_codes.update(state_manager_summary.get("warning_signals", []))

    aggregation_evidence_refs = _string_list(
        aggregation_handoff.get("evidence_refs"))
    refined_state_summary = {
        "batch_id": batch_id,
        "round_id": round_id,
        "hypothesis_id": hypothesis_id,
        "state_version": state_version,
        "summary": str(target_hypothesis.get("summary", "") or ""),
        "status": str(target_hypothesis.get("status", "unresolved") or "unresolved"),
        "evidence_refs": _string_list(target_hypothesis.get("evidence_refs"))
        or aggregation_evidence_refs,
        "open_gaps": _string_list(target_hypothesis.get("open_gaps"))[:5],
        "preserved_contradictions": _string_list(
            target_hypothesis.get("preserved_contradictions")
        )[:5],
        "merged_findings": _string_list(target_hypothesis.get("merged_findings"))[:5],
        "last_updated_round": str(target_hypothesis.get("last_updated_round", "") or ""),
    }

    process_signal_summary = {
        "batch_id": batch_id,
        "round_id": round_id,
        "is_final_round": bool(is_final_round),
        "state_committed": bool(component_run.get("state_committed", False)),
        "validation_ok": bool(component_run.get("validation_ok", False)),
        "applied_update_count": len(state_update_result.get("applied_updates", [])),
        "remaining_open_gap_count": len(state_update_result.get("remaining_open_gaps", [])),
        "warning_codes": sorted(warning_codes),
    }

    if canonical_state is None:
        canonical_state = load_canonical_batch_state(updated_batch_state)

    semantic_landscape_summary = _project_semantic_landscape(
        dict(canonical_state.structural_substrate)) if canonical_state is not None else {"regions": []}
    hypothesis_universe = _build_hypothesis_universe(
        canonical_state, batch_id) if canonical_state is not None else []

    candidate_hypothesis_ids, selected_hypothesis_ids = _ranking_snapshot(
        round_id,
        raw_component_bundles,
        [item.get("hypothesis_id", "") for item in hypothesis_universe],
    )
    investigation_history = _build_investigation_history(
        round_id=round_id,
        selected_hypothesis_ids=selected_hypothesis_ids,
        state_manager_bundle=raw,
    )
    ranking_history = [
        {
            "round_id": round_id,
            "candidate_hypothesis_ids": list(candidate_hypothesis_ids),
            "selected_hypothesis_ids": list(selected_hypothesis_ids),
        }
    ]
    investigation_outcomes = _build_investigation_outcomes(
        round_id=round_id,
        selected_hypothesis_ids=selected_hypothesis_ids,
        state=canonical_state,
    )
    active_hypothesis_gaps = _build_active_hypothesis_gaps(
        canonical_state) if canonical_state is not None else []

    critic_input_min = {
        "batch_id": batch_id,
        "round_id": round_id,
    }

    return {
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
        "known_evidence_refs": sorted(known_evidence_refs),
        "source_state_manager_run_path": str(artifact_paths.get("component_run_path", "") or ""),
    }
