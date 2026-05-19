"""Validate a persisted MVP run log against baseline thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from utils.metrics import compute_run_metrics
from utils.run_logging import load_json


DEFAULT_THRESHOLDS = {
    "valid_action_rate": 0.80,
    "parse_error_rate": 0.20,
    "unique_features_explored": 3,
    "repeated_feature_rate": 0.30,
}


def _load_run_payload(run_path: str | Path) -> dict:
    return load_json(run_path)


def validate_run(run_path: str | Path) -> dict:
    payload = _load_run_payload(run_path)
    metrics = compute_run_metrics(payload)

    checks = {
        "valid_action_rate": metrics["valid_action_rate"] >= DEFAULT_THRESHOLDS["valid_action_rate"],
        "parse_error_rate": metrics["parse_error_rate"] <= DEFAULT_THRESHOLDS["parse_error_rate"],
        "unique_features_explored": metrics["unique_features_explored"] >= DEFAULT_THRESHOLDS["unique_features_explored"],
        "repeated_feature_rate": metrics["repeated_feature_rate"] <= DEFAULT_THRESHOLDS["repeated_feature_rate"],
    }
    return {
        "run_path": str(run_path),
        "metrics": metrics,
        "thresholds": DEFAULT_THRESHOLDS,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate one MVP run log.")
    parser.add_argument("run_path", help="Path to run JSON log file")
    args = parser.parse_args()

    result = validate_run(args.run_path)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
