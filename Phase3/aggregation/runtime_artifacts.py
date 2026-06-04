"""Artifact persistence for Aggregation component runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_AGGREGATION_DIR = Path(__file__).resolve(
).parent.parent / "logs" / "aggregation_runs"
_RUN_INDEX_PATTERN = re.compile(r"^aggregation_run_(?P<index>\d{3})_")


def _format_hypothesis_tag(hypothesis_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_",
                        str(hypothesis_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_hypothesis"


def ensure_aggregation_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_AGGREGATION_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_aggregation_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_aggregation_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_aggregation_run_basename(
    hypothesis_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_aggregation_run_index(
        log_dir)
    return "aggregation_run_{index:03d}_{day_month}_{hypothesis_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        hypothesis_tag=_format_hypothesis_tag(hypothesis_id),
    )


def build_aggregation_artifact_paths(
    *,
    hypothesis_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_aggregation_runs_dir(log_dir)
    run_dir = runs_dir / \
        build_aggregation_run_basename(hypothesis_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "worker_result_set_path": run_dir / "worker_result_set.json",
        "normalized_inputs_path": run_dir / "normalized_inputs.json",
        "overlap_diagnostics_path": run_dir / "overlap_diagnostics.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "parsed_output_path": run_dir / "parsed_output.json",
        "aggregation_handoff_path": run_dir / "aggregation_handoff.json",
        "repair_attempts_path": run_dir / "repair_attempts.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_aggregation_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    worker_result_set: dict[str, Any],
    normalized_inputs: dict[str, Any],
    overlap_diagnostics: list[dict[str, Any]],
    rendered_prompt: str,
    raw_response: str,
    parsed_output: dict[str, Any],
    aggregation_handoff: dict[str, Any],
    repair_attempts: list[dict[str, Any]],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["worker_result_set_path"], worker_result_set)
    write_json(artifact_paths["normalized_inputs_path"], normalized_inputs)
    write_json(artifact_paths["overlap_diagnostics_path"], overlap_diagnostics)
    _write_text(artifact_paths["rendered_prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["parsed_output_path"], parsed_output)
    write_json(artifact_paths["aggregation_handoff_path"], aggregation_handoff)
    write_json(artifact_paths["repair_attempts_path"], repair_attempts)
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


def list_aggregation_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_aggregation_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir()
             and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_aggregation_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    repair_attempts_path = artifact_paths.get("repair_attempts_path")
    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "worker_result_set": load_json(artifact_paths["worker_result_set_path"]),
        "normalized_inputs": load_json(artifact_paths["normalized_inputs_path"]),
        "overlap_diagnostics": load_json(artifact_paths["overlap_diagnostics_path"]),
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "parsed_output": load_json(artifact_paths["parsed_output_path"]),
        "aggregation_handoff": load_json(artifact_paths["aggregation_handoff_path"]),
        "repair_attempts": load_json(repair_attempts_path) if repair_attempts_path else [],
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }
