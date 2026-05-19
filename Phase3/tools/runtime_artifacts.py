"""Artifact persistence for direct Phase 3A tool execution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_TOOL_RUNS_DIR = Path(__file__).resolve().parent.parent / "logs" / "tool_runs"
_TOOL_RUN_PATTERN = re.compile(r"^tool_run_(?P<index>\d{3})_")


def ensure_tool_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_TOOL_RUNS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_tool_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_tool_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.glob("tool_run_*"):
        if not path.is_dir():
            continue
        match = _TOOL_RUN_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or "unknown"


def build_tool_run_basename(
    *,
    tool_name: str,
    target_scope: str,
    log_dir: str | Path | None = None,
    timestamp: datetime | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    index = get_next_tool_run_index(log_dir)
    return f"tool_run_{index:03d}_{ts.strftime('%d-%m')}_{_slugify(tool_name)}_{_slugify(target_scope)}"


def build_tool_run_artifact_paths(
    *,
    tool_name: str,
    target_scope: str,
    log_dir: str | Path | None = None,
    basename: str | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_tool_runs_dir(log_dir)
    run_basename = basename or build_tool_run_basename(
        tool_name=tool_name,
        target_scope=target_scope,
        log_dir=runs_dir,
    )
    run_dir = runs_dir / run_basename
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "tool_call_request_path": run_dir / "tool_call_request.json",
        "tool_capability_record_path": run_dir / "tool_capability_record.json",
        "normalized_inputs_path": run_dir / "normalized_inputs.json",
        "raw_tool_output_path": run_dir / "raw_tool_output.json",
        "parsed_output_path": run_dir / "parsed_output.json",
        "validation_report_path": run_dir / "validation_report.json",
        "tool_metrics_path": run_dir / "tool_metrics.json",
        "cache_record_path": run_dir / "cache_record.json",
        "replay_diff_path": run_dir / "replay_diff.json",
    }


def build_tool_evidence_refs(artifact_paths: dict[str, Path]) -> list[dict[str, str]]:
    return [
        {"artifact": "parsed_output", "path": str(artifact_paths["parsed_output_path"])},
        {"artifact": "raw_tool_output", "path": str(artifact_paths["raw_tool_output_path"])},
        {"artifact": "component_run", "path": str(artifact_paths["component_run_path"])},
    ]


def save_tool_run_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    tool_call_request: dict[str, Any],
    tool_capability_record: dict[str, Any],
    normalized_inputs: dict[str, Any],
    raw_tool_output: dict[str, Any],
    parsed_output: dict[str, Any],
    validation_report: dict[str, Any],
    tool_metrics: dict[str, Any],
    cache_record: dict[str, Any] | None = None,
    replay_diff: dict[str, Any] | None = None,
) -> dict[str, str]:
    write_json(artifact_paths["tool_call_request_path"], tool_call_request)
    write_json(artifact_paths["tool_capability_record_path"], tool_capability_record)
    write_json(artifact_paths["normalized_inputs_path"], normalized_inputs)
    write_json(artifact_paths["raw_tool_output_path"], raw_tool_output)
    write_json(artifact_paths["parsed_output_path"], parsed_output)
    write_json(artifact_paths["validation_report_path"], validation_report)
    write_json(artifact_paths["tool_metrics_path"], tool_metrics)

    if cache_record is not None:
        write_json(artifact_paths["cache_record_path"], cache_record)
    if replay_diff is not None:
        write_json(artifact_paths["replay_diff_path"], replay_diff)

    component_payload = dict(component_run)
    component_payload["artifact_paths"] = {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
        and (key != "replay_diff_path" or replay_diff is not None)
        and (key != "cache_record_path" or cache_record is not None)
    }
    write_json(artifact_paths["component_run_path"], component_payload)

    return {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
        and path.exists()
    }


def list_tool_run_dirs(log_dir: str | Path | None = None, limit: int | None = None) -> list[Path]:
    runs_dir = ensure_tool_runs_dir(log_dir)
    run_dirs = sorted(
        (path for path in runs_dir.glob("tool_run_*") if path.is_dir()),
        reverse=True,
    )
    if limit is None:
        return run_dirs
    return run_dirs[:limit]


def load_tool_run_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    bundle = {
        "component_run": component_run,
        "tool_call_request": load_json(artifact_paths["tool_call_request_path"]),
        "tool_capability_record": load_json(artifact_paths["tool_capability_record_path"]),
        "normalized_inputs": load_json(artifact_paths["normalized_inputs_path"]),
        "raw_tool_output": load_json(artifact_paths["raw_tool_output_path"]),
        "parsed_output": load_json(artifact_paths["parsed_output_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "tool_metrics": load_json(artifact_paths["tool_metrics_path"]),
        "artifact_paths": artifact_paths,
    }
    cache_path = artifact_paths.get("cache_record_path")
    if cache_path:
        bundle["cache_record"] = load_json(cache_path)
    replay_diff_path = artifact_paths.get("replay_diff_path")
    if replay_diff_path:
        bundle["replay_diff"] = load_json(replay_diff_path)
    return bundle