"""Artifact persistence for Planner component runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_PLANNER_DIR = Path(__file__).resolve().parent.parent / "logs" / "planner_runs"
_RUN_INDEX_PATTERN = re.compile(r"^planner_run_(?P<index>\d{3})_")


def _format_round_tag(round_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(round_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_round"


def ensure_planner_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_PLANNER_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_planner_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_planner_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_planner_run_basename(
    round_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_planner_run_index(log_dir)
    return "planner_run_{index:03d}_{day_month}_{round_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        round_tag=_format_round_tag(round_id),
    )


def build_planner_artifact_paths(
    *,
    round_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_planner_runs_dir(log_dir)
    run_dir = runs_dir / build_planner_run_basename(round_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "ranking_decision_min_path": run_dir / "ranking_decision_min.json",
        "selected_hypothesis_context_path": run_dir / "selected_hypothesis_context.json",
        "planner_round_context_path": run_dir / "planner_round_context.json",
        "projected_selected_context_path": run_dir / "projected_selected_context.json",
        "projected_planner_round_context_path": run_dir / "projected_planner_round_context.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "parsed_output_path": run_dir / "parsed_output.json",
        "strategy_index_path": run_dir / "strategy_index.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_planner_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    ranking_decision_min: dict[str, Any],
    selected_hypothesis_context: dict[str, Any],
    planner_round_context: dict[str, Any],
    projected_selected_context: dict[str, Any],
    projected_planner_round_context: dict[str, Any],
    rendered_prompt: str,
    raw_response: str,
    parsed_output: dict[str, Any],
    strategy_index: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["ranking_decision_min_path"], ranking_decision_min)
    write_json(artifact_paths["selected_hypothesis_context_path"], selected_hypothesis_context)
    write_json(artifact_paths["planner_round_context_path"], planner_round_context)
    write_json(artifact_paths["projected_selected_context_path"], projected_selected_context)
    write_json(
        artifact_paths["projected_planner_round_context_path"],
        projected_planner_round_context,
    )
    _write_text(artifact_paths["rendered_prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["parsed_output_path"], parsed_output)
    write_json(artifact_paths["strategy_index_path"], strategy_index)
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


def list_planner_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_planner_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_planner_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})

    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "ranking_decision_min": load_json(artifact_paths["ranking_decision_min_path"]),
        "selected_hypothesis_context": load_json(artifact_paths["selected_hypothesis_context_path"]),
        "planner_round_context": load_json(artifact_paths["planner_round_context_path"]),
        "projected_selected_context": load_json(artifact_paths["projected_selected_context_path"]),
        "projected_planner_round_context": load_json(
            artifact_paths["projected_planner_round_context_path"]
        ),
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "parsed_output": load_json(artifact_paths["parsed_output_path"]),
        "strategy_index": load_json(artifact_paths["strategy_index_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }