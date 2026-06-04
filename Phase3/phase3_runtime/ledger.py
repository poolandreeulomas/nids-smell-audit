"""Batch-ledger schema for the authoritative Phase 3A runtime."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any


def _ensure_json_primitive(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, bool, int, float)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_ensure_json_primitive(value) for value in obj]
    if isinstance(obj, dict):
        return {str(key): _ensure_json_primitive(value) for key, value in obj.items()}
    return str(obj)


def _string_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        stripped = _string_value(value)
        if stripped:
            normalized.append(stripped)
    return normalized


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _dict_list(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return [dict(item) for item in values if isinstance(item, dict)]


@dataclass
class HypothesisExecutionRecord:
    hypothesis_id: str
    planner_strategy_id: str = ""
    router_run_path: str = ""
    task_ids: list[str] = field(default_factory=list)
    worker_run_paths: list[str] = field(default_factory=list)
    aggregation_run_path: str = ""
    state_manager_run_path: str = ""
    start_state_version: int = 0
    end_state_version: int = 0
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "HypothesisExecutionRecord":
        raw = payload or {}
        return cls(
            hypothesis_id=_string_value(raw.get("hypothesis_id")),
            planner_strategy_id=_string_value(raw.get("planner_strategy_id")),
            router_run_path=_string_value(raw.get("router_run_path")),
            task_ids=_string_list(raw.get("task_ids")),
            worker_run_paths=_string_list(raw.get("worker_run_paths")),
            aggregation_run_path=_string_value(raw.get("aggregation_run_path")),
            state_manager_run_path=_string_value(raw.get("state_manager_run_path")),
            start_state_version=_int_value(raw.get("start_state_version")),
            end_state_version=_int_value(raw.get("end_state_version")),
            status=_string_value(raw.get("status")) or "pending",
        )


@dataclass
class RoundManifest:
    round_id: str
    round_index: int
    analysis_mode: str = "initial"
    analysis_run_path: str = ""
    frozen_snapshot_path: str = ""
    global_aggregation_path: str = ""
    ranking_run_path: str = ""
    planner_run_path: str = ""
    selected_hypothesis_ids: list[str] = field(default_factory=list)
    deferred_hypothesis_ids: list[str] = field(default_factory=list)
    start_state_version: int = 0
    end_state_version: int = 0
    status: str = "pending"
    terminal_reason: str = ""
    critic_run_path: str = ""
    hypothesis_runs: list[HypothesisExecutionRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RoundManifest":
        raw = payload or {}
        hypothesis_runs = [
            HypothesisExecutionRecord.from_dict(item)
            for item in _dict_list(raw.get("hypothesis_runs"))
        ]
        return cls(
            round_id=_string_value(raw.get("round_id")),
            round_index=_int_value(raw.get("round_index")),
            analysis_mode=_string_value(raw.get("analysis_mode")) or "initial",
            analysis_run_path=_string_value(raw.get("analysis_run_path")),
            frozen_snapshot_path=_string_value(raw.get("frozen_snapshot_path")),
            global_aggregation_path=_string_value(raw.get("global_aggregation_path")),
            ranking_run_path=_string_value(raw.get("ranking_run_path")),
            planner_run_path=_string_value(raw.get("planner_run_path")),
            selected_hypothesis_ids=_string_list(raw.get("selected_hypothesis_ids")),
            deferred_hypothesis_ids=_string_list(raw.get("deferred_hypothesis_ids")),
            start_state_version=_int_value(raw.get("start_state_version")),
            end_state_version=_int_value(raw.get("end_state_version")),
            status=_string_value(raw.get("status")) or "pending",
            terminal_reason=_string_value(raw.get("terminal_reason")),
            critic_run_path=_string_value(raw.get("critic_run_path")),
            hypothesis_runs=hypothesis_runs,
        )


@dataclass
class FinalizationRecord:
    terminal_reason: str = ""
    final_state_manager_run_path: str = ""
    final_batch_auditor_run_path: str = ""
    final_state_version: int = 0
    final_status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "FinalizationRecord":
        raw = payload or {}
        return cls(
            terminal_reason=_string_value(raw.get("terminal_reason")),
            final_state_manager_run_path=_string_value(raw.get("final_state_manager_run_path")),
            final_batch_auditor_run_path=_string_value(raw.get("final_batch_auditor_run_path")),
            final_state_version=_int_value(raw.get("final_state_version")),
            final_status=_string_value(raw.get("final_status")) or "pending",
        )


@dataclass
class BatchLedger:
    batch_id: str
    dataset_path: str
    model_name: str
    max_rounds: int
    critic_enabled: bool = False
    status: str = "pending"
    created_at: str = ""
    completed_at: str = ""
    semantic_extraction_run_path: str = ""
    initial_investigation_analysis_run_path: str = ""
    initial_state_path: str = ""
    initial_state_version: int = 0
    round_manifests: list[RoundManifest] = field(default_factory=list)
    finalization: FinalizationRecord = field(default_factory=FinalizationRecord)

    def to_dict(self) -> dict[str, Any]:
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "BatchLedger":
        raw = payload or {}
        manifests = [RoundManifest.from_dict(item) for item in _dict_list(raw.get("round_manifests"))]
        finalization = FinalizationRecord.from_dict(
            raw.get("finalization") if isinstance(raw.get("finalization"), dict) else {}
        )
        return cls(
            batch_id=_string_value(raw.get("batch_id")),
            dataset_path=_string_value(raw.get("dataset_path")),
            model_name=_string_value(raw.get("model_name")),
            max_rounds=_int_value(raw.get("max_rounds"), default=0),
            critic_enabled=bool(raw.get("critic_enabled", False)),
            status=_string_value(raw.get("status")) or "pending",
            created_at=_string_value(raw.get("created_at")),
            completed_at=_string_value(raw.get("completed_at")),
            semantic_extraction_run_path=_string_value(raw.get("semantic_extraction_run_path")),
            initial_investigation_analysis_run_path=_string_value(
                raw.get("initial_investigation_analysis_run_path")
            ),
            initial_state_path=_string_value(raw.get("initial_state_path")),
            initial_state_version=_int_value(raw.get("initial_state_version")),
            round_manifests=manifests,
            finalization=finalization,
        )
