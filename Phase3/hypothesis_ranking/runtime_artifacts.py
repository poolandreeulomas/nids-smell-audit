"""Artifact persistence for Hypothesis Ranking component runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from utils.run_logging import load_json, write_json


DEFAULT_HYPOTHESIS_RANKING_DIR = Path(__file__).resolve().parent.parent / "logs" / "hypothesis_ranking_runs"
_RUN_INDEX_PATTERN = re.compile(r"^hypothesis_ranking_run_(?P<index>\d{3})_")


def _format_round_tag(round_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(round_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_round"


def ensure_hypothesis_ranking_runs_dir(log_dir: str | Path | None = None) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_HYPOTHESIS_RANKING_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_next_hypothesis_ranking_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_hypothesis_ranking_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_hypothesis_ranking_run_basename(
    round_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_hypothesis_ranking_run_index(log_dir)
    return "hypothesis_ranking_run_{index:03d}_{day_month}_{round_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        round_tag=_format_round_tag(round_id),
    )


def build_hypothesis_ranking_artifact_paths(
    *,
    round_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_hypothesis_ranking_runs_dir(log_dir)
    run_dir = runs_dir / build_hypothesis_ranking_run_basename(round_id, log_dir=log_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "candidate_hypotheses_path": run_dir / "candidate_hypotheses.json",
        "ranking_state_snapshot_path": run_dir / "ranking_state_snapshot.json",
        "projected_candidate_context_path": run_dir / "projected_candidate_context.json",
        "projected_ranking_state_path": run_dir / "projected_ranking_state.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "parsed_output_path": run_dir / "parsed_output.json",
        "selection_index_path": run_dir / "selection_index.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def save_hypothesis_ranking_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    candidate_hypotheses: dict[str, Any],
    ranking_state_snapshot: dict[str, Any],
    projected_candidate_context: dict[str, Any],
    projected_ranking_state: dict[str, Any],
    rendered_prompt: str,
    raw_response: str,
    parsed_output: dict[str, Any],
    selection_index: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["candidate_hypotheses_path"], candidate_hypotheses)
    write_json(artifact_paths["ranking_state_snapshot_path"], ranking_state_snapshot)
    write_json(artifact_paths["projected_candidate_context_path"], projected_candidate_context)
    write_json(artifact_paths["projected_ranking_state_path"], projected_ranking_state)
    _write_text(artifact_paths["rendered_prompt_path"], rendered_prompt)
    _write_text(artifact_paths["raw_response_path"], raw_response)
    write_json(artifact_paths["parsed_output_path"], parsed_output)
    write_json(artifact_paths["selection_index_path"], selection_index)
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


def list_hypothesis_ranking_run_dirs(
    *,
    log_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[Path]:
    runs_dir = ensure_hypothesis_ranking_runs_dir(log_dir)
    paths = [path for path in runs_dir.iterdir() if path.is_dir() and _RUN_INDEX_PATTERN.match(path.name)]
    paths.sort(key=lambda path: path.name, reverse=True)
    if limit is not None:
        return paths[:limit]
    return paths


def load_hypothesis_ranking_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = component_run.get("artifact_paths", {})

    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "candidate_hypotheses": load_json(artifact_paths["candidate_hypotheses_path"]),
        "ranking_state_snapshot": load_json(artifact_paths["ranking_state_snapshot_path"]),
        "projected_candidate_context": load_json(artifact_paths["projected_candidate_context_path"]),
        "projected_ranking_state": load_json(artifact_paths["projected_ranking_state_path"]),
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "parsed_output": load_json(artifact_paths["parsed_output_path"]),
        "selection_index": load_json(artifact_paths["selection_index_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }