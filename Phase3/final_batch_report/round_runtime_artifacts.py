"""Artifact persistence for Phase 3A Round-Level Final Reports.

Persists reports under logs/round_report_runs/ and links them to round manifests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_ROUND_REPORT_DIR = (
    Path(__file__).resolve().parent.parent / "logs" / "round_report_runs"
)
_RUN_INDEX_PATTERN = re.compile(r"^round_report_run_(?P<index>\d{3})_")


def _format_tag(text: str | None) -> str:
    normalized = re.sub(
        r"[^a-z0-9]+", "_", str(text or "").strip().lower()
    ).strip("_")
    return normalized[:30] or "unknown"


def ensure_round_report_runs_dir(
    log_dir: str | Path | None = None,
) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_ROUND_REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_round_report_run_index(
    log_dir: str | Path | None = None,
) -> int:
    runs_dir = ensure_round_report_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_round_report_run_basename(
    batch_id: str,
    round_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = (
        run_index
        if run_index is not None
        else get_next_round_report_run_index(log_dir)
    )
    return "round_report_run_{index:03d}_{day_month}_{batch_tag}_{round_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        batch_tag=_format_tag(batch_id),
        round_tag=_format_tag(round_id),
    )


def build_round_report_artifact_paths(
    *,
    batch_id: str,
    round_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_round_report_runs_dir(log_dir)
    run_dir = runs_dir / build_round_report_run_basename(
        batch_id, round_id, log_dir=log_dir
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "report_path": run_dir / "report.md",
        "prompt_path": run_dir / "prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "manifest_path": run_dir / "round_report_manifest.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_round_report_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    report_markdown: str,
    rendered_prompt: str,
    raw_response: str,
    runtime_metrics: dict[str, Any],
    round_manifest_path: str | Path | None = None,
) -> dict[str, str]:
    """Persist all round report artifacts and link with the source round manifest."""
    _write_text(artifact_paths["report_path"], report_markdown)
    _write_text(artifact_paths["prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["runtime_metrics_path"], runtime_metrics)

    report_manifest = {
        "component": "round_report",
        "created_at": datetime.now(UTC).isoformat(),
        "batch_id": component_run.get("batch_id"),
        "round_id": component_run.get("round_id"),
        "status": component_run.get("status"),
        "report_path": str(artifact_paths["report_path"]),
        "source_manifest_path": str(round_manifest_path or ""),
        "schema_version": component_run.get("schema_version"),
        "prompt_version": component_run.get("prompt_version"),
    }
    write_json(artifact_paths["manifest_path"], report_manifest)

    component_payload = dict(component_run)
    component_payload["artifact_paths"] = {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
    }
    write_json(artifact_paths["component_run_path"], component_payload)

    # Link back to source round manifest if accessible on disk
    if round_manifest_path:
        rm_file = Path(round_manifest_path)
        if rm_file.is_file():
            try:
                rm_data = load_json(rm_file)
                if isinstance(rm_data, dict):
                    rm_data["round_report_path"] = str(artifact_paths["report_path"])
                    rm_data["round_report_run_dir"] = str(artifact_paths["run_dir"])
                    write_json(rm_file, rm_data)
            except Exception:
                pass

    return {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
    }

