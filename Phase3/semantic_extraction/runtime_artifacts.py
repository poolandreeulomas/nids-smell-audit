"""Artifact persistence for Semantic Extraction component runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_SEMANTIC_EXTRACTION_DIR = Path(__file__).resolve().parent.parent / "logs" / "semantic_extraction_runs"
_RUN_INDEX_PATTERN = re.compile(r"^semantic_extraction_run_(?P<index>\d{3})_")


def _format_batch_tag(batch_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(batch_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_batch"


def ensure_semantic_extraction_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_SEMANTIC_EXTRACTION_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_semantic_extraction_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_semantic_extraction_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_semantic_extraction_run_basename(
    batch_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_semantic_extraction_run_index(log_dir)
    return "semantic_extraction_run_{index:03d}_{day_month}_{batch}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        batch=_format_batch_tag(batch_id),
    )


def build_semantic_extraction_artifact_paths(
    *,
    batch_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_semantic_extraction_runs_dir(log_dir)
    run_dir = runs_dir / build_semantic_extraction_run_basename(batch_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "overview_summary_min_path": run_dir / "overview_summary_min.json",
        "partition_context_path": run_dir / "partition_context.json",
        "projected_evidence_path": run_dir / "projected_evidence.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "parsed_output_path": run_dir / "parsed_output.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_semantic_extraction_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    overview_summary_min: dict[str, Any],
    partition_context: dict[str, Any],
    projected_evidence: dict[str, Any],
    rendered_prompt: str,
    raw_response: str,
    parsed_output: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any] | None = None,
) -> dict[str, str]:
    write_json(artifact_paths["overview_summary_min_path"], overview_summary_min)
    write_json(artifact_paths["partition_context_path"], partition_context)
    write_json(artifact_paths["projected_evidence_path"], projected_evidence)
    _write_text(artifact_paths["rendered_prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["parsed_output_path"], parsed_output)
    write_json(artifact_paths["validation_report_path"], validation_report)
    write_json(artifact_paths["runtime_metrics_path"], runtime_metrics)
    if replay_metadata is not None:
        write_json(artifact_paths["replay_metadata_path"], replay_metadata)

    component_payload = dict(component_run)
    component_payload["artifact_paths"] = {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir" and (key != "replay_metadata_path" or replay_metadata is not None)
    }
    write_json(artifact_paths["component_run_path"], component_payload)

    return {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir" and (key != "replay_metadata_path" or replay_metadata is not None)
    }


def list_semantic_extraction_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_semantic_extraction_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_semantic_extraction_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    replay_metadata_path = artifact_paths.get("replay_metadata_path")

    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "overview_summary_min": load_json(artifact_paths["overview_summary_min_path"]),
        "partition_context": load_json(artifact_paths["partition_context_path"]),
        "projected_evidence": load_json(artifact_paths["projected_evidence_path"]),
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "parsed_output": load_json(artifact_paths["parsed_output_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(replay_metadata_path) if replay_metadata_path else None,
    }