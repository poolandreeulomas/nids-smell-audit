"""Worker-result loading and normalization helpers for Aggregation."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from aggregation.contracts import build_worker_result_set
from worker.runtime_artifacts import list_worker_run_dirs, load_worker_bundle


def _string_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        stripped = _string_value(value)
        if stripped:
            normalized.append(stripped)
    return normalized


def normalize_worker_result(worker_result: dict[str, Any]) -> dict[str, Any]:
    raw = worker_result if isinstance(worker_result, dict) else {}
    return {
        "task_id": _string_value(raw.get("task_id")),
        "hypothesis_id": _string_value(raw.get("hypothesis_id")),
        "status": _string_value(raw.get("status")),
        "findings": _string_list(raw.get("findings")),
        "evidence_refs": _string_list(raw.get("evidence_refs")),
        "contradictions": _string_list(raw.get("contradictions")),
        "limitations": _string_list(raw.get("limitations")),
    }


def _build_overlap_diagnostics(worker_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for left, right in combinations(worker_results, 2):
        shared_findings = sorted(set(left.get("findings", [])).intersection(right.get("findings", [])))
        shared_evidence_refs = sorted(set(left.get("evidence_refs", [])).intersection(right.get("evidence_refs", [])))
        shared_contradictions = sorted(
            set(left.get("contradictions", [])).intersection(right.get("contradictions", []))
        )
        if not shared_findings and not shared_evidence_refs and not shared_contradictions:
            continue
        diagnostics.append(
            {
                "left_task_id": left.get("task_id", "unknown_task"),
                "right_task_id": right.get("task_id", "unknown_task"),
                "shared_findings": shared_findings,
                "shared_evidence_refs": shared_evidence_refs,
                "shared_contradictions": shared_contradictions,
            }
        )
    return diagnostics


def build_normalized_inputs(
    worker_result_set: dict[str, Any],
    *,
    expected_task_ids: list[str] | None = None,
    source_run_dirs: list[str] | None = None,
) -> dict[str, Any]:
    raw = worker_result_set if isinstance(worker_result_set, dict) else {}
    expected_task_ids_list = sorted({task_id for task_id in (_string_list(expected_task_ids) if expected_task_ids else [])})
    worker_results = [
        normalize_worker_result(worker_result)
        for worker_result in (raw.get("worker_results") if isinstance(raw.get("worker_results"), list) else [])
        if isinstance(worker_result, dict)
    ]
    worker_results.sort(key=lambda item: item.get("task_id", ""))

    selected_task_ids = [result.get("task_id", "") for result in worker_results if result.get("task_id")]
    selected_task_id_set = set(selected_task_ids)
    expected_task_id_set = set(expected_task_ids_list)

    status_counts = Counter(str(result.get("status") or "unknown") for result in worker_results)
    source_evidence_refs = sorted(
        {
            evidence_ref
            for result in worker_results
            for evidence_ref in result.get("evidence_refs", [])
        }
    )
    source_contradiction_texts = sorted(
        {
            contradiction
            for result in worker_results
            for contradiction in result.get("contradictions", [])
        }
    )
    source_contradictions = [
        {"id": f"contr_{idx}", "text": text}
        for idx, text in enumerate(source_contradiction_texts)
    ]
    source_contradiction_lookup = {
        item["id"]: item["text"]
        for item in source_contradictions
    }
    source_limitations = sorted(
        {
            limitation
            for result in worker_results
            for limitation in result.get("limitations", [])
        }
    )

    return {
        "batch_id": _string_value(raw.get("batch_id")),
        "round_id": _string_value(raw.get("round_id")),
        "hypothesis_id": _string_value(raw.get("hypothesis_id")),
        "worker_result_count": len(worker_results),
        "expected_task_ids": expected_task_ids_list,
        "selected_task_ids": selected_task_ids,
        "missing_task_ids": sorted(expected_task_id_set - selected_task_id_set),
        "extra_task_ids": sorted(selected_task_id_set - expected_task_id_set),
        "source_run_dirs": sorted({str(path) for path in (source_run_dirs or []) if str(path).strip()}),
        "status_counts": dict(sorted(status_counts.items())),
        "source_evidence_refs": source_evidence_refs,
        "source_contradictions": source_contradictions,
        "source_limitations": source_limitations,
        "source_finding_count": sum(len(result.get("findings", [])) for result in worker_results),
        "non_success_count": sum(
            1 for result in worker_results if str(result.get("status") or "") not in {"completed", "partial"}
        ),
        "worker_results": worker_results,
        "overlap_diagnostics": _build_overlap_diagnostics(worker_results),
        "source_contradiction_lookup": source_contradiction_lookup,
    }


def _is_authoritative_worker_bundle(
    bundle: dict[str, Any],
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
) -> bool:
    component_run = bundle.get("component_run") if isinstance(bundle.get("component_run"), dict) else {}
    if str(component_run.get("batch_id") or "") != batch_id:
        return False
    if str(component_run.get("round_id") or "") != round_id:
        return False
    if str(component_run.get("hypothesis_id") or "") != hypothesis_id:
        return False
    if not bool(component_run.get("validation_ok")):
        return False
    if not bool(component_run.get("result_committed")):
        return False
    worker_result = bundle.get("worker_result") if isinstance(bundle.get("worker_result"), dict) else {}
    if not worker_result:
        return False
    if str(worker_result.get("hypothesis_id") or "") != hypothesis_id:
        return False
    if not str(worker_result.get("task_id") or "").strip():
        return False
    return True


def load_worker_result_set(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    expected_task_ids: list[str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized_batch_id = _string_value(batch_id) or "unknown_batch"
    normalized_round_id = _string_value(round_id) or "unknown_round"
    normalized_hypothesis_id = _string_value(hypothesis_id) or "unknown_hypothesis"
    expected_task_id_set = set(_string_list(expected_task_ids)) if expected_task_ids else set()

    selected_results_by_task_id: dict[str, dict[str, Any]] = {}
    selected_run_dirs: list[str] = []

    for run_dir in list_worker_run_dirs(log_dir=log_dir):
        try:
            bundle = load_worker_bundle(run_dir)
        except Exception:
            continue
        if not _is_authoritative_worker_bundle(
            bundle,
            batch_id=normalized_batch_id,
            round_id=normalized_round_id,
            hypothesis_id=normalized_hypothesis_id,
        ):
            continue
        worker_result = normalize_worker_result(bundle.get("worker_result", {}))
        task_id = worker_result.get("task_id", "")
        if expected_task_id_set and task_id not in expected_task_id_set:
            continue
        if task_id in selected_results_by_task_id:
            continue
        selected_results_by_task_id[task_id] = worker_result
        selected_run_dirs.append(str(run_dir))
        if expected_task_id_set and len(selected_results_by_task_id) == len(expected_task_id_set):
            break

    worker_results = [selected_results_by_task_id[task_id] for task_id in sorted(selected_results_by_task_id)]
    worker_result_set = build_worker_result_set(
        batch_id=normalized_batch_id,
        round_id=normalized_round_id,
        hypothesis_id=normalized_hypothesis_id,
        worker_results=worker_results,
    )
    normalized_inputs = build_normalized_inputs(
        worker_result_set,
        expected_task_ids=sorted(expected_task_id_set),
        source_run_dirs=selected_run_dirs,
    )
    return {
        "worker_result_set": worker_result_set,
        "normalized_inputs": normalized_inputs,
        "selected_run_dirs": selected_run_dirs,
    }