"""Resolve bounded Final Batch Auditor inputs from committed runtime artifacts."""

from __future__ import annotations

import re
from typing import Any

from aggregation.runtime_artifacts import list_aggregation_run_dirs, load_aggregation_bundle
from critic.runtime_artifacts import list_critic_run_dirs, load_critic_bundle
from state.schema import CanonicalBatchState
from state_manager.runtime_artifacts import list_state_manager_run_dirs, load_state_manager_bundle


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


def _bundle_identity(bundle: dict[str, Any]) -> str:
    artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
    component_run = dict(bundle.get("component_run", {}) or {})
    component_run_path = str(artifact_paths.get("component_run_path", "") or "").strip()
    if component_run_path:
        return component_run_path
    request_id = str(component_run.get("request_id", "") or "").strip()
    if request_id:
        return request_id
    component = str(component_run.get("component", "") or "unknown")
    batch_id = str(component_run.get("batch_id", "") or "unknown")
    round_id = str(component_run.get("round_id", "") or "unknown")
    hypothesis_id = str(component_run.get("hypothesis_id", "") or "unknown")
    return f"{component}:{batch_id}:{round_id}:{hypothesis_id}"


def _merge_bundle_lists(*bundle_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in bundle_groups:
        for bundle in group:
            identity = _bundle_identity(bundle)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(bundle)
    return merged


def _round_sort_key(value: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", str(value or ""))
    if match:
        return (int(match.group(1)), str(value or ""))
    return (0, str(value or ""))


def _is_state_manager_bundle_ready(bundle: dict[str, Any]) -> bool:
    component_run = dict(bundle.get("component_run", {}) or {})
    return bool(component_run.get("validation_ok", False)) and bool(
        component_run.get("state_committed", False)
    ) and bool(bundle.get("updated_batch_state"))


def _is_aggregation_bundle_ready(bundle: dict[str, Any]) -> bool:
    component_run = dict(bundle.get("component_run", {}) or {})
    return bool(component_run.get("validation_ok", False)) and bool(
        component_run.get("handoff_committed", False)
    )


def _is_critic_bundle_ready(bundle: dict[str, Any]) -> bool:
    component_run = dict(bundle.get("component_run", {}) or {})
    return bool(component_run.get("validation_ok", False))


def _load_persisted_batch_component_bundles(batch_id: str) -> dict[str, list[dict[str, Any]]]:
    normalized_batch_id = str(batch_id or "").strip()
    discovered: dict[str, list[dict[str, Any]]] = {
        "state_manager": [],
        "aggregation": [],
        "critic": [],
    }
    if not normalized_batch_id:
        return discovered

    for run_dir in list_state_manager_run_dirs():
        try:
            bundle = load_state_manager_bundle(run_dir)
        except Exception:
            continue
        component_run = dict(bundle.get("component_run", {}) or {})
        if str(component_run.get("batch_id", "") or "").strip() != normalized_batch_id:
            continue
        if _is_state_manager_bundle_ready(bundle):
            discovered["state_manager"].append(bundle)

    for run_dir in list_aggregation_run_dirs():
        try:
            bundle = load_aggregation_bundle(run_dir)
        except Exception:
            continue
        component_run = dict(bundle.get("component_run", {}) or {})
        if str(component_run.get("batch_id", "") or "").strip() != normalized_batch_id:
            continue
        if _is_aggregation_bundle_ready(bundle):
            discovered["aggregation"].append(bundle)

    for run_dir in list_critic_run_dirs():
        try:
            bundle = load_critic_bundle(run_dir)
        except Exception:
            continue
        component_run = dict(bundle.get("component_run", {}) or {})
        if str(component_run.get("batch_id", "") or "").strip() != normalized_batch_id:
            continue
        if _is_critic_bundle_ready(bundle):
            discovered["critic"].append(bundle)

    return discovered


def _collect_state_traceability_refs(canonical_state: CanonicalBatchState) -> list[str]:
    refs: list[str] = []
    substrate = dict(canonical_state.structural_substrate or {})
    for region in substrate.get("compressed_regions", []) or []:
        if not isinstance(region, dict):
            continue
        refs.extend(_string_list(region.get("evidence_refs")))
    for hypothesis in canonical_state.interpretive_hypotheses:
        refs.extend(hypothesis.evidence_refs)
    return list(dict.fromkeys(refs))


def _resolve_hypothesis_snapshot(
    bundle: dict[str, Any],
) -> dict[str, Any]:
    updated_batch_state = dict(bundle.get("updated_batch_state", {}) or {})
    component_run = dict(bundle.get("component_run", {}) or {})
    state_delta_record = dict(bundle.get("state_delta_record", {}) or {})
    state_manager_context = dict(bundle.get("state_manager_context", {}) or {})
    hypothesis_id = str(component_run.get("hypothesis_id", "") or "").strip()

    if updated_batch_state and hypothesis_id:
        try:
            canonical_state = CanonicalBatchState.from_dict(updated_batch_state)
            for hypothesis in canonical_state.interpretive_hypotheses:
                if hypothesis.hypothesis_id == hypothesis_id:
                    return hypothesis.to_dict()
        except Exception:
            pass

    target_hypothesis = dict(state_manager_context.get("target_hypothesis", {}) or {})
    if target_hypothesis:
        return target_hypothesis
    return state_delta_record


def _critic_feedback_refs(bundle: dict[str, Any]) -> list[str]:
    payload = dict(bundle.get("critic_feedback_payload", {}) or {})
    refs: list[str] = []
    for item in payload.get("module_feedback", []) or []:
        if not isinstance(item, dict):
            continue
        refs.extend(_string_list(item.get("evidence_refs")))
    return list(dict.fromkeys(refs))


def _index_history_bundles(
    bundles: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for bundle in bundles:
        component_run = dict(bundle.get("component_run", {}) or {})
        round_id = str(component_run.get("round_id", "") or "").strip()
        hypothesis_id = str(component_run.get("hypothesis_id", "") or "").strip()
        if round_id:
            indexed[(round_id, hypothesis_id)] = bundle
    return indexed


def build_final_batch_audit_context(
    state_manager_bundle: dict[str, Any],
    *,
    batch_component_bundles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = state_manager_bundle if isinstance(state_manager_bundle, dict) else {}
    artifact_paths = dict(raw.get("artifact_paths", {}) or {})
    component_run = dict(raw.get("component_run", {}) or {})
    updated_batch_state = dict(raw.get("updated_batch_state", {}) or {})
    batch_id = str(
        component_run.get("batch_id") or updated_batch_state.get("batch_id") or "unknown_batch"
    ).strip() or "unknown_batch"

    discovered = _load_persisted_batch_component_bundles(batch_id)
    provided = batch_component_bundles if isinstance(batch_component_bundles, dict) else {}
    state_manager_bundles = _merge_bundle_lists(
        [raw],
        _bundle_list(provided.get("state_manager")),
        discovered.get("state_manager", []),
    )
    aggregation_bundles = _merge_bundle_lists(
        _bundle_list(provided.get("aggregation")),
        discovered.get("aggregation", []),
    )
    critic_bundles = _merge_bundle_lists(
        _bundle_list(provided.get("critic")),
        discovered.get("critic", []),
    )

    ready_state_manager_bundles = [
        bundle for bundle in state_manager_bundles if _is_state_manager_bundle_ready(bundle)
    ]
    ready_aggregation_bundles = [
        bundle for bundle in aggregation_bundles if _is_aggregation_bundle_ready(bundle)
    ]
    ready_critic_bundles = [bundle for bundle in critic_bundles if _is_critic_bundle_ready(bundle)]

    ready_state_manager_bundles.sort(
        key=lambda bundle: (
            _int_value(
                dict(bundle.get("component_run", {}) or {}).get("new_state_version"),
                default=0,
            ),
            _round_sort_key(dict(bundle.get("component_run", {}) or {}).get("round_id", "")),
        )
    )

    final_state_ref = _artifact_ref(
        artifact_paths,
        "updated_batch_state_path",
        "state_manager.updated_batch_state",
    )

    try:
        canonical_state = CanonicalBatchState.from_dict(updated_batch_state)
    except Exception:
        canonical_state = CanonicalBatchState(
            batch_id=batch_id,
            state_version=_int_value(updated_batch_state.get("state_version"), default=1),
            structural_substrate=dict(updated_batch_state.get("structural_substrate", {}) or {}),
        )

    known_traceability_refs: set[str] = {final_state_ref}
    known_traceability_refs.update(_collect_state_traceability_refs(canonical_state))

    substrate = dict(canonical_state.structural_substrate or {})
    hypothesis_snapshots: list[dict[str, Any]] = []
    for hypothesis in canonical_state.interpretive_hypotheses[:8]:
        hypothesis_snapshots.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "status": hypothesis.status,
                "summary": hypothesis.summary,
                "evidence_refs": list(hypothesis.evidence_refs),
                "open_gaps": list(hypothesis.open_gaps),
                "preserved_contradictions": list(hypothesis.preserved_contradictions),
                "merged_findings": list(hypothesis.merged_findings),
                "last_updated_round": hypothesis.last_updated_round,
                "revision_count": hypothesis.revision_count,
            }
        )

    final_state_summary = {
        "batch_id": canonical_state.batch_id or batch_id,
        "state_version": canonical_state.state_version,
        "substrate_region_count": len(substrate.get("compressed_regions", []) or []),
        "hypothesis_count": len(canonical_state.interpretive_hypotheses),
        "active_hypothesis_count": len(
            [item for item in canonical_state.interpretive_hypotheses if item.status != "resolved"]
        ),
        "revision_count": len(canonical_state.revision_log),
        "hypothesis_snapshots": hypothesis_snapshots,
    }

    aggregation_index = _index_history_bundles(ready_aggregation_bundles)
    critic_index = _index_history_bundles(ready_critic_bundles)

    round_artifact_refs: list[dict[str, str]] = []
    hypothesis_history_refs: list[dict[str, str]] = []
    round_history_summary: list[dict[str, Any]] = []
    warning_codes: set[str] = set()

    for bundle in ready_state_manager_bundles:
        bundle_component_run = dict(bundle.get("component_run", {}) or {})
        bundle_artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
        round_id = str(bundle_component_run.get("round_id", "") or "").strip() or "unknown_round"
        hypothesis_id = str(bundle_component_run.get("hypothesis_id", "") or "").strip() or "unknown_hypothesis"
        bundle_key = (round_id, hypothesis_id)

        updated_state_ref = _artifact_ref(
            bundle_artifact_paths,
            "updated_batch_state_path",
            f"state_manager.updated_batch_state.{round_id}",
        )
        state_update_ref = _artifact_ref(
            bundle_artifact_paths,
            "state_update_result_path",
            f"state_manager.state_update_result.{round_id}",
        )
        round_artifact_refs.extend(
            [
                {
                    "round_id": round_id,
                    "component_name": "state_manager",
                    "artifact_kind": "updated_batch_state",
                    "artifact_ref": updated_state_ref,
                },
                {
                    "round_id": round_id,
                    "component_name": "state_manager",
                    "artifact_kind": "state_update_result",
                    "artifact_ref": state_update_ref,
                },
            ]
        )
        hypothesis_history_refs.append(
            {
                "hypothesis_id": hypothesis_id,
                "round_id": round_id,
                "history_ref": updated_state_ref,
            }
        )
        known_traceability_refs.update({updated_state_ref, state_update_ref})

        hypothesis_snapshot = _resolve_hypothesis_snapshot(bundle)
        aggregation_bundle = aggregation_index.get(bundle_key)
        critic_bundle = critic_index.get(bundle_key)

        aggregation_handoff = {}
        overlap_diagnostics: list[dict[str, Any]] = []
        if aggregation_bundle is not None:
            aggregation_paths = dict(aggregation_bundle.get("artifact_paths", {}) or {})
            aggregation_handoff = dict(aggregation_bundle.get("aggregation_handoff", {}) or {})
            overlap_diagnostics = list(aggregation_bundle.get("overlap_diagnostics", []) or [])
            aggregation_handoff_ref = _artifact_ref(
                aggregation_paths,
                "aggregation_handoff_path",
                f"aggregation.aggregation_handoff.{round_id}",
            )
            overlap_ref = _artifact_ref(
                aggregation_paths,
                "overlap_diagnostics_path",
                f"aggregation.overlap_diagnostics.{round_id}",
            )
            round_artifact_refs.extend(
                [
                    {
                        "round_id": round_id,
                        "component_name": "aggregation",
                        "artifact_kind": "aggregation_handoff",
                        "artifact_ref": aggregation_handoff_ref,
                    },
                    {
                        "round_id": round_id,
                        "component_name": "aggregation",
                        "artifact_kind": "overlap_diagnostics",
                        "artifact_ref": overlap_ref,
                    },
                ]
            )
            known_traceability_refs.update({aggregation_handoff_ref, overlap_ref})
            known_traceability_refs.update(_string_list(aggregation_handoff.get("evidence_refs")))
        else:
            fallback_aggregation_ref = _artifact_ref(
                bundle_artifact_paths,
                "aggregation_handoff_path",
                f"aggregation.aggregation_handoff.{round_id}",
            )
            round_artifact_refs.append(
                {
                    "round_id": round_id,
                    "component_name": "aggregation",
                    "artifact_kind": "aggregation_handoff",
                    "artifact_ref": fallback_aggregation_ref,
                }
            )
            known_traceability_refs.add(fallback_aggregation_ref)

        critic_feedback_count = 0
        if critic_bundle is not None:
            critic_paths = dict(critic_bundle.get("artifact_paths", {}) or {})
            critic_feedback_ref = _artifact_ref(
                critic_paths,
                "critic_feedback_payload_path",
                f"critic.critic_feedback_payload.{round_id}",
            )
            round_artifact_refs.append(
                {
                    "round_id": round_id,
                    "component_name": "critic",
                    "artifact_kind": "critic_feedback_payload",
                    "artifact_ref": critic_feedback_ref,
                }
            )
            known_traceability_refs.add(critic_feedback_ref)
            critic_feedback_refs = _critic_feedback_refs(critic_bundle)
            known_traceability_refs.update(critic_feedback_refs)
            critic_feedback_count = len(
                dict(critic_bundle.get("critic_feedback_payload", {}) or {}).get("module_feedback", []) or []
            )

        traceability_refs = _string_list(hypothesis_snapshot.get("evidence_refs"))
        traceability_refs.extend(_string_list(aggregation_handoff.get("evidence_refs")))
        traceability_refs = list(dict.fromkeys(traceability_refs))[:6]
        known_traceability_refs.update(traceability_refs)

        contradictions = _string_list(hypothesis_snapshot.get("preserved_contradictions")) or _string_list(
            aggregation_handoff.get("preserved_contradictions")
        )
        open_gaps = _string_list(hypothesis_snapshot.get("open_gaps"))
        if contradictions:
            warning_codes.add("contradictions_survive")
        if open_gaps:
            warning_codes.add("open_pressures_survive")
        if overlap_diagnostics:
            warning_codes.add("overlap_survives")

        round_history_summary.append(
            {
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "state_version": _int_value(bundle_component_run.get("new_state_version"), default=0),
                "status": str(hypothesis_snapshot.get("status", "unknown") or "unknown"),
                "summary": str(hypothesis_snapshot.get("summary", "") or ""),
                "contradiction_count": len(contradictions),
                "open_gap_count": len(open_gaps),
                "overlap_group_count": len(overlap_diagnostics),
                "critic_feedback_count": critic_feedback_count,
                "traceability_refs": traceability_refs,
            }
        )

    round_history_summary.sort(key=lambda item: _round_sort_key(item.get("round_id", "")))
    round_artifact_refs = [
        item
        for item in round_artifact_refs
        if str(item.get("artifact_ref", "") or "").strip()
    ]
    hypothesis_history_refs = [
        item
        for item in hypothesis_history_refs
        if str(item.get("history_ref", "") or "").strip()
    ]
    known_traceability_refs.update(
        str(item.get("artifact_ref", "") or "").strip() for item in round_artifact_refs
    )
    known_traceability_refs.update(
        str(item.get("history_ref", "") or "").strip() for item in hypothesis_history_refs
    )

    process_signal_summary = {
        "batch_id": batch_id,
        "state_version": canonical_state.state_version,
        "round_count": len(round_history_summary),
        "critic_run_count": len(ready_critic_bundles),
        "terminal_gate_expected": True,
        "warning_codes": sorted(code for code in warning_codes if code),
    }

    final_audit_input = {
        "batch_id": batch_id,
        "final_state_ref": final_state_ref,
        "round_artifact_refs": round_artifact_refs,
        "hypothesis_history_refs": hypothesis_history_refs,
    }

    return {
        "final_audit_input": final_audit_input,
        "final_state_summary": final_state_summary,
        "round_history_summary": round_history_summary,
        "process_signal_summary": process_signal_summary,
        "known_traceability_refs": sorted(ref for ref in known_traceability_refs if ref),
        "source_state_manager_run_path": str(artifact_paths.get("component_run_path", "") or ""),
    }
