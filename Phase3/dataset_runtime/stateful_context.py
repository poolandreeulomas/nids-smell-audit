"""Lightweight stateful context for dataset orchestration.

Tracks per-partition status through the lifecycle:
    pending → running → completed
    pending → running → failed → (retry once) → running → completed
    pending → running → failed → (retry once) → running → failed → skipped

Not responsible for:
- Partition discovery (assumed to already exist)
- Runtime orchestration logic
- Any state beyond simple tracking
"""

from __future__ import annotations

from typing import Optional

from dataset_runtime.models import PartitionResult, PartitionStatus


class DatasetRunStatefulContext:
    """Lightweight stateful context for dataset orchestration.

    Responsibilities:
    - Hold reference to partitions (immutable after construction)
    - Track per-partition status
    - Track attempts (initial + 1 retry = max 2 attempts per partition)
    - Provide helper methods for checking completion state
    - Expose partition metadata collection after run completes
    """

    def __init__(
        self,
        partitions: list[str],
        *,
        dataset_name: str,
        max_retries: int = 1,
    ) -> None:
        if not isinstance(partitions, list):
            raise TypeError("partitions must be a list of strings")
        self._dataset_name = str(dataset_name)
        self._max_retries = int(max_retries) if max_retries >= 0 else 1
        self._partitions: dict[str, PartitionResult] = {
            name: PartitionResult(
                partition_name=name,
                status=PartitionStatus.PENDING,
            )
            for name in partitions
        }
        self._partition_order: list[str] = list(partitions)

    # --- Partition status ---

    def get_next_partition_to_run(self) -> Optional[str]:
        """Return the next partition that should be executed.

        Priority:
        1. Partitions that need retry (failed with attempts remaining)
        2. Pending partitions (in original order)

        Returns None if all partitions are terminal.
        """
        # First: check for retry-able partitions
        for name in self._partition_order:
            result = self._partitions.get(name)
            if result is None:
                continue
            if result.status == PartitionStatus.FAILED and self.needs_retry(name):
                return name

        # Second: check for pending partitions
        for name in self._partition_order:
            result = self._partitions.get(name)
            if result is None:
                continue
            if result.status == PartitionStatus.PENDING:
                return name

        return None

    def start_partition(self, partition_name: str) -> None:
        """Mark a partition as running."""
        if partition_name not in self._partitions:
            raise KeyError(f"Unknown partition: {partition_name}")
        result = self._partitions[partition_name]
        result.status = PartitionStatus.RUNNING
        result.attempt_count += 1

    def complete_partition(self, partition_name: str) -> None:
        """Mark a partition as completed successfully."""
        if partition_name not in self._partitions:
            raise KeyError(f"Unknown partition: {partition_name}")
        self._partitions[partition_name].status = PartitionStatus.COMPLETED

    def fail_partition(self, partition_name: str) -> None:
        """Mark a partition as failed."""
        if partition_name not in self._partitions:
            raise KeyError(f"Unknown partition: {partition_name}")
        result = self._partitions[partition_name]
        result.status = PartitionStatus.FAILED
        result.retry_count += 1

    def skip_partition(self, partition_name: str) -> None:
        """Mark a partition as skipped (max retries exceeded)."""
        if partition_name not in self._partitions:
            raise KeyError(f"Unknown partition: {partition_name}")
        self._partitions[partition_name].status = PartitionStatus.SKIPPED

    def needs_retry(self, partition_name: str) -> bool:
        """Check if a partition should be retried.

        Returns True if the partition has failed and has not exceeded
        the retry budget (attempt_count <= max_retries means retry is allowed).
        """
        if partition_name not in self._partitions:
            return False
        result = self._partitions[partition_name]
        return (
            result.status == PartitionStatus.FAILED
            and result.attempt_count <= self._max_retries
        )

    # --- Status queries ---

    @property
    def overall_status(self) -> str:
        """Return overall run status (completed, partial, failed)."""
        if not self._partitions:
            return "completed"

        total = len(self._partitions)
        completed = sum(
            1 for r in self._partitions.values()
            if r.status == PartitionStatus.COMPLETED
        )
        failed = sum(
            1 for r in self._partitions.values()
            if r.status == PartitionStatus.FAILED
        )
        skipped = sum(
            1 for r in self._partitions.values()
            if r.status == PartitionStatus.SKIPPED
        )
        running = sum(
            1 for r in self._partitions.values()
            if r.status == PartitionStatus.RUNNING
        )

        if running > 0:
            return "running"
        if completed == total:
            return "completed"
        if completed > 0:
            return "partial"
        if failed == total or skipped == total:
            return "failed"
        if skipped > 0 and completed == 0:
            return "failed"
        return "pending"

    @property
    def completed_partitions(self) -> list[str]:
        """Return list of successfully completed partition names."""
        return [
            name for name, result in self._partitions.items()
            if result.status == PartitionStatus.COMPLETED
        ]

    @property
    def failed_partitions(self) -> list[str]:
        """Return list of failed partition names (not yet retried or skipped)."""
        return [
            name for name, result in self._partitions.items()
            if result.status == PartitionStatus.FAILED
        ]

    @property
    def skipped_partitions(self) -> list[str]:
        """Return list of skipped partition names (exhausted retries)."""
        return [
            name for name, result in self._partitions.items()
            if result.status == PartitionStatus.SKIPPED
        ]

    @property
    def partition_results(self) -> dict[str, PartitionResult]:
        """Return the full mapping of partition results."""
        return dict(self._partitions)

    @property
    def dataset_name(self) -> str:
        """Return the dataset name."""
        return self._dataset_name

    @property
    def total_partitions(self) -> int:
        """Return the total number of partitions."""
        return len(self._partitions)


def build_dataset_context(
    partitions: list[str],
    *,
    dataset_name: str,
    max_retries: int = 1,
) -> DatasetRunStatefulContext:
    """Factory function for DatasetRunStatefulContext.

    Args:
        partitions: List of partition names (assumed to already exist).
        dataset_name: Name of the dataset being processed.
        max_retries: Maximum number of retry attempts (default: 1).

    Returns:
        DatasetRunStatefulContext instance.
    """
    return DatasetRunStatefulContext(
        partitions=partitions,
        dataset_name=dataset_name,
        max_retries=max_retries,
    )