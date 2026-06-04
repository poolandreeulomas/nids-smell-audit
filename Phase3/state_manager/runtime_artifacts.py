"""Artifact persistence for State Manager component runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_STATE_MANAGER_DIR = Path(__file__).resolve().parent.parent / "logs" / "state_manager_runs"
_RUN_INDEX_PATTERN = re.compile(r"^state_manager_run_(?P<index>\d{3})_")


def _format_hypothesis_tag(hypothesis_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(hypothesis_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_hypothesis"


def ensure_state_manager_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_STATE_MANAGER_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_state_manager_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_state_manager_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_state_manager_run_basename(
    hypothesis_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_state_manager_run_index(log_dir)
    return "state_manager_run_{index:03d}_{day_month}_{hypothesis_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        hypothesis_tag=_format_hypothesis_tag(hypothesis_id),
    )


def build_state_manager_artifact_paths(
    *,
    hypothesis_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_state_manager_runs_dir(log_dir)
    run_dir = runs_dir / build_state_manager_run_basename(hypothesis_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "prior_state_path": run_dir / "prior_state.json",
        "aggregation_handoff_path": run_dir / "aggregation_handoff.json",
        "state_manager_context_path": run_dir / "state_manager_context.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "state_delta_record_path": run_dir / "state_delta_record.json",
        "updated_batch_state_path": run_dir / "updated_batch_state.json",
        "state_update_result_path": run_dir / "state_update_result.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_state_manager_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    prior_state: dict[str, Any],
    aggregation_handoff: dict[str, Any],
    state_manager_context: dict[str, Any],
    rendered_prompt: str,
    raw_response: str,
    state_delta_record: dict[str, Any],
    updated_batch_state: dict[str, Any],
    state_update_result: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["prior_state_path"], prior_state)
    write_json(artifact_paths["aggregation_handoff_path"], aggregation_handoff)
    write_json(artifact_paths["state_manager_context_path"], state_manager_context)
    _write_text(artifact_paths["rendered_prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["state_delta_record_path"], state_delta_record)
    write_json(artifact_paths["updated_batch_state_path"], updated_batch_state)
    write_json(artifact_paths["state_update_result_path"], state_update_result)
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


def list_state_manager_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_state_manager_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_state_manager_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "prior_state": load_json(artifact_paths["prior_state_path"]),
        "aggregation_handoff": load_json(artifact_paths["aggregation_handoff_path"]),
        "state_manager_context": load_json(artifact_paths["state_manager_context_path"]),
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "state_delta_record": load_json(artifact_paths["state_delta_record_path"]),
        "updated_batch_state": load_json(artifact_paths["updated_batch_state_path"]),
        "state_update_result": load_json(artifact_paths["state_update_result_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }