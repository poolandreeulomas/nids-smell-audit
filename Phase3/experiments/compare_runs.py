"""Compare multiple MVP run logs using simple feature overlap and metrics."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

from utils.metrics import (
    compute_overlap_score,
    compute_run_metrics,
    extract_final_feature_list,
)
from utils.run_logging import load_json


def compare_runs(run_paths: list[str | Path]) -> dict:
    payloads = [(str(path), load_json(path)) for path in run_paths]
    runs = []
    for path, payload in payloads:
        metrics = compute_run_metrics(payload)
        final_features = extract_final_feature_list(payload)
        runs.append({
            "path": path,
            "run_id": payload.get("run_id"),
            "metrics": metrics,
            "final_features": final_features,
        })

    pairwise = []
    for left, right in combinations(runs, 2):
        overlap = compute_overlap_score(
            left["final_features"], right["final_features"])
        pairwise.append({
            "left": left["path"],
            "right": right["path"],
            "overlap_score": overlap,
            "left_features": left["final_features"],
            "right_features": right["final_features"],
        })

    average_overlap = (
        sum(item["overlap_score"] for item in pairwise) / len(pairwise)
        if pairwise else 1.0
    )
    return {
        "run_count": len(runs),
        "runs": runs,
        "pairwise": pairwise,
        "average_overlap_score": average_overlap,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare multiple MVP run logs.")
    parser.add_argument("run_paths", nargs="+",
                        help="Paths to run JSON log files")
    args = parser.parse_args()

    result = compare_runs(args.run_paths)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
