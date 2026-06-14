"""Dataset Runtime Orchestrator.

The main orchestration layer that coordinates execution across all partitions.

Flow:
    For each partition:
        run_single_batch(partition_name)  ← injected callable
            ↓ (returns SinglePartitionResult)
        Collect partition results
    ↓
    Coverage Builder ← collects all partition memories
    ↓
    Dataset Memory
    ↓
    Dataset Merger ← produces Final Dataset Report
    ↓
    DatasetRuntimeArtifacts (full trace + persistence)

Failure policy:
    - Partition fails → retry once
    - Partition fails again → record failure, skip partition
    - Continue with remaining partitions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from dataset_runtime.models import PartitionStatus
from dataset_runtime.runtime_artifacts import (
    DatasetRuntimeArtifacts,
    SinglePartitionResult,
    build_dataset_run_path,
    save_dataset_run_record,
)
from dataset_runtime.stateful_context import (
    DatasetRunStatefulContext,
    build_dataset_context,
)

logger = logging.getLogger(__name__)


def run_partition(
    partition_name: str,
    *,
    mode: str = "regular",  # "regular" or "retry"
) -> SinglePartitionResult:
    """Execute a single partition through the full pipeline.

    Note: This function signature matches the implementation plan.
    The actual per-partition logic is expected to be injected through
    the run_single_batch callable passed to run_full_dataset.

    Args:
        partition_name: Name of the partition to run.
        mode: Execution mode ("regular" or "retry").

    Returns:
        SinglePartitionResult with execution details.
    """
    # This function serves as a placeholder/default that wraps
    # the callable injection pattern. The real per-partition execution
    # is delegated to the run_single_batch callable.
    return SinglePartitionResult(
        partition_name=partition_name,
        status="pending",
    )


def run_full_dataset(
    partitions: list[str],
    *,
    dataset_name: str = "CICIDS2017",
    max_retries: int = 1,
    run_single_batch: Callable[[str], SinglePartitionResult],
    run_coverage_builder: Callable[
        [list[dict[str, Any]], int], dict[str, Any]
    ],
    run_dataset_merger: Callable[[dict[str, Any]], dict[str, Any]],
    log_dir: str | Path | None = None,
) -> DatasetRuntimeArtifacts:
    """Execute the full dataset pipeline across partitions.

    Flow:
        For each partition:
            Run Full Batch
                ↓
            Run Partition Memory Extractor
                ↓
        Coverage Builder
            ↓
        Dataset Merger
            ↓
        Save Final Dataset Report

    Args:
        partitions: List of partition names (assumed to already exist).
        dataset_name: Name of the dataset being processed.
        max_retries: Maximum number of retry attempts (default: 1).
        run_single_batch: Callable that executes a single partition's full
            pipeline (Phase 3A + Partition Memory Extractor) and returns
            a SinglePartitionResult.
        run_coverage_builder: Callable that takes a list of partition
            memories and total partition count, returns dataset memory.
        run_dataset_merger: Callable that takes dataset memory and returns
            final dataset report.
        log_dir: Optional log directory for persisting run artifacts.

    Returns:
        DatasetRuntimeArtifacts with full run trace.
    """
    started_at = datetime.now(UTC)
    run_id = f"dataset_run_{started_at.strftime('%Y%m%d_%H%M%S')}"

    artifacts = DatasetRuntimeArtifacts(
        run_id=run_id,
        dataset_name=dataset_name,
        started_at=started_at,
        total_partitions=len(partitions),
    )

    # Step 1: Build stateful context
    ctx = build_dataset_context(
        partitions,
        dataset_name=dataset_name,
        max_retries=max_retries,
    )

    # Step 2: Execute each partition (with retry)
    while True:
        partition_name = ctx.get_next_partition_to_run()
        if partition_name is None:
            break

        is_retry = ctx.partition_results[partition_name].status == PartitionStatus.FAILED
        mode = "retry" if is_retry else "regular"

        ctx.start_partition(partition_name)
        logger.info(
            "Executing partition %s (mode=%s, attempt=%d)",
            partition_name,
            mode,
            ctx.partition_results[partition_name].attempt_count,
        )

        try:
            result = run_single_batch(partition_name)

            if result.status == "completed":
                ctx.complete_partition(partition_name)
                artifacts.partition_results.append(result)
                artifacts.completed_partitions += 1
                logger.info("Partition %s completed successfully", partition_name)
            else:
                # Execution returned but not successful
                ctx.fail_partition(partition_name)
                _handle_failure(
                    ctx, partition_name, result.error_message
                )
                artifacts.partition_results.append(result)

        except Exception as exc:
            error_msg = str(exc)
            logger.warning(
                "Partition %s failed: %s", partition_name, error_msg
            )
            ctx.fail_partition(partition_name)
            _handle_failure(
                ctx, partition_name, error_msg
            )

    # Step 3: Update partition counts from final context state
    artifacts.completed_partitions = len(ctx.completed_partitions)
    artifacts.failed_partitions = len(ctx.failed_partitions)
    artifacts.skipped_partitions = len(ctx.skipped_partitions)

    # Step 4: Run Coverage Builder if any partitions completed
    partition_memories: list[dict[str, Any]] = []
    for pr in artifacts.partition_results:
        if pr.status == "completed" and pr.partition_memory is not None:
            partition_memories.append(pr.partition_memory)

    if partition_memories:
        try:
            coverage_result = run_coverage_builder(
                partition_memories,
                len(partitions),
            )
            artifacts.dataset_memory = coverage_result.get("dataset_memory")
            logger.info(
                "Coverage builder completed: %d partition memories processed",
                len(partition_memories),
            )
        except Exception as exc:
            artifacts.error_message = f"Coverage builder failed: {exc}"
            logger.error("Coverage builder failed: %s", exc)

    # Step 5: Run Dataset Merger if dataset memory is available
    if artifacts.dataset_memory is not None:
        try:
            merger_result = run_dataset_merger(artifacts.dataset_memory)
            artifacts.final_dataset_report = merger_result.get("final_dataset_report")
            logger.info("Dataset merger completed successfully")
        except Exception as exc:
            logger.error("Dataset merger failed: %s", exc)
            if artifacts.error_message:
                artifacts.error_message += f"; Dataset merger failed: {exc}"
            else:
                artifacts.error_message = f"Dataset merger failed: {exc}"

    # Step 6: Finalize
    artifacts.overall_status = ctx.overall_status
    artifacts.completed_at = datetime.now(UTC)

    # Step 7: Persist
    if log_dir or True:  # always persist
        run_path = build_dataset_run_path(run_id, log_dir=log_dir)
        save_dataset_run_record(run_path, artifacts)
        logger.info(
            "Dataset run %s saved to %s", run_id, run_path
        )

    return artifacts


def _handle_failure(
    ctx: DatasetRunStatefulContext,
    partition_name: str,
    error_message: str | None,
) -> None:
    """Handle a partition failure with retry logic."""
    result = ctx.partition_results[partition_name]
    if error_message:
        result.error_message = error_message

    if ctx.needs_retry(partition_name):
        logger.info(
            "Partition %s will be retried (attempt %d/%d)",
            partition_name,
            result.attempt_count,
            ctx._max_retries if hasattr(ctx, '_max_retries') else 1,
        )
    else:
        ctx.skip_partition(partition_name)
        logger.warning(
            "Partition %s skipped after %d attempt(s)",
            partition_name,
            result.attempt_count,
        )