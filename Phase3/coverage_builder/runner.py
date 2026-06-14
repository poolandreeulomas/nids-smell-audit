"""Execution wrapper for the Phase 3B Coverage Builder.

Flow:

    List of Partition Memory run directories
        ↓ (load each via load_partition_memory_bundle)
    List of Partition Memory dicts
        ↓ (aggregator.build_dataset_memory)
    Dataset Memory
        ↓
    Persist Artifacts
        ↓
    Return Results
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from coverage_builder.aggregator import build_dataset_memory
from coverage_builder.contracts import SCHEMA_VERSION
from coverage_builder.runtime_artifacts import (
    build_coverage_builder_artifact_paths,
    save_coverage_builder_artifacts,
)
from instrumentation import phase_start, phase_end
from partition_memory_extractor.runtime_artifacts import (
    load_partition_memory_bundle,
)


def run_coverage_builder(
    partition_memory_run_dirs: list[str | Path],
    dataset_id: str,
    *,
    log_dir: str | None = None,
) -> dict[str, Any]:
    """Build a Dataset Memory from a list of Partition Memory run directories.

    Flow:
        Load Partition Memory bundles
            ↓
        Aggregate into Dataset Memory
            ↓
        Persist Artifacts
            ↓
        Return Results

    Args:
        partition_memory_run_dirs: List of Partition Memory run directories.
        dataset_id: Human-readable dataset identifier (e.g. "CICIDS2017").
        log_dir: Optional log directory override.

    Returns:
        Dict with dataset_memory, runtime_metrics, artifact_paths.
    """
    request_id = f"coverage_builder_{uuid4().hex}"

    # Step 1: Load Partition Memory bundles
    partition_memories: list[dict[str, Any]] = []
    loaded_count = 0
    failed_count = 0
    for run_dir in partition_memory_run_dirs:
        try:
            bundle = load_partition_memory_bundle(str(run_dir))
            pm = bundle.get("partition_memory", {})
            if isinstance(pm, dict) and pm.get("partition_id"):
                partition_memories.append(pm)
                loaded_count += 1
            else:
                failed_count += 1
        except Exception:
            failed_count += 1

    batch_id = None
    # Attempt to derive batch_id from the first loaded partition memory
    if partition_memories:
        first_bundle = load_partition_memory_bundle(
            str(partition_memory_run_dirs[0])
        )
        batch_id = first_bundle.get("component_run", {}).get("batch_id")

    state_version = "deterministic"

    start_time = perf_counter()
    phase_start(
        "coverage_builder",
        batch_id=batch_id or dataset_id,
        state_version=state_version,
    )

    # Step 2: Aggregate
    total = len(partition_memory_run_dirs)
    try:
        dataset_memory = build_dataset_memory(
            partition_memories,
            partitions_available=total,
        )
        status = "ok"
    except Exception as exc:
        dataset_memory = {
            "execution_metadata": {
                "partitions_available": total,
                "partitions_completed": loaded_count,
                "partitions_failed": total - loaded_count,
            },
            "artifact_family_coverage": [],
            "finding_coverage": [],
            "partition_summaries": [],
            "global_signals": [],
            "error": str(exc),
        }
        status = "error"

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)

    phase_end(
        "coverage_builder",
        elapsed_s=duration_ms / 1000.0,
        batch_id=batch_id or dataset_id,
        state_version=state_version,
    )

    # Step 3: Build runtime metrics
    runtime_metrics = {
        "request_id": request_id,
        "dataset_id": dataset_id,
        "batch_id": batch_id or dataset_id,
        "schema_version": SCHEMA_VERSION,
        "duration_ms": duration_ms,
        "status": status,
        "partitions_available": total,
        "partitions_loaded": loaded_count,
        "partitions_failed": failed_count,
    }

    # Step 4: Build component run metadata
    component_run = {
        "component": "coverage_builder",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "status": status,
    }

    # Step 5: Persist artifacts
    artifact_paths = build_coverage_builder_artifact_paths(
        dataset_id=dataset_id,
        log_dir=log_dir,
    )
    persisted_paths = save_coverage_builder_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        dataset_memory=dataset_memory,
        runtime_metrics=runtime_metrics,
    )

    return {
        "dataset_memory": dataset_memory,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }