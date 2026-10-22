"""Resolve round-level report inputs from round artifacts and canonical state.

Follows the architectural conventions of Phase3/final_batch_report/input_resolver.py.
Distinguishes evidence generated in this round from evidence accumulated in previous rounds.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

from data.dataset_config import DatasetConfig, get_default_dataset_config
from final_batch_report.contracts import PARTITION_SCENARIOS
from final_batch_report.input_resolver import (
    build_intended_behavioral_scenario,
    build_partition_audit_context,
)
from final_batch_report.round_contracts import (
    ROUND_REPORT_PROMPT_VERSION,
    ROUND_REPORT_SCHEMA_VERSION,
)
from state.schema import CanonicalBatchState, InterpretiveHypothesis, StateRevisionRecord
from utils.run_logging import load_json

logger = logging.getLogger(__name__)

_INTERNAL_ID_RE = re.compile(
    r"\b(?:e\d+|region_\d+|task_\d+_step_\d+)\b",
    re.IGNORECASE,
)


def _strip_internal_ids(text: str) -> str:
    cleaned = _INTERNAL_ID_RE.sub("[ref]", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


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


def _to_manifest_dict(
    round_manifest: Any,
) -> dict[str, Any]:
    if hasattr(round_manifest, "to_dict"):
        return round_manifest.to_dict()
    return dict(round_manifest or {})


def _load_optional_json(path_str: str | Path | None) -> dict[str, Any]:
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.is_file():
        return {}
    try:
        data = load_json(path)
        return dict(data) if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load JSON from %s: %exc", path, exc)
        return {}


def _resolve_round_canonical_state(
    canonical_state: CanonicalBatchState | dict[str, Any] | None,
    manifest_dict: dict[str, Any],
) -> CanonicalBatchState:
    if isinstance(canonical_state, CanonicalBatchState):
        return canonical_state
    if isinstance(canonical_state, dict) and canonical_state:
        return CanonicalBatchState.from_dict(canonical_state)

    # Attempt to load state from last state manager run path if available
    hypothesis_runs = list(manifest_dict.get("hypothesis_runs", []) or [])
    for rec in reversed(hypothesis_runs):
        sm_path = str(rec.get("state_manager_run_path", "") or "").strip()
        if sm_path:
            sm_data = _load_optional_json(sm_path)
            state_data = sm_data.get("updated_batch_state")
            if isinstance(state_data, dict) and state_data:
                return CanonicalBatchState.from_dict(state_data)
            # Try component run directory
            state_file = Path(sm_path).parent / "updated_batch_state.json"
            if state_file.is_file():
                return CanonicalBatchState.from_dict(_load_optional_json(state_file))

    return CanonicalBatchState(batch_id=str(manifest_dict.get("batch_id") or "unknown_batch"))


def resolve_round_report_context(
    *,
    round_manifest: RoundManifest | dict[str, Any],
    frozen_snapshot: dict[str, Any] | None = None,
    canonical_state: CanonicalBatchState | dict[str, Any] | None = None,
    dataset_path: str | Path | None = None,
    dataset_config: DatasetConfig | None = None,
    round_bundles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Master resolver constructing structured evidence for one Phase 3A round.

    Distinguishes new evidence produced in this round from inherited prior evidence.
    """
    manifest_dict = _to_manifest_dict(round_manifest)
    round_id = str(manifest_dict.get("round_id") or "round-001").strip()
    round_index = int(manifest_dict.get("round_index", 0) or 0)
    analysis_mode = str(manifest_dict.get("analysis_mode", "initial") or "initial")
    round_status = str(manifest_dict.get("status", "unknown") or "unknown")
    terminal_reason = str(manifest_dict.get("terminal_reason", "") or "")
    start_state_version = int(manifest_dict.get("start_state_version", 0) or 0)
    end_state_version = int(manifest_dict.get("end_state_version", 0) or 0)

    # 1. Resolve Frozen Snapshot
    resolved_snapshot = dict(frozen_snapshot or {})
    if not resolved_snapshot:
        snapshot_path = str(manifest_dict.get("frozen_snapshot_path", "") or "").strip()
        if snapshot_path:
            resolved_snapshot = _load_optional_json(snapshot_path)

    batch_id = str(
        resolved_snapshot.get("batch_id")
        or manifest_dict.get("batch_id")
        or "unknown_batch"
    ).strip()

    # 2. Resolve Canonical State (Post-round)
    post_state = _resolve_round_canonical_state(canonical_state, manifest_dict)
    if not batch_id and post_state.batch_id:
        batch_id = post_state.batch_id

    # 3. Resolve Partition & Scenario Context
    resolved_dataset_path = Path(dataset_path) if dataset_path else None
    partition_name = resolved_dataset_path.name if resolved_dataset_path else "unknown_partition"
    partition_audit_context = build_partition_audit_context(partition_name)
    intended_scenario = build_intended_behavioral_scenario(
        partition_name, dataset_config=dataset_config
    )

    # 4. Resolve Execution Identity
    execution_identity = {
        "dataset_name": str(resolved_dataset_path) if resolved_dataset_path else partition_name,
        "partition_name": partition_name,
        "batch_id": batch_id,
        "round_id": round_id,
        "round_index": round_index,
        "analysis_mode": analysis_mode,
        "status": round_status,
        "terminal_reason": terminal_reason,
        "start_state_version": start_state_version,
        "end_state_version": end_state_version,
        "source_manifest_path": str(manifest_dict.get("frozen_snapshot_path", "")),
        "schema_version": ROUND_REPORT_SCHEMA_VERSION,
        "prompt_version": ROUND_REPORT_PROMPT_VERSION,
    }

    # 5. Resolve Investigation Objectives
    selected_hypothesis_ids = _string_list(manifest_dict.get("selected_hypothesis_ids", []))
    deferred_hypothesis_ids = _string_list(manifest_dict.get("deferred_hypothesis_ids", []))

    # Look up summaries from snapshot or state
    prior_ref = dict(resolved_snapshot.get("initial_hypothesis_set_ref", {}) or {})
    prior_hyp_refs = {
        str(item.get("hypothesis_id") or "").strip(): str(item.get("summary") or "").strip()
        for item in (prior_ref.get("hypothesis_refs") or [])
        if isinstance(item, dict) and item.get("hypothesis_id")
    }

    hypotheses_targeted: list[dict[str, Any]] = []
    for hyp_id in selected_hypothesis_ids:
        # Check post-state for summary
        state_hyp = next((h for h in post_state.interpretive_hypotheses if h.hypothesis_id == hyp_id), None)
        summary = state_hyp.summary if state_hyp else prior_hyp_refs.get(hyp_id, "")
        hypotheses_targeted.append({
            "hypothesis_id": hyp_id,
            "summary": summary,
            "status": state_hyp.status if state_hyp else "unresolved",
        })

    # Planned worker tasks from router runs
    worker_tasks_planned: list[dict[str, Any]] = []
    hypothesis_runs = list(manifest_dict.get("hypothesis_runs", []) or [])
    for rec in hypothesis_runs:
        hyp_id = str(rec.get("hypothesis_id", "") or "")
        router_path = str(rec.get("router_run_path", "") or "")
        task_ids = _string_list(rec.get("task_ids", []))
        router_data = _load_optional_json(router_path)
        parsed_router = router_data.get("parsed_output") or {}
        tasks = parsed_router.get("worker_tasks") if isinstance(parsed_router, dict) else []
        if isinstance(tasks, list):
            for t in tasks:
                if isinstance(t, dict):
                    worker_tasks_planned.append({
                        "task_id": str(t.get("task_id", "") or ""),
                        "hypothesis_id": hyp_id,
                        "question": str(t.get("question", "") or ""),
                        "feature_focus": _string_list(t.get("feature_focus", [])),
                        "assigned_tools": _string_list(t.get("assigned_tools", [])),
                        "allowed_actions": _string_list(t.get("allowed_actions", [])),
                    })
        elif task_ids:
            for tid in task_ids:
                worker_tasks_planned.append({
                    "task_id": tid,
                    "hypothesis_id": hyp_id,
                    "question": f"Investigate hypothesis {hyp_id}",
                    "feature_focus": [],
                    "assigned_tools": [],
                    "allowed_actions": [],
                })

    investigation_objectives = {
        "selected_hypothesis_ids": selected_hypothesis_ids,
        "deferred_hypothesis_ids": deferred_hypothesis_ids,
        "hypotheses_targeted": hypotheses_targeted,
        "worker_tasks_planned": worker_tasks_planned,
    }

    # 6. Resolve Round-Specific Evidence (Workers, Tools, Numerical Results)
    bundles = dict(round_bundles or {})
    worker_bundles: list[dict[str, Any]] = list(bundles.get("worker_bundles", []) or [])

    # If worker bundles were not passed in-memory, load from disk
    if not worker_bundles:
        for rec in hypothesis_runs:
            worker_paths = list(rec.get("worker_run_paths", []) or [])
            for wpath in worker_paths:
                wdata = _load_optional_json(wpath)
                if wdata:
                    worker_bundles.append(wdata)

    round_worker_findings: list[dict[str, Any]] = []
    round_tool_executions: list[dict[str, Any]] = []
    features_investigated: set[str] = set()
    validation_warnings: list[str] = []

    for wbundle in worker_bundles:
        w_output = dict(wbundle.get("parsed_output") or wbundle.get("worker_output") or {})
        w_res = dict(w_output.get("worker_result") or {})
        w_task_id = str(wbundle.get("task_id") or dict(wbundle.get("component_run", {})).get("task_id") or "")
        w_hyp_id = str(wbundle.get("hypothesis_id") or dict(wbundle.get("component_run", {})).get("hypothesis_id") or "")

        # Extract worker findings
        raw_findings = w_res.get("findings") or []
        for f in raw_findings:
            if isinstance(f, str):
                round_worker_findings.append({
                    "task_id": w_task_id,
                    "hypothesis_id": w_hyp_id,
                    "finding": _strip_internal_ids(f),
                })
            elif isinstance(f, dict):
                desc = str(f.get("description") or f.get("summary") or "")
                round_worker_findings.append({
                    "task_id": w_task_id,
                    "hypothesis_id": w_hyp_id,
                    "finding": _strip_internal_ids(desc),
                    "confidence": f.get("confidence"),
                })

        # Extract tool events and numerical metrics
        op_trace = dict(wbundle.get("operational_trace") or {})
        tool_events = list(op_trace.get("tool_events", []) or [])
        for event in tool_events:
            if not isinstance(event, dict):
                continue
            tool_res = dict(event.get("tool_result") or {})
            action = dict(event.get("action") or {})
            tool_name = str(tool_res.get("tool_name") or action.get("action_class") or "unknown_tool")
            feat_name = str(action.get("feature_name") or tool_res.get("feature_name") or "").strip()
            rel_feat = str(action.get("related_feature_name") or tool_res.get("related_feature_name") or "").strip()
            if feat_name:
                features_investigated.add(feat_name)
            if rel_feat:
                features_investigated.add(rel_feat)

            # Numerical metrics extracted from tool result
            metrics = dict(tool_res.get("metrics") or {})
            signals = _string_list(tool_res.get("signals") or [])

            round_tool_executions.append({
                "call_id": str(event.get("call_id") or ""),
                "task_id": w_task_id,
                "hypothesis_id": w_hyp_id,
                "tool_name": tool_name,
                "feature_name": feat_name,
                "related_feature_name": rel_feat,
                "status": str(tool_res.get("status") or "ok"),
                "metrics": metrics,
                "signals": signals,
            })

        # Extract worker validation warnings
        val_rep = dict(wbundle.get("validation_report") or {})
        for err in list(val_rep.get("errors", []) or []):
            if isinstance(err, dict):
                validation_warnings.append(str(err.get("message") or ""))

    # Critic bundle
    critic_bundle = dict(bundles.get("critic_bundle", {}) or {})
    if not critic_bundle and manifest_dict.get("critic_run_path"):
        critic_bundle = _load_optional_json(manifest_dict["critic_run_path"])

    critic_feedback = {}
    if critic_bundle:
        critic_out = dict(critic_bundle.get("parsed_output") or critic_bundle.get("critic_decision") or {})
        critic_feedback = {
            "status": str(dict(critic_bundle.get("component_run", {})).get("status") or "completed"),
            "critique": _strip_internal_ids(str(critic_out.get("critique") or "")),
            "strengths": [_strip_internal_ids(s) for s in _string_list(critic_out.get("strengths", []))],
            "blind_spots": [_strip_internal_ids(b) for b in _string_list(critic_out.get("blind_spots", []))],
            "next_round_guidance": [_strip_internal_ids(g) for g in _string_list(critic_out.get("next_round_guidance", []))],
        }

    round_evidence = {
        "worker_findings": round_worker_findings,
        "tool_executions": round_tool_executions,
        "features_investigated": sorted(features_investigated),
        "validation_warnings": list(dict.fromkeys(validation_warnings)),
        "critic_feedback": critic_feedback,
    }

    # 7. Resolve State Changes and Transitions (Distinguishing round delta from prior state)
    # Check revision log for records belonging to this round
    round_revisions: list[dict[str, Any]] = []
    for record in post_state.revision_log:
        rec_round_id = str(record.round_id or "").strip()
        rec_version = int(record.state_version or 0)
        # Matches round_id or falls in state version window of this round
        if rec_round_id == round_id or (start_state_version < rec_version <= end_state_version):
            round_revisions.append({
                "state_version": record.state_version,
                "hypothesis_id": record.hypothesis_id,
                "revision_type": record.revision_type,
                "applied_updates": record.applied_updates,
            })

    # Categorize hypotheses: updated in this round vs inherited from earlier
    updated_hypotheses: list[dict[str, Any]] = []
    inherited_hypotheses: list[dict[str, Any]] = []

    for hyp in post_state.interpretive_hypotheses:
        is_updated_in_round = (
            hyp.last_updated_round == round_id
            or any(r["hypothesis_id"] == hyp.hypothesis_id for r in round_revisions)
        )
        hyp_data = {
            "hypothesis_id": hyp.hypothesis_id,
            "summary": _strip_internal_ids(hyp.summary),
            "status": hyp.status,
            "revision_count": hyp.revision_count,
            "last_updated_round": hyp.last_updated_round,
            "merged_findings": [_strip_internal_ids(f) for f in _string_list(hyp.merged_findings)],
            "open_gaps": [_strip_internal_ids(g) for g in _string_list(hyp.open_gaps)],
            "preserved_contradictions": [_strip_internal_ids(c) for c in _string_list(hyp.preserved_contradictions)],
            "evidence_count": len(hyp.evidence_refs or []),
        }

        if is_updated_in_round:
            updated_hypotheses.append(hyp_data)
        else:
            inherited_hypotheses.append(hyp_data)

    state_transitions = {
        "round_start_state_version": start_state_version,
        "round_end_state_version": end_state_version,
        "round_revisions": round_revisions,
        "updated_hypotheses": updated_hypotheses,
        "inherited_hypotheses": inherited_hypotheses,
    }

    # 8. Resolve Provenance and Limitations
    source_artifacts = {
        "round_manifest": str(manifest_dict.get("manifest_path") or ""),
        "frozen_snapshot": str(manifest_dict.get("frozen_snapshot_path") or ""),
        "analysis_run": str(manifest_dict.get("analysis_run_path") or ""),
        "ranking_run": str(manifest_dict.get("ranking_run_path") or ""),
        "planner_run": str(manifest_dict.get("planner_run_path") or ""),
        "global_aggregation": str(manifest_dict.get("global_aggregation_path") or ""),
        "critic_run": str(manifest_dict.get("critic_run_path") or ""),
    }

    unresolved_questions: list[str] = []
    for hyp in updated_hypotheses:
        unresolved_questions.extend(hyp.get("open_gaps", []))
    for err in validation_warnings:
        unresolved_questions.append(f"Validation limitation: {err}")

    provenance_and_limitations = {
        "source_artifacts": {k: v for k, v in source_artifacts.items() if v},
        "unresolved_questions": list(dict.fromkeys(unresolved_questions)),
        "scope_boundary": (
            f"This audit report covers Round {round_id} only. "
            "It reflects findings and tool observations generated during this round, "
            "and does not represent a final multi-round batch conclusion."
        ),
    }

    return {
        "execution_identity": execution_identity,
        "partition_audit_context": partition_audit_context,
        "intended_behavioral_scenario": intended_scenario,
        "investigation_objectives": investigation_objectives,
        "round_evidence": round_evidence,
        "state_transitions": state_transitions,
        "provenance_and_limitations": provenance_and_limitations,
    }
