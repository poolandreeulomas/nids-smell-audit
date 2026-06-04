"""Authoritative orchestration helpers for the Phase 3A batch runtime."""

from __future__ import annotations

from phase3_runtime.contracts import SCHEMA_VERSION
from phase3_runtime.ledger import BatchLedger, FinalizationRecord, HypothesisExecutionRecord, RoundManifest
from phase3_runtime.orchestrator import run_phase3a_batch
from phase3_runtime.runtime_artifacts import (
    build_phase3a_runtime_artifact_paths,
    build_phase3a_runtime_run_basename,
    ensure_phase3a_runtime_runs_dir,
    get_next_phase3a_runtime_run_index,
    list_phase3a_runtime_run_dirs,
    load_phase3a_runtime_bundle,
    save_phase3a_runtime_artifacts,
)

__all__ = [
    "BatchLedger",
    "FinalizationRecord",
    "HypothesisExecutionRecord",
    "RoundManifest",
    "SCHEMA_VERSION",
    "build_phase3a_runtime_artifact_paths",
    "build_phase3a_runtime_run_basename",
    "ensure_phase3a_runtime_runs_dir",
    "get_next_phase3a_runtime_run_index",
    "list_phase3a_runtime_run_dirs",
    "load_phase3a_runtime_bundle",
    "run_phase3a_batch",
    "save_phase3a_runtime_artifacts",
]
