"""Load minimal prompt-layer context for CICIDS2017 partitions."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from judge.context_loader import resolve_judge_partition_phenomenon


_CONTEXT_DIR = Path(__file__).resolve().parent / "context" / "cicids2017"
_CURRENT_PARTITION_ENV = "NIDS_DATASET_PATH"


@lru_cache(maxsize=None)
def _read_context_file(name: str) -> str:
    path = _CONTEXT_DIR / f"{name}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _resolve_agent_phenomenon_name(partition_name: str) -> str | None:
    # Reuse the Judge phenomenon resolver through a narrow adapter so the
    # prompt layer stays aligned without depending on Judge prompt internals.
    return resolve_judge_partition_phenomenon(partition_name)


def get_current_agent_partition_name() -> str:
    # The current prompt-layer transport is an environment variable, but the
    # loader itself only operates on partition-name strings.
    return str(os.environ.get(_CURRENT_PARTITION_ENV, "") or "").strip()


def get_agent_partition_context(partition_name: str) -> str:
    phenomenon_name = _resolve_agent_phenomenon_name(partition_name)
    if not phenomenon_name:
        return ""
    return _read_context_file(phenomenon_name)
