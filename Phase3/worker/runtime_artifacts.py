"""Artifact persistence for Worker component runs."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_WORKER_DIR = Path(__file__).resolve().parent.parent / "logs" / "worker_runs"
_RUN_INDEX_PATTERN = re.compile(r"^worker_run_(?P<index>\d{3})_")


def _format_task_tag(task_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(task_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_task"


def _write_json_like(file_path: Path, payload: Any) -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return file_path


def ensure_worker_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_WORKER_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_worker_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_worker_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_worker_run_basename(
    task_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_worker_run_index(log_dir)
    return "worker_run_{index:03d}_{day_month}_{task}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        task=_format_task_tag(task_id),
    )


def build_worker_artifact_paths(
    *,
    task_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_worker_runs_dir(log_dir)
    run_dir = runs_dir / build_worker_run_basename(task_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "worker_task_path": run_dir / "worker_task.json",
        "worker_runtime_refs_path": run_dir / "worker_runtime_refs.json",
        "prompt_snapshots_path": run_dir / "prompt_snapshots.json",
        "raw_model_responses_path": run_dir / "raw_model_responses.json",
        "parsed_steps_path": run_dir / "parsed_steps.json",
        "tool_events_path": run_dir / "tool_events.json",
        "retry_events_path": run_dir / "retry_events.json",
        "failure_events_path": run_dir / "failure_events.json",
        "worker_result_path": run_dir / "worker_result.json",
        "worker_output_path": run_dir / "worker_output.json",
        "operational_trace_path": run_dir / "operational_trace.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def save_worker_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    worker_task: dict[str, Any],
    worker_runtime_refs: dict[str, Any],
    prompt_snapshots: list[dict[str, Any]],
    raw_model_responses: list[dict[str, Any]],
    parsed_steps: list[dict[str, Any]],
    tool_events: list[dict[str, Any]],
    retry_events: list[dict[str, Any]],
    failure_events: list[dict[str, Any]],
    worker_result: dict[str, Any],
    worker_output: dict[str, Any],
    operational_trace: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["worker_task_path"], worker_task)
    write_json(artifact_paths["worker_runtime_refs_path"], worker_runtime_refs)
    _write_json_like(artifact_paths["prompt_snapshots_path"], prompt_snapshots)
    _write_json_like(artifact_paths["raw_model_responses_path"], raw_model_responses)
    _write_json_like(artifact_paths["parsed_steps_path"], parsed_steps)
    _write_json_like(artifact_paths["tool_events_path"], tool_events)
    _write_json_like(artifact_paths["retry_events_path"], retry_events)
    _write_json_like(artifact_paths["failure_events_path"], failure_events)
    write_json(artifact_paths["worker_result_path"], worker_result)
    write_json(artifact_paths["worker_output_path"], worker_output)
    write_json(artifact_paths["operational_trace_path"], operational_trace)
    write_json(artifact_paths["validation_report_path"], validation_report)
    write_json(artifact_paths["runtime_metrics_path"], runtime_metrics)
    write_json(artifact_paths["replay_metadata_path"], replay_metadata)

    component_payload = dict(component_run)
    component_payload["artifact_paths"] = {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
    }
    write_json(artifact_paths["component_run_path"], component_payload)

    return {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
    }


def list_worker_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_worker_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_worker_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "worker_task": load_json(artifact_paths["worker_task_path"]),
        "worker_runtime_refs": load_json(artifact_paths["worker_runtime_refs_path"]),
        "prompt_snapshots": load_json(artifact_paths["prompt_snapshots_path"]),
        "raw_model_responses": load_json(artifact_paths["raw_model_responses_path"]),
        "parsed_steps": load_json(artifact_paths["parsed_steps_path"]),
        "tool_events": load_json(artifact_paths["tool_events_path"]),
        "retry_events": load_json(artifact_paths["retry_events_path"]),
        "failure_events": load_json(artifact_paths["failure_events_path"]),
        "worker_result": load_json(artifact_paths["worker_result_path"]),
        "worker_output": load_json(artifact_paths["worker_output_path"]),
        "operational_trace": load_json(artifact_paths["operational_trace_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }