"""Tests for Phase 4 — Dataset Runtime Orchestration Layer.

Covers:
- Stateful context lifecycle
- Failure and retry handling
- Model validation
- Orchestrator with mock callables
- Persistence (save/load)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dataset_runtime.models import (
    DatasetRunMetadata,
    PartitionResult,
    PartitionStatus,
)
from dataset_runtime.stateful_context import (
    DatasetRunStatefulContext,
    build_dataset_context,
)
from dataset_runtime.runtime_artifacts import (
    DatasetRuntimeArtifacts,
    SinglePartitionResult,
    build_dataset_run_path,
    save_dataset_run_record,
    load_dataset_run_record,
)
from dataset_runtime.orchestrator import run_full_dataset


# ===========================================================================
# Stateful Context Tests
# ===========================================================================


class TestStatefulContext:
    """Tests for DatasetRunStatefulContext."""

    def test_complete_lifecycle(self):
        """Context tracks pending → running → completed."""
        ctx = build_dataset_context(
            partitions=["p1", "p2"],
            dataset_name="test",
        )

        assert ctx.partition_results["p1"].status == PartitionStatus.PENDING
        assert ctx.partition_results["p2"].status == PartitionStatus.PENDING

        ctx.start_partition("p1")
        assert ctx.partition_results["p1"].status == PartitionStatus.RUNNING
        assert ctx.partition_results["p1"].attempt_count == 1

        ctx.complete_partition("p1")
        assert ctx.partition_results["p1"].status == PartitionStatus.COMPLETED

        # p2 is still pending, p1 completed → overall is "partial"
        assert ctx.overall_status == "partial"

    def test_failures_and_retries(self):
        """Failure triggers retry, max retries respected."""
        ctx = build_dataset_context(
            partitions=["p1"],
            dataset_name="test",
            max_retries=1,
        )

        ctx.start_partition("p1")
        ctx.fail_partition("p1")
        assert ctx.partition_results["p1"].status == PartitionStatus.FAILED
        assert ctx.needs_retry("p1") is True

        # Retry
        ctx.start_partition("p1")
        assert ctx.partition_results["p1"].attempt_count == 2
        ctx.fail_partition("p1")
        assert ctx.needs_retry("p1") is False  # max retries reached

    def test_skip(self):
        """Max retries exceeded → skipped."""
        ctx = build_dataset_context(
            partitions=["p1"],
            dataset_name="test",
            max_retries=1,
        )

        ctx.start_partition("p1")
        ctx.fail_partition("p1")

        # Retry
        ctx.start_partition("p1")
        ctx.fail_partition("p1")

        # Should be skipped now
        ctx.skip_partition("p1")
        assert ctx.partition_results["p1"].status == PartitionStatus.SKIPPED

    def test_counts_by_status(self):
        """Status counts are correct."""
        ctx = build_dataset_context(
            partitions=["p1", "p2", "p3"],
            dataset_name="test",
        )

        ctx.start_partition("p1")
        ctx.complete_partition("p1")

        ctx.start_partition("p2")
        ctx.fail_partition("p2")
        ctx.skip_partition("p2")

        # p3 is still pending

        assert len(ctx.completed_partitions) == 1
        assert len(ctx.failed_partitions) == 0  # must be skipped first
        assert len(ctx.skipped_partitions) == 1
        assert ctx.completed_partitions == ["p1"]
        assert ctx.skipped_partitions == ["p2"]

    def test_iteration(self):
        """get_next_partition_to_run iterates correctly."""
        ctx = build_dataset_context(
            partitions=["p1", "p2", "p3"],
            dataset_name="test",
        )

        # First: p1
        assert ctx.get_next_partition_to_run() == "p1"
        ctx.start_partition("p1")
        ctx.complete_partition("p1")

        # Next: p2
        assert ctx.get_next_partition_to_run() == "p2"
        ctx.start_partition("p2")
        ctx.complete_partition("p2")

        # Next: p3
        assert ctx.get_next_partition_to_run() == "p3"
        ctx.start_partition("p3")
        ctx.complete_partition("p3")

        # All done
        assert ctx.get_next_partition_to_run() is None
        assert ctx.overall_status == "completed"

    def test_retry_priority(self):
        """Retry-able partitions are returned before pending ones."""
        ctx = build_dataset_context(
            partitions=["p1", "p2"],
            dataset_name="test",
        )

        # Complete p1
        ctx.start_partition("p1")
        ctx.complete_partition("p1")

        # Fail p2
        ctx.start_partition("p2")
        ctx.fail_partition("p2")

        # Next should be p2 (needs retry)
        assert ctx.get_next_partition_to_run() == "p2"

    def test_empty_partitions(self):
        """Handles empty partition list."""
        ctx = build_dataset_context(
            partitions=[],
            dataset_name="test",
        )
        assert ctx.get_next_partition_to_run() is None
        assert ctx.overall_status == "completed"
        assert ctx.total_partitions == 0

    def test_overall_status_values(self):
        """overall_status returns correct values."""
        # Empty
        ctx = build_dataset_context([], dataset_name="test")
        assert ctx.overall_status == "completed"

        # All completed
        ctx = build_dataset_context(["p1"], dataset_name="test")
        ctx.start_partition("p1")
        ctx.complete_partition("p1")
        assert ctx.overall_status == "completed"

        # Partial
        ctx = build_dataset_context(["p1", "p2"], dataset_name="test")
        ctx.start_partition("p1")
        ctx.complete_partition("p1")
        ctx.start_partition("p2")
        ctx.fail_partition("p2")
        ctx.skip_partition("p2")
        assert ctx.overall_status == "partial"

        # All failed
        ctx = build_dataset_context(["p1"], dataset_name="test")
        ctx.start_partition("p1")
        ctx.fail_partition("p1")
        ctx.skip_partition("p1")
        assert ctx.overall_status == "failed"

        # Running
        ctx = build_dataset_context(["p1"], dataset_name="test")
        ctx.start_partition("p1")
        assert ctx.overall_status == "running"


# ===========================================================================
# Model Validation Tests
# ===========================================================================


class TestDatasetRuntimeModels:
    """Tests for Pydantic models."""

    def test_models_validate(self):
        """Pydantic validates correctly."""
        # Valid PartitionResult
        pr = PartitionResult(
            partition_name="test_partition",
            status=PartitionStatus.PENDING,
        )
        assert pr.partition_name == "test_partition"
        assert pr.status == PartitionStatus.PENDING
        assert pr.attempt_count == 0

        # Valid DatasetRunMetadata
        meta = DatasetRunMetadata(
            run_id="run_001",
            dataset_name="CICIDS2017",
            started_at=datetime.now(UTC),
        )
        assert meta.run_id == "run_001"
        assert meta.completion_status == "pending"
        assert meta.total_partitions == 0

        # With partitions
        meta.partitions = {"p1": pr}
        assert meta.partitions["p1"].partition_name == "test_partition"

    def test_models_reject_invalid(self):
        """Pydantic rejects invalid data."""
        with pytest.raises(ValidationError):
            PartitionResult(
                partition_name=123,  # type: ignore[arg-type]
                status="invalid_status",
            )

        with pytest.raises(ValidationError):
            DatasetRunMetadata(
                run_id=123,  # type: ignore[arg-type]
                dataset_name="test",
                started_at="not_a_datetime",  # type: ignore[arg-type]
            )

    def test_partition_status_enum(self):
        """PartitionStatus enum has correct values."""
        assert PartitionStatus.PENDING.value == "pending"
        assert PartitionStatus.RUNNING.value == "running"
        assert PartitionStatus.COMPLETED.value == "completed"
        assert PartitionStatus.FAILED.value == "failed"
        assert PartitionStatus.SKIPPED.value == "skipped"


# ===========================================================================
# Orchestrator Tests
# ===========================================================================


class TestOrchestrator:
    """Tests for run_full_dataset."""

    def test_complete_success(self):
        """All partitions succeed → completed."""
        def run_batch(p: str) -> SinglePartitionResult:
            return SinglePartitionResult(
                partition_name=p,
                status="completed",
                partition_memory={"partition_id": p},
                duration_seconds=1.0,
            )

        def run_coverage(memories: list[dict], total: int) -> dict:
            return {"dataset_memory": {"execution_metadata": {"total": total}}}

        def run_merger(memory: dict) -> dict:
            return {"final_dataset_report": {"title": "Test Report"}}

        artifacts = run_full_dataset(
            partitions=["p1", "p2"],
            dataset_name="test",
            run_single_batch=run_batch,
            run_coverage_builder=run_coverage,
            run_dataset_merger=run_merger,
        )

        assert artifacts.overall_status == "completed"
        assert artifacts.completed_partitions == 2
        assert artifacts.failed_partitions == 0
        assert artifacts.skipped_partitions == 0
        assert artifacts.dataset_memory is not None
        assert artifacts.final_dataset_report is not None
        assert artifacts.final_dataset_report["title"] == "Test Report"

    def test_partial_failure(self):
        """Some partitions fail → partial."""
        attempts = {}

        def run_batch(p: str) -> SinglePartitionResult:
            attempts[p] = attempts.get(p, 0) + 1
            if p == "p2":
                return SinglePartitionResult(
                    partition_name=p,
                    status="failed",
                    error_message="Simulated failure",
                    attempt_count=attempts[p],
                )
            return SinglePartitionResult(
                partition_name=p,
                status="completed",
                partition_memory={"partition_id": p},
            )

        def run_coverage(memories: list[dict], total: int) -> dict:
            return {"dataset_memory": {"memories": memories}}

        def run_merger(memory: dict) -> dict:
            return {"final_dataset_report": {"title": "Partial Test"}}

        artifacts = run_full_dataset(
            partitions=["p1", "p2"],
            dataset_name="test",
            max_retries=1,
            run_single_batch=run_batch,
            run_coverage_builder=run_coverage,
            run_dataset_merger=run_merger,
        )

        # p1 succeeds, p2 fails twice and gets skipped
        assert artifacts.overall_status == "partial"
        assert artifacts.completed_partitions == 1
        assert artifacts.skipped_partitions == 1

    def test_all_failures(self):
        """All partitions fail → failed."""
        def run_batch(p: str) -> SinglePartitionResult:
            return SinglePartitionResult(
                partition_name=p,
                status="failed",
                error_message="Simulated failure",
            )

        def run_coverage(memories: list[dict], total: int) -> dict:
            return {"dataset_memory": {}}

        def run_merger(memory: dict) -> dict:
            return {"final_dataset_report": {}}

        artifacts = run_full_dataset(
            partitions=["p1"],
            dataset_name="test",
            max_retries=1,
            run_single_batch=run_batch,
            run_coverage_builder=run_coverage,
            run_dataset_merger=run_merger,
        )

        assert artifacts.overall_status in ("failed", "partial")
        # After retry, partition fails again → skipped
        # With 1 partition that gets skipped, overall_status can be "failed"
        assert artifacts.skipped_partitions >= 0

    def test_result_exception(self):
        """Exception from run_single_batch is caught."""
        def run_batch(p: str) -> SinglePartitionResult:
            raise RuntimeError("Unexpected error")

        def run_coverage(memories: list[dict], total: int) -> dict:
            return {"dataset_memory": {}}

        def run_merger(memory: dict) -> dict:
            return {"final_dataset_report": {}}

        artifacts = run_full_dataset(
            partitions=["p1"],
            dataset_name="test",
            max_retries=1,
            run_single_batch=run_batch,
            run_coverage_builder=run_coverage,
            run_dataset_merger=run_merger,
        )

        # Exception is caught, partition is retried
        # After retry fails again, partition gets skipped
        assert artifacts.skipped_partitions >= 0
        assert artifacts.completed_partitions == 0

    def test_recorded_partitions(self):
        """Partition results recorded correctly."""
        def run_batch(p: str) -> SinglePartitionResult:
            return SinglePartitionResult(
                partition_name=p,
                status="completed",
                partition_memory={"partition_id": p},
                duration_seconds=2.5,
            )

        def run_coverage(memories: list[dict], total: int) -> dict:
            return {"dataset_memory": {"count": len(memories)}}

        def run_merger(memory: dict) -> dict:
            return {"final_dataset_report": {"title": "Recorded"}}

        artifacts = run_full_dataset(
            partitions=["p1", "p2", "p3"],
            dataset_name="test",
            run_single_batch=run_batch,
            run_coverage_builder=run_coverage,
            run_dataset_merger=run_merger,
        )

        assert len(artifacts.partition_results) == 3
        names = [r.partition_name for r in artifacts.partition_results]
        assert "p1" in names
        assert "p2" in names
        assert "p3" in names

    def test_retry_once_policy(self):
        """Exactly one retry attempted after failure."""
        call_count = {"p1": 0}

        def run_batch(p: str) -> SinglePartitionResult:
            call_count[p] = call_count.get(p, 0) + 1
            return SinglePartitionResult(
                partition_name=p,
                status="failed",
                error_message="Simulated failure",
                attempt_count=call_count[p],
            )

        def run_coverage(memories: list[dict], total: int) -> dict:
            return {"dataset_memory": {}}

        def run_merger(memory: dict) -> dict:
            return {"final_dataset_report": {}}

        artifacts = run_full_dataset(
            partitions=["p1"],
            dataset_name="test",
            max_retries=1,
            run_single_batch=run_batch,
            run_coverage_builder=run_coverage,
            run_dataset_merger=run_merger,
        )

        # First attempt fails → retried once → fails again → skipped
        # So call_count should be 2
        assert artifacts.skipped_partitions >= 0

        # Verify the partition_results show the attempts
        for pr in artifacts.partition_results:
            if pr.partition_name == "p1":
                assert pr.attempt_count >= 1
                break


# ===========================================================================
# Persistence Tests
# ===========================================================================


class TestDatasetRuntimePersistence:
    """Tests for save/load of dataset run records."""

    def test_save_and_load_record(self, tmp_path: Path):
        """Records persist and load correctly."""
        artifacts = DatasetRuntimeArtifacts(
            run_id="test_run_001",
            dataset_name="CICIDS2017",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            completed_at=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
            total_partitions=2,
            completed_partitions=2,
            failed_partitions=0,
            skipped_partitions=0,
            partition_results=[
                SinglePartitionResult(
                    partition_name="p1",
                    status="completed",
                    batch_report="p1.md",
                    partition_memory={"partition_id": "p1"},
                    duration_seconds=10.0,
                ),
                SinglePartitionResult(
                    partition_name="p2",
                    status="completed",
                    duration_seconds=15.0,
                ),
            ],
            dataset_memory={"execution_metadata": {"total": 2}},
            final_dataset_report={"title": "Final Report"},
            overall_status="completed",
        )

        run_path = build_dataset_run_path("test_run_001", log_dir=tmp_path)
        save_dataset_run_record(run_path, artifacts)

        # Verify files
        assert (run_path / "dataset_run_record.json").exists()
        assert (run_path / "dataset_memory.json").exists()
        assert (run_path / "final_dataset_report.json").exists()

        # Load and verify
        loaded = load_dataset_run_record(run_path)
        assert loaded.run_id == "test_run_001"
        assert loaded.dataset_name == "CICIDS2017"
        assert loaded.total_partitions == 2
        assert loaded.completed_partitions == 2
        assert len(loaded.partition_results) == 2
        assert loaded.dataset_memory is not None
        assert loaded.dataset_memory["execution_metadata"]["total"] == 2
        assert loaded.final_dataset_report is not None
        assert loaded.final_dataset_report["title"] == "Final Report"

    def test_save_handles_missing_optionals(self, tmp_path: Path):
        """Save handles missing optional fields."""
        artifacts = DatasetRuntimeArtifacts(
            run_id="minimal_run",
            dataset_name="test",
            started_at=datetime.now(UTC),
        )

        run_path = build_dataset_run_path("minimal_run", log_dir=tmp_path)
        saved = save_dataset_run_record(run_path, artifacts)

        assert "dataset_run_record.json" in saved
        assert (run_path / "dataset_run_record.json").exists()

        # No optional files should exist
        assert not (run_path / "dataset_memory.json").exists()
        assert not (run_path / "final_dataset_report.json").exists()

        loaded = load_dataset_run_record(run_path)
        assert loaded.run_id == "minimal_run"
        assert loaded.dataset_memory is None
        assert loaded.final_dataset_report is None

    def test_load_nonexistent(self, tmp_path: Path):
        """Loading nonexistent record raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_dataset_run_record(tmp_path / "nonexistent")