"""Global configuration for MVP agent project."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

MAX_STEPS = 10
# DATA_DIR is the directory containing all dataset subdirectories.
# Each subdirectory (e.g. cic_ids_2017, UNSW_NB15) holds CSV partitions.
# Discovery is filesystem-based: any .csv/.tsv/.tab file under DATA_DIR
# is automatically treated as a selectable partition.
DATA_DIR = REPO_ROOT / "data"
LOG_DIR = REPO_ROOT / "logs" / "runs"