"""Run artifact persistence helpers for MVP sessions.

This module persists human-readable JSON logs for full run traces and
associated metrics.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from state.schema import AgentState
from state.store import state_to_dict


DEFAULT_RUNS_DIR = Path(__file__).resolve().parent.parent / "logs" / "runs"


def ensure_runs_dir(log_dir: str | Path | None = None) -> Path:
    """Ensure the runs directory exists and return it."""
    target = Path(log_dir) if log_dir else DEFAULT_RUNS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def build_run_basename(timestamp: datetime | None = None) -> str:
    """Build timestamp-based basename aligned with MVP plan."""
    ts = timestamp or datetime.now(UTC)
    return ts.strftime("run_%Y%m%d_%H%M%S_%f")


def build_run_log_payload(
    state: AgentState,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build full JSON payload for one run log."""
    payload = state_to_dict(state)
    payload["summary"] = {
        "history_len": len(state.history),
        "errors_len": len(state.errors),
        "analyzed_feature_count": len(state.analyzed_features),
        "promising_feature_count": len(state.promising_features),
    }
    if metrics is not None:
        payload["metrics"] = metrics
    return payload


def write_json(file_path: str | Path, payload: dict[str, Any]) -> Path:
    """Write JSON with indentation for easy inspection."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def save_run_artifacts(
    state: AgentState,
    metrics: dict[str, Any],
    log_dir: str | Path | None = None,
    basename: str | None = None,
) -> dict[str, str]:
    """Persist run log and metrics JSON files and return their paths."""
    runs_dir = ensure_runs_dir(log_dir)
    run_basename = basename or build_run_basename()

    run_log_path = runs_dir / f"{run_basename}.json"
    metrics_log_path = runs_dir / f"{run_basename}_metrics.json"

    run_payload = build_run_log_payload(state, metrics=metrics)
    metrics_payload = {
        "run_id": state.run_id,
        "objective": state.objective,
        "metadata": state.metadata,
        "metrics": metrics,
    }

    write_json(run_log_path, run_payload)
    write_json(metrics_log_path, metrics_payload)

    return {
        "run_log_path": str(run_log_path),
        "metrics_log_path": str(metrics_log_path),
    }


def load_json(file_path: str | Path) -> dict[str, Any]:
    """Load JSON file into memory."""
    return json.loads(Path(file_path).read_text(encoding="utf-8"))