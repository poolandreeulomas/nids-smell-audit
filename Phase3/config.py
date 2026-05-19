"""Global configuration for MVP agent project."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

MAX_STEPS = 10
# Keep these anchored to the repository root so CLI execution does not depend on cwd.
DATA_DIR = REPO_ROOT / "data" / "cic_ids_2017"
LOG_DIR = REPO_ROOT / "logs" / "runs"
