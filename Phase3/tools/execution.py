"""Phase 3A direct tools execution wrapper.

This module reuses the existing deterministic tools and registry while exposing
the smaller Phase 3A contract surface plus artifact-first observability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from data.dataset_config import DatasetConfig, get_default_dataset_config
from tools.common import collect_cache_events_since, resolve_tool_inputs, snapshot_cache_events
from tools.contracts import SCHEMA_VERSION, build_request_failure_result, normalize_legacy_tool_result
from tools.registry import get_tool_capability_records, run_tool
from tools.runtime_artifacts import build_tool_evidence_refs, build_tool_run_artifact_paths, save_tool_run_artifacts
from tools.validator import validate_tool_call_request, validate_tool_inventory, validate_tool_result


def _build_invalid_request_legacy_result(
    *,
    tool_name: str,
    input_refs: dict[str, Any],
    request_validation: dict[str, Any],
) -> dict[str, Any]:
    error_messages = "; ".join(item["message"] for item in request_validation["errors"])
    return {
        "ok": False,
        "tool": tool_name,
        "feature_name": input_refs.get("feature_name"),
        "value": None,
        "error_code": "INVALID_TOOL_REQUEST",
        "error_message": error_messages or "Tool request validation failed.",
        "meta": {"validation_errors": request_validation["errors"]},
    }


def _build_execution_constraints_summary(request: dict[str, Any], *, replay_of: str | None) -> dict[str, Any]:
    constraints = dict(request.get("execution_constraints") or {})
    if replay_of:
        constraints["replay_of"] = replay_of
    return constraints


def execute_tool_call(
    tool_call_request: dict[str, Any],
    *,
    dataset_path: str | Path,
    config: DatasetConfig | None = None,
    dataset_frame: pd.DataFrame | None = None,
    valid_numeric_features: list[str] | None = None,
    log_dir: str | Path | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
) -> dict[str, Any]:
    """Execute one tool request through the Phase 3A tools surface."""
    capability_records = get_tool_capability_records()
    inventory_validation = validate_tool_inventory(capability_records)
    request_validation = validate_tool_call_request(tool_call_request, capability_records)

    tool_name = str(tool_call_request.get("tool_name") or "unknown_tool")
    target_scope = str(tool_call_request.get("target_scope") or "unknown_scope")
    input_refs = dict(tool_call_request.get("input_refs") or {})
    capability_record = capability_records.get(tool_name, {})

    raw_tool_output: dict[str, Any]
    cache_record = {"status": "unavailable", "events": []}
    normalized_inputs: dict[str, Any] = {
        "dataset_path": str(dataset_path),
        "target_scope": target_scope,
        "input_refs": input_refs,
        "preprocessing_profile_ref": tool_call_request.get("preprocessing_profile_ref"),
        "execution_constraints": _build_execution_constraints_summary(tool_call_request, replay_of=replay_of),
    }

    cfg = config or get_default_dataset_config()
    start_time = perf_counter()

    if request_validation["ok"]:
        try:
            cfg, resolved_df, resolved_valid_features = resolve_tool_inputs(
                dataset_path,
                cfg,
                dataset_frame,
                valid_numeric_features,
            )
            normalized_inputs["resolved_feature_count"] = len(resolved_valid_features)
            normalized_inputs["dataframe_shape"] = [int(resolved_df.shape[0]), int(resolved_df.shape[1])]
            normalized_inputs["label_column"] = cfg.label_column

            cache_cursor = snapshot_cache_events(resolved_df)
            raw_tool_output = run_tool(
                tool_name=tool_name,
                feature_name=input_refs.get("feature_name"),
                dataset_path=dataset_path,
                config=cfg,
                dataset_frame=resolved_df,
                valid_numeric_features=resolved_valid_features,
                related_feature_name=input_refs.get("related_feature_name"),
            )
            cache_events = collect_cache_events_since(resolved_df, cache_cursor)
            cache_record = {
                "status": "tracked",
                "events": cache_events,
                "event_count": len(cache_events),
            }
        except Exception as exc:  # noqa: BLE001
            raw_tool_output = {
                "ok": False,
                "tool": tool_name,
                "feature_name": input_refs.get("feature_name"),
                "value": None,
                "error_code": "RUNTIME_ERROR",
                "error_message": str(exc),
                "meta": {},
            }
    else:
        raw_tool_output = _build_invalid_request_legacy_result(
            tool_name=tool_name,
            input_refs=input_refs,
            request_validation=request_validation,
        )

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)

    artifact_paths = build_tool_run_artifact_paths(
        tool_name=tool_name,
        target_scope=target_scope,
        log_dir=log_dir,
    )
    evidence_refs = build_tool_evidence_refs(artifact_paths)

    if request_validation["ok"]:
        tool_result = normalize_legacy_tool_result(
            call_id=str(tool_call_request.get("call_id") or "unknown_call"),
            tool_name=tool_name,
            legacy_result=raw_tool_output,
            evidence_refs=evidence_refs,
        )
    else:
        error = request_validation["errors"][0] if request_validation["errors"] else {"message": "Tool request validation failed."}
        tool_result = build_request_failure_result(
            call_id=str(tool_call_request.get("call_id") or "unknown_call"),
            tool_name=tool_name,
            code="INVALID_TOOL_REQUEST",
            message=error["message"],
            evidence_refs=evidence_refs,
        )

    result_validation = validate_tool_result(tool_result)
    validation_report = {
        "ok": inventory_validation["ok"] and request_validation["ok"] and result_validation["ok"],
        "schema_version": SCHEMA_VERSION,
        "inventory_validation": inventory_validation,
        "request_validation": request_validation,
        "result_validation": result_validation,
    }

    tool_metrics = {
        "tool_name": tool_name,
        "target_scope": target_scope,
        "duration_ms": duration_ms,
        "status": tool_result["status"],
        "cache_status": cache_record["status"],
        "cache_event_count": cache_record.get("event_count", 0),
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }

    component_run = {
        "component": "tools",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "call_id": tool_result["call_id"],
        "tool_name": tool_name,
        "target_scope": target_scope,
        "status": tool_result["status"],
        "validation_ok": validation_report["ok"],
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }

    persisted_paths = save_tool_run_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        tool_call_request=tool_call_request,
        tool_capability_record=capability_record,
        normalized_inputs=normalized_inputs,
        raw_tool_output=raw_tool_output,
        parsed_output=tool_result,
        validation_report=validation_report,
        tool_metrics=tool_metrics,
        cache_record=cache_record,
    )

    return {
        "component_run": component_run,
        "tool_call_request": tool_call_request,
        "tool_capability_record": capability_record,
        "normalized_inputs": normalized_inputs,
        "raw_tool_output": raw_tool_output,
        "tool_result": tool_result,
        "validation_report": validation_report,
        "tool_metrics": tool_metrics,
        "cache_record": cache_record,
        "artifact_paths": persisted_paths,
    }