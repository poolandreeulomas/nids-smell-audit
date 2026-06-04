"""Artifact persistence for Investigation Analysis component runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_INVESTIGATION_ANALYSIS_DIR = Path(__file__).resolve().parent.parent / "logs" / "investigation_analysis_runs"
_RUN_INDEX_PATTERN = re.compile(r"^investigation_analysis_run_(?P<index>\d{3})_")


def _format_batch_tag(batch_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(batch_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_batch"


def ensure_investigation_analysis_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_INVESTIGATION_ANALYSIS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_investigation_analysis_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_investigation_analysis_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_investigation_analysis_run_basename(
    batch_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_investigation_analysis_run_index(log_dir)
    return "investigation_analysis_run_{index:03d}_{day_month}_{batch}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        batch=_format_batch_tag(batch_id),
    )


def build_investigation_analysis_artifact_paths(
    *,
    batch_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_investigation_analysis_runs_dir(log_dir)
    run_dir = runs_dir / build_investigation_analysis_run_basename(batch_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "semantic_substrate_path": run_dir / "semantic_substrate.json",
        "analysis_context_min_path": run_dir / "analysis_context_min.json",
        "analysis_iteration_context_min_path": run_dir / "analysis_iteration_context_min.json",
        "projected_substrate_path": run_dir / "projected_substrate.json",
        "projected_analysis_context_path": run_dir / "projected_analysis_context.json",
        "projected_iteration_context_path": run_dir / "projected_iteration_context.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "parsed_output_path": run_dir / "parsed_output.json",
        "hypothesis_index_path": run_dir / "hypothesis_index.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_investigation_analysis_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    semantic_substrate: dict[str, Any],
    analysis_context_min: dict[str, Any],
    analysis_iteration_context_min: dict[str, Any],
    projected_substrate: dict[str, Any],
    projected_analysis_context: dict[str, Any],
    projected_iteration_context: dict[str, Any],
    rendered_prompt: str,
    raw_response: str,
    parsed_output: dict[str, Any],
    hypothesis_index: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["semantic_substrate_path"], semantic_substrate)
    write_json(artifact_paths["analysis_context_min_path"], analysis_context_min)
    write_json(artifact_paths["analysis_iteration_context_min_path"], analysis_iteration_context_min)
    write_json(artifact_paths["projected_substrate_path"], projected_substrate)
    write_json(artifact_paths["projected_analysis_context_path"], projected_analysis_context)
    write_json(artifact_paths["projected_iteration_context_path"], projected_iteration_context)
    _write_text(artifact_paths["rendered_prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["parsed_output_path"], parsed_output)
    write_json(artifact_paths["hypothesis_index_path"], hypothesis_index)
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


def list_investigation_analysis_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_investigation_analysis_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_investigation_analysis_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})

    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "semantic_substrate": load_json(artifact_paths["semantic_substrate_path"]),
        "analysis_context_min": load_json(artifact_paths["analysis_context_min_path"]),
        "analysis_iteration_context_min": load_json(artifact_paths["analysis_iteration_context_min_path"]),
        "projected_substrate": load_json(artifact_paths["projected_substrate_path"]),
        "projected_analysis_context": load_json(artifact_paths["projected_analysis_context_path"]),
        "projected_iteration_context": load_json(artifact_paths["projected_iteration_context_path"]),
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "parsed_output": load_json(artifact_paths["parsed_output_path"]),
        "hypothesis_index": load_json(artifact_paths["hypothesis_index_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }