"""Run one MVP agent session and persist logs and metrics."""

from __future__ import annotations
from utils.metrics import state_metrics_payload
from utils.run_logging import save_run_artifacts
from main import main
from config import LOG_DIR

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_mvp() -> dict[str, str]:
    """Execute one run through main wiring and save JSON artifacts."""
    final_state = main()
    metrics = state_metrics_payload(final_state)
    artifact_paths = save_run_artifacts(
        final_state,
        metrics,
        log_dir=LOG_DIR,
    )
    print(json.dumps({"artifacts": artifact_paths,
          "metrics": metrics}, indent=2, ensure_ascii=True))
    return artifact_paths


if __name__ == "__main__":
    run_mvp()
