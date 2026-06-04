"""Artifact persistence for authoritative Phase 3A batch runtime runs."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from phase3_runtime.ledger import BatchLedger
from utils.run_logging import load_json, write_json


DEFAULT_PHASE3A_RUNTIME_DIR = Path(__file__).resolve(
).parent.parent / "logs" / "phase3a_runtime_runs"
_RUN_INDEX_PATTERN = re.compile(r"^phase3a_runtime_run_(?P<index>\d{3})_")


def _format_batch_tag(batch_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_",
                        str(batch_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_batch"


def ensure_phase3a_runtime_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_PHASE3A_RUNTIME_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_phase3a_runtime_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_phase3a_runtime_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_phase3a_runtime_run_basename(
    batch_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_phase3a_runtime_run_index(
        log_dir)
    return "phase3a_runtime_run_{index:03d}_{day_month}_{batch_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        batch_tag=_format_batch_tag(batch_id),
    )


def build_phase3a_runtime_artifact_paths(
    *,
    batch_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_phase3a_runtime_runs_dir(log_dir)
    run_dir = runs_dir / \
        build_phase3a_runtime_run_basename(batch_id, log_dir=log_dir)
    round_dir = run_dir / "round_manifests"
    round_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "run_manifest_path": run_dir / "run_manifest.json",
        "runtime_summary_path": run_dir / "runtime_summary.json",
        "event_stream_path": run_dir / "event_stream.jsonl",
        "terminal_log_path": run_dir / "runtime_terminal.log",
        "component_run_path": run_dir / "component_run.json",
        "batch_ledger_path": run_dir / "batch_ledger.json",
        "initial_runtime_context_path": run_dir / "initial_runtime_context.json",
        "initial_state_path": run_dir / "initial_state.json",
        "finalization_summary_path": run_dir / "finalization_summary.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
        "round_manifests_dir": round_dir,
    }


def save_phase3a_runtime_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    batch_ledger: BatchLedger | dict[str, Any],
    initial_runtime_context: dict[str, Any],
    finalization_summary: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
    runtime_summary: dict[str, Any] | None = None,
    run_manifest: dict[str, Any] | None = None,
) -> dict[str, str]:
    ledger_payload = batch_ledger.to_dict() if isinstance(
        batch_ledger, BatchLedger) else dict(batch_ledger)

    write_json(artifact_paths["batch_ledger_path"], ledger_payload)
    write_json(
        artifact_paths["initial_runtime_context_path"], initial_runtime_context)
    write_json(
        artifact_paths["finalization_summary_path"], finalization_summary)
    write_json(artifact_paths["runtime_metrics_path"], runtime_metrics)
    write_json(artifact_paths["replay_metadata_path"], replay_metadata)

    round_manifest_dir = artifact_paths["round_manifests_dir"]
    for manifest in ledger_payload.get("round_manifests", []) or []:
        if not isinstance(manifest, dict):
            continue
        round_id = str(manifest.get("round_id")
                       or "unknown_round").strip() or "unknown_round"
        write_json(round_manifest_dir / f"{round_id}.json", manifest)

    completed_components = list(component_run.get("completed_components", []))
    failed_components = list(component_run.get("failed_components", []))
    warnings = list(component_run.get("warnings", []))
    errors = list(component_run.get("errors", []))
    run_id = Path(str(artifact_paths.get("run_dir", ""))).name
    batch_id = str(component_run.get("batch_id")
                   or ledger_payload.get("batch_id") or "")
    mode = str(component_run.get("execution_mode") or "")
    status = str(component_run.get("status")
                 or ledger_payload.get("status") or "")
    start_time = str(component_run.get("created_at")
                     or ledger_payload.get("created_at") or "")
    end_time = str(component_run.get("completed_at")
                   or ledger_payload.get("completed_at") or "")
    dataset_path = str(
        initial_runtime_context.get("dataset_path")
        or ledger_payload.get("dataset_path")
        or ""
    )

    run_manifest_payload = dict(run_manifest or {
        "run_id": run_id,
        "batch_id": batch_id,
        "mode": mode,
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "dataset": dataset_path,
        "completed_components": completed_components,
        "failed_components": failed_components,
        "warnings": warnings,
        "errors": errors,
    })
    write_json(artifact_paths["run_manifest_path"], run_manifest_payload)

    runtime_summary_payload = dict(runtime_summary or {
        "run_id": run_id,
        "batch_id": batch_id,
        "mode": mode,
        "status": status,
        "final_status": str(component_run.get("final_status") or ""),
        "terminal_reason": str(component_run.get("terminal_reason") or ""),
        "start_time": start_time,
        "end_time": end_time,
        "dataset": dataset_path,
        "completed_components": completed_components,
        "failed_components": failed_components,
        "warnings": warnings,
        "errors": errors,
        "round_count": int(runtime_metrics.get("round_count", 0) or 0),
        "final_state_version": int(runtime_metrics.get("final_state_version", 0) or 0),
    })
    runtime_summary_payload["artifact_paths"] = {
        key: str(path) for key, path in artifact_paths.items()
    }
    write_json(artifact_paths["runtime_summary_path"], runtime_summary_payload)

    component_payload = dict(component_run)
    component_payload["artifact_paths"] = {
        key: str(path)
        for key, path in artifact_paths.items()
    }
    write_json(artifact_paths["component_run_path"], component_payload)

    persisted = {
        key: str(path)
        for key, path in artifact_paths.items()
    }
    return persisted


def list_phase3a_runtime_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_phase3a_runtime_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir()
             and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_phase3a_runtime_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = dict(component_run.get("artifact_paths", {}) or {})
    ledger_payload = load_json(artifact_paths["batch_ledger_path"])
    batch_ledger = BatchLedger.from_dict(ledger_payload)
    initial_state_path = Path(
        str(artifact_paths.get("initial_state_path", "") or "").strip())
    initial_state = load_json(
        initial_state_path) if initial_state_path.is_file() else {}
    runtime_summary_path = Path(
        str(artifact_paths.get("runtime_summary_path", "") or "").strip())
    runtime_summary = load_json(
        runtime_summary_path) if runtime_summary_path.is_file() else {}
    run_manifest_path = Path(
        str(artifact_paths.get("run_manifest_path", "") or "").strip())
    run_manifest = load_json(run_manifest_path) if run_manifest_path.is_file() else {}
    event_stream_path = Path(
        str(artifact_paths.get("event_stream_path", "") or "").strip())
    event_stream: list[dict[str, Any]] = []
    if event_stream_path.is_file():
        for line in event_stream_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            event_stream.append(json.loads(stripped))
    terminal_log_path = Path(
        str(artifact_paths.get("terminal_log_path", "") or "").strip())
    terminal_log_text = terminal_log_path.read_text(
        encoding="utf-8") if terminal_log_path.is_file() else ""

    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "batch_ledger": batch_ledger,
        "run_manifest": run_manifest,
        "initial_runtime_context": load_json(artifact_paths["initial_runtime_context_path"]),
        "initial_state": initial_state,
        "finalization_summary": load_json(artifact_paths["finalization_summary_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "runtime_summary": runtime_summary,
        "event_stream": event_stream,
        "terminal_log_text": terminal_log_text,
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }
