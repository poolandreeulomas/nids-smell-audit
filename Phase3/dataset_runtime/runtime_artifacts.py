"""Artifact types and persistence for dataset runs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from dataset_runtime.models import DatasetRunMetadata

logger = logging.getLogger(__name__)

DEFAULT_DATASET_RUNS_DIR = (
    Path(__file__).resolve().parent.parent / "logs" / "dataset_runtime_runs"
)


@dataclass
class SinglePartitionResult:
    """Result of a single partition's execution."""

    partition_name: str
    status: str
    final_state: Optional[Any] = None
    batch_report: Optional[str] = None
    partition_memory: Optional[dict] = None
    duration_seconds: float = 0.0
    attempt_count: int = 1
    is_retry: bool = False
    error_message: Optional[str] = None


@dataclass
class DatasetRuntimeArtifacts:
    """Artifacts produced during a dataset run."""

    run_id: str
    dataset_name: str
    started_at: Any  # datetime
    completed_at: Optional[Any] = None  # datetime
    total_partitions: int = 0
    completed_partitions: int = 0
    failed_partitions: int = 0
    skipped_partitions: int = 0
    partition_results: list[SinglePartitionResult] = field(default_factory=list)
    dataset_memory: Optional[dict] = None
    final_dataset_report: Optional[dict] = None
    overall_status: str = "pending"
    error_message: Optional[str] = None


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def build_dataset_run_path(
    run_id: str,
    *,
    log_dir: str | Path | None = None,
) -> Path:
    """Build the run directory path for a dataset execution run."""
    base = Path(log_dir) if log_dir else DEFAULT_DATASET_RUNS_DIR
    run_path = base / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def save_dataset_run_record(
    run_path: Path,
    artifacts: DatasetRuntimeArtifacts,
) -> dict[str, str]:
    """Save dataset runtime artifacts to disk.

    Produces:
        {run_path}/dataset_run_record.json  — structured run record
        {run_path}/dataset_memory.json      — dataset memory (if available)
        {run_path}/final_dataset_report.json — final report (if available)

    Args:
        run_path: Path to save the artifacts.
        artifacts: DatasetRuntimeArtifacts to persist.

    Returns:
        Dict mapping artifact keys to file paths.
    """
    run_path.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}

    # Build metadata record
    metadata = DatasetRunMetadata(
        run_id=artifacts.run_id,
        dataset_name=artifacts.dataset_name,
        started_at=artifacts.started_at,
        completed_at=artifacts.completed_at,
        total_partitions=artifacts.total_partitions,
        completion_status=artifacts.overall_status,
        partitions={},
    )

    # Save full run record (including partition results)
    record = {
        "run_id": artifacts.run_id,
        "dataset_name": artifacts.dataset_name,
        "started_at": artifacts.started_at.isoformat() if hasattr(artifacts.started_at, 'isoformat') else str(artifacts.started_at),
        "completed_at": artifacts.completed_at.isoformat() if artifacts.completed_at and hasattr(artifacts.completed_at, 'isoformat') else str(artifacts.completed_at or ""),
        "total_partitions": artifacts.total_partitions,
        "completed_partitions": artifacts.completed_partitions,
        "failed_partitions": artifacts.failed_partitions,
        "skipped_partitions": artifacts.skipped_partitions,
        "overall_status": artifacts.overall_status,
        "error_message": artifacts.error_message,
        "partition_results": [
            {
                "partition_name": r.partition_name,
                "status": r.status,
                "batch_report": r.batch_report,
                "partition_memory": r.partition_memory,
                "duration_seconds": r.duration_seconds,
                "attempt_count": r.attempt_count,
                "is_retry": r.is_retry,
                "error_message": r.error_message,
            }
            for r in artifacts.partition_results
        ],
        "dataset_memory": artifacts.dataset_memory,
        "final_dataset_report": artifacts.final_dataset_report,
    }

    record_path = run_path / "dataset_run_record.json"
    _write_text(record_path, json.dumps(record, indent=2, ensure_ascii=True, default=str))
    paths["dataset_run_record.json"] = str(record_path)

    # Save dataset memory separately if available
    if artifacts.dataset_memory:
        mem_path = run_path / "dataset_memory.json"
        _write_text(mem_path, json.dumps(artifacts.dataset_memory, indent=2, ensure_ascii=True, default=str))
        paths["dataset_memory.json"] = str(mem_path)

    # Save final dataset report separately if available
    if artifacts.final_dataset_report:
        report_path = run_path / "final_dataset_report.json"
        _write_text(report_path, json.dumps(artifacts.final_dataset_report, indent=2, ensure_ascii=True, default=str))
        paths["final_dataset_report.json"] = str(report_path)

    return paths


def load_dataset_run_record(run_path: Path) -> DatasetRuntimeArtifacts:
    """Load a dataset run record from disk.

    Args:
        run_path: Path to the run directory.

    Returns:
        DatasetRuntimeArtifacts instance.
    """
    record_file = run_path / "dataset_run_record.json"
    if not record_file.exists():
        raise FileNotFoundError(f"Dataset run record not found: {record_file}")

    raw = json.loads(record_file.read_text(encoding="utf-8"))

    partition_results = [
        SinglePartitionResult(
            partition_name=r.get("partition_name", ""),
            status=r.get("status", "unknown"),
            batch_report=r.get("batch_report"),
            partition_memory=r.get("partition_memory"),
            duration_seconds=r.get("duration_seconds", 0.0),
            attempt_count=r.get("attempt_count", 1),
            is_retry=r.get("is_retry", False),
            error_message=r.get("error_message"),
        )
        for r in raw.get("partition_results", [])
    ]

    return DatasetRuntimeArtifacts(
        run_id=raw.get("run_id", ""),
        dataset_name=raw.get("dataset_name", ""),
        started_at=raw.get("started_at", ""),
        completed_at=raw.get("completed_at"),
        total_partitions=raw.get("total_partitions", 0),
        completed_partitions=raw.get("completed_partitions", 0),
        failed_partitions=raw.get("failed_partitions", 0),
        skipped_partitions=raw.get("skipped_partitions", 0),
        partition_results=partition_results,
        dataset_memory=raw.get("dataset_memory"),
        final_dataset_report=raw.get("final_dataset_report"),
        overall_status=raw.get("overall_status", "unknown"),
        error_message=raw.get("error_message"),
    )