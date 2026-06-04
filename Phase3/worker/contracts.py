"""Contracts and defaults for the Phase 3A Worker runtime."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "phase3a.worker.v1"
DEFAULT_MAX_WORKER_STEPS = 8
DEFAULT_MAX_RETRIES = 1
VALID_WORKER_STATUSES = {
    "completed",
    "partial",
    "failed",
    "inconclusive",
}


def build_worker_output(
    *,
    batch_id: str,
    round_id: str,
    worker_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "batch_id": str(batch_id or "unknown_batch").strip() or "unknown_batch",
        "round_id": str(round_id or "unknown_round").strip() or "unknown_round",
        "worker_result": dict(worker_result or {}),
    }