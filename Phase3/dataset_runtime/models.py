"""Pydantic models for dataset run metadata."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class PartitionStatus(str, Enum):
    """Status of a partition's execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PartitionResult(BaseModel):
    """Result of a single partition execution."""

    partition_name: str
    status: PartitionStatus
    batch_report_path: Optional[str] = None
    partition_memory_path: Optional[str] = None
    attempt_count: int = 0
    retry_count: int = 0
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None


class DatasetRunMetadata(BaseModel):
    """Metadata for a complete dataset execution run."""

    run_id: str
    dataset_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_partitions: int = 0
    completion_status: str = "pending"
    partitions: dict[str, PartitionResult] = {}