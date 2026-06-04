"""Artifact persistence for Final Batch Auditor component runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_FINAL_BATCH_AUDITOR_DIR = (
    Path(__file__).resolve().parent.parent / "logs" / "final_batch_auditor_runs"
)
_RUN_INDEX_PATTERN = re.compile(r"^final_batch_audit_run_(?P<index>\d{3})_")


def _format_batch_tag(batch_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(batch_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_batch"


def ensure_final_batch_auditor_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_FINAL_BATCH_AUDITOR_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_final_batch_auditor_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_final_batch_auditor_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_final_batch_auditor_run_basename(
    batch_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = (
        run_index if run_index is not None else get_next_final_batch_auditor_run_index(log_dir)
    )
    return "final_batch_audit_run_{index:03d}_{day_month}_{batch_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        batch_tag=_format_batch_tag(batch_id),
    )


def build_final_batch_auditor_artifact_paths(
    *,
    batch_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_final_batch_auditor_runs_dir(log_dir)
    run_dir = runs_dir / build_final_batch_auditor_run_basename(batch_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "final_audit_input_path": run_dir / "final_audit_input.json",
        "final_state_summary_path": run_dir / "final_state_summary.json",
        "round_history_summary_path": run_dir / "round_history_summary.json",
        "process_signal_summary_path": run_dir / "process_signal_summary.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "debugging_audit_report_path": run_dir / "debugging_audit_report.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_final_batch_auditor_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    final_audit_input: dict[str, Any],
    final_state_summary: dict[str, Any],
    round_history_summary: list[dict[str, Any]],
    process_signal_summary: dict[str, Any],
    rendered_prompt: str,
    raw_response: str,
    debugging_audit_report: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["final_audit_input_path"], final_audit_input)
    write_json(artifact_paths["final_state_summary_path"], final_state_summary)
    write_json(artifact_paths["round_history_summary_path"], round_history_summary)
    write_json(artifact_paths["process_signal_summary_path"], process_signal_summary)
    _write_text(artifact_paths["rendered_prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["debugging_audit_report_path"], debugging_audit_report)
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


def list_final_batch_auditor_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_final_batch_auditor_runs_dir(log_dir)
    paths = [
        path
        for path in runs_dir.iterdir()
        if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)
    ]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_final_batch_auditor_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})
    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "final_audit_input": load_json(artifact_paths["final_audit_input_path"]),
        "final_state_summary": load_json(artifact_paths["final_state_summary_path"]),
        "round_history_summary": load_json(artifact_paths["round_history_summary_path"]),
        "process_signal_summary": load_json(artifact_paths["process_signal_summary_path"]),
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "debugging_audit_report": load_json(artifact_paths["debugging_audit_report_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }
