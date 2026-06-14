"""Artifact persistence for Coverage Builder component runs.

Persists: dataset_memory.json, runtime_metrics.json.
No prompt or raw response — this component is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_COVERAGE_BUILDER_DIR = (
    Path(__file__).resolve().parent.parent / "logs" / "coverage_builder_runs"
)
_RUN_INDEX_PATTERN = re.compile(r"^coverage_builder_run_(?P<index>\d{3})_")


def _format_dataset_tag(dataset_id: str | None) -> str:
    normalized = re.sub(
        r"[^a-z0-9]+", "_", str(dataset_id or "").strip().lower()
    ).strip("_")
    return normalized[:40] or "unknown_dataset"


def ensure_coverage_builder_runs_dir(
    log_dir: str | Path | None = None,
) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_COVERAGE_BUILDER_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_coverage_builder_run_index(
    log_dir: str | Path | None = None,
) -> int:
    runs_dir = ensure_coverage_builder_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_coverage_builder_run_basename(
    dataset_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = (
        run_index
        if run_index is not None
        else get_next_coverage_builder_run_index(log_dir)
    )
    return "coverage_builder_run_{index:03d}_{day_month}_{dataset_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        dataset_tag=_format_dataset_tag(dataset_id),
    )


def build_coverage_builder_artifact_paths(
    *,
    dataset_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_coverage_builder_runs_dir(log_dir)
    run_dir = runs_dir / build_coverage_builder_run_basename(
        dataset_id, log_dir=log_dir
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "dataset_memory_path": run_dir / "dataset_memory.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
    }


def save_coverage_builder_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    dataset_memory: dict[str, Any],
    runtime_metrics: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["dataset_memory_path"], dataset_memory)
    write_json(artifact_paths["runtime_metrics_path"], runtime_metrics)

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


def list_coverage_builder_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_coverage_builder_runs_dir(log_dir)
    paths = [
        path
        for path in runs_dir.iterdir()
        if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)
    ]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_coverage_builder_bundle(
    run_dir: str | Path,
) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "dataset_memory": load_json(artifact_paths["dataset_memory_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
    }