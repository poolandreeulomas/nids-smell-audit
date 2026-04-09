"""Run one MVP agent session and persist logs and metrics."""

from __future__ import annotations

import json

from analysis.interpreter import extract_run_insights
from analysis.summarizer import generate_summary
from config import LOG_DIR
from main import main
from utils.metrics import state_metrics_payload
from utils.run_logging import load_json, save_run_artifacts


def _build_error_summary(final_state) -> list[dict[str, str | int | None]]:
    recent_errors = final_state.errors[-3:]
    return [
        {
            "step_id": error.get("step_id"),
            "error_code": error.get("error_code"),
            "error_message": error.get("error_message"),
        }
        for error in recent_errors
    ]


def _build_step_summary(final_state) -> list[dict[str, str | int | float | None]]:
    steps = []
    for step in final_state.history:
        observation = step.get("observation") or {}
        action_input = step.get("action_input") or {}
        steps.append(
            {
                "step_id": step.get("step_id"),
                "action": step.get("action"),
                "feature": action_input.get("feature_name"),
                "status": step.get("execution_status"),
                "value": observation.get("value"),
                "error_code": observation.get("error_code"),
            }
        )
    return steps


def run_mvp() -> dict[str, str]:
    """Execute one run through main wiring and save JSON artifacts."""
    final_state = main()
    metrics = state_metrics_payload(final_state)
    artifact_paths = save_run_artifacts(
        final_state,
        metrics,
        log_dir=LOG_DIR,
    )
    summary = {
        "artifacts": artifact_paths,
        "metrics": metrics,
        "summary": {
            "history_len": len(final_state.history),
            "errors_len": len(final_state.errors),
            "analyzed_feature_count": len(final_state.analyzed_features),
        },
        "steps": _build_step_summary(final_state),
        "recent_errors": _build_error_summary(final_state),
    }
    run_payload = load_json(artifact_paths["run_log_path"])
    insights = extract_run_insights(run_payload)
    interpreted_summary = generate_summary(insights)

    print(interpreted_summary)
    print()
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return artifact_paths


if __name__ == "__main__":
    run_mvp()
