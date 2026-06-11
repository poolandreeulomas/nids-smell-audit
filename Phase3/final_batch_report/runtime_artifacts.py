"""Artifact persistence for Final Partition Audit Report Generator component runs.

Persists: report.md, prompt.txt, raw_response.txt, runtime_metrics.json.
Nothing else. Keep lightweight.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_FINAL_BATCH_REPORT_DIR = (
    Path(__file__).resolve().parent.parent / "logs" / "final_batch_report_runs"
)
_RUN_INDEX_PATTERN = re.compile(r"^final_batch_report_run_(?P<index>\d{3})_")


def _format_batch_tag(batch_id: str | None) -> str:
    normalized = re.sub(
        r"[^a-z0-9]+", "_", str(batch_id or "").strip().lower()
    ).strip("_")
    return normalized[:40] or "unknown_batch"


def ensure_final_batch_report_runs_dir(
    log_dir: str | Path | None = None,
) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_FINAL_BATCH_REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_final_batch_report_run_index(
    log_dir: str | Path | None = None,
) -> int:
    runs_dir = ensure_final_batch_report_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_final_batch_report_run_basename(
    batch_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = (
        run_index
        if run_index is not None
        else get_next_final_batch_report_run_index(log_dir)
    )
    return "final_batch_report_run_{index:03d}_{day_month}_{batch_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        batch_tag=_format_batch_tag(batch_id),
    )


def build_final_batch_report_artifact_paths(
    *,
    batch_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_final_batch_report_runs_dir(log_dir)
    run_dir = runs_dir / build_final_batch_report_run_basename(
        batch_id, log_dir=log_dir
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "report_path": run_dir / "report.md",
        "prompt_path": run_dir / "prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_final_batch_report_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    report_markdown: str,
    rendered_prompt: str,
    raw_response: str,
    runtime_metrics: dict[str, Any],
) -> dict[str, str]:
    _write_text(artifact_paths["report_path"], report_markdown)
    _write_text(artifact_paths["prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
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


def list_final_batch_report_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_final_batch_report_runs_dir(log_dir)
    paths = [
        path
        for path in runs_dir.iterdir()
        if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)
    ]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_final_batch_report_bundle(
    run_dir: str | Path,
) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "report_markdown": Path(artifact_paths["report_path"]).read_text(
            encoding="utf-8"
        ),
        "rendered_prompt": Path(artifact_paths["prompt_path"]).read_text(
            encoding="utf-8"
        ),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(
            encoding="utf-8"
        ),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
    }