"""Worker-facing execution adapter over the shared Phase 3A tool surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data.dataset_config import get_default_dataset_config
from data.loader import load_dataset
from tools.common import sanitize_json_like
from tools.execution import execute_tool_call
from tools.registry import get_tool_capability_records
from tools.validator import validate_tool_result


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def build_action_tool_map(
    allowed_actions: list[str],
    capability_records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    records = capability_records or get_tool_capability_records()
    role_to_tools: dict[str, list[str]] = {}
    for tool_name, record in records.items():
        role = str(record.get("epistemic_role") or "").strip()
        if not role:
            continue
        role_to_tools.setdefault(role, []).append(tool_name)

    errors: list[dict[str, str]] = []
    action_tool_map: dict[str, str] = {}
    for action_class in allowed_actions:
        candidate_tools = sorted(role_to_tools.get(action_class, []))
        if not candidate_tools:
            errors.append(_error(
                "allowed_actions", f"No tool is registered for action_class '{action_class}'."))
            continue
        if len(candidate_tools) > 1:
            errors.append(
                _error(
                    "allowed_actions",
                    f"Ambiguous action_class '{action_class}' maps to multiple tools: {candidate_tools}.",
                )
            )
            continue
        action_tool_map[action_class] = candidate_tools[0]

    return {
        "ok": not errors,
        "errors": errors,
        "action_tool_map": action_tool_map,
    }


def prepare_worker_dataset(dataset_path: str | Path) -> dict[str, Any]:
    cfg = get_default_dataset_config()
    dataframe, valid_numeric_features = load_dataset(dataset_path, cfg)
    return {
        "dataset_path": str(dataset_path),
        "config": cfg,
        "dataset_frame": dataframe,
        "valid_numeric_features": valid_numeric_features,
    }


def _build_request(
    *,
    call_id: str,
    tool_name: str,
    feature_name: str | None,
    related_feature_name: str | None,
) -> dict[str, Any]:
    if tool_name == "duplication_analysis":
        target_scope = "dataset"
        input_refs: dict[str, Any] = {}
    elif tool_name == "feature_relation" and related_feature_name:
        target_scope = "feature_pair"
        input_refs = {
            "feature_name": feature_name,
            "related_feature_name": related_feature_name,
        }
    else:
        target_scope = "feature"
        input_refs = {"feature_name": feature_name}

    return {
        "call_id": call_id,
        "tool_name": tool_name,
        "target_scope": target_scope,
        "input_refs": input_refs,
        "preprocessing_profile_ref": "default",
        "execution_constraints": {
            "cache_policy": "reuse",
            "validation_mode": "strict",
            "save_raw_output": True,
        },
    }


def _build_invalid_tool_event(
    *,
    call_id: str,
    action: dict[str, Any],
    tool_name: str | None,
    message: str,
    request_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_tool_name = str(tool_name or "unresolved_tool")
    tool_result = {
        "call_id": call_id,
        "tool_name": safe_tool_name,
        "status": "error",
        "observations": {"error_message": message},
        "evidence_refs": [],
        "limitations": [{"code": "INVALID_ACTION", "message": message}],
    }
    result_validation = validate_tool_result(tool_result)
    return {
        "ok": False,
        "execution_ok": False,
        "call_id": call_id,
        "action": dict(action),
        "tool_name": safe_tool_name,
        "request": {},
        "request_validation": request_validation or {"ok": False, "errors": [_error("request", message)], "warnings": []},
        "raw_tool_output": {
            "ok": False,
            "tool": safe_tool_name,
            "error_code": "INVALID_ACTION",
            "error_message": message,
        },
        "tool_result": tool_result,
        "result_validation": result_validation,
        "cache_events": [],
        "artifact_paths": {},
        "tool_metrics": {},
        "error_message": message,
    }


def execute_worker_action(
    action: dict[str, Any],
    *,
    task_id: str,
    step_index: int,
    action_index: int = 1,
    action_count: int = 1,
    action_tool_map: dict[str, str],
    capability_records: dict[str, dict[str, Any]],
    runtime_dataset: dict[str, Any],
    local_context_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    action_class = str(action.get("action_class") or "").strip()
    context_ref = str(action.get("context_ref") or "").strip()
    feature_name = str(action.get("feature_name") or "").strip() or None
    related_feature_name = str(action.get(
        "related_feature_name") or "").strip() or None
    call_id = (
        f"{task_id}_step_{step_index:02d}"
        if action_count <= 1
        else f"{task_id}_step_{step_index:02d}_call_{action_index:02d}"
    )

    tool_name = action_tool_map.get(action_class)
    if tool_name is None:
        return _build_invalid_tool_event(
            call_id=call_id,
            action=action,
            tool_name=None,
            message=f"Action class '{action_class}' is not admitted for this worker task.",
        )

    local_context = local_context_index.get(context_ref)
    if local_context is None:
        return _build_invalid_tool_event(
            call_id=call_id,
            action=action,
            tool_name=tool_name,
            message=f"Unknown context_ref '{context_ref}' for this worker task.",
        )

    allowed_features = set(local_context.get("feature_names") or [])
    if tool_name != "duplication_analysis":
        if feature_name is None:
            return _build_invalid_tool_event(
                call_id=call_id,
                action=action,
                tool_name=tool_name,
                message="feature_name is required for the selected action.",
            )
        if allowed_features and feature_name not in allowed_features:
            return _build_invalid_tool_event(
                call_id=call_id,
                action=action,
                tool_name=tool_name,
                message=f"feature_name '{feature_name}' is outside the selected local context.",
            )
    if related_feature_name is not None:
        if tool_name != "feature_relation":
            return _build_invalid_tool_event(
                call_id=call_id,
                action=action,
                tool_name=tool_name,
                message="related_feature_name is only supported for relation_verification actions.",
            )
        if allowed_features and related_feature_name not in allowed_features:
            return _build_invalid_tool_event(
                call_id=call_id,
                action=action,
                tool_name=tool_name,
                message=f"related_feature_name '{related_feature_name}' is outside the selected local context.",
            )

    request = _build_request(
        call_id=call_id,
        tool_name=tool_name,
        feature_name=feature_name,
        related_feature_name=related_feature_name,
    )
    tool_bundle = execute_tool_call(
        request,
        dataset_path=runtime_dataset["dataset_path"],
        config=runtime_dataset["config"],
        dataset_frame=runtime_dataset["dataset_frame"],
        valid_numeric_features=runtime_dataset["valid_numeric_features"],
        caller_mode="worker",
    )

    raw_tool_output = sanitize_json_like(tool_bundle["raw_tool_output"])
    tool_result = sanitize_json_like(tool_bundle["tool_result"])
    cache_events = list(tool_bundle.get("cache_record", {}).get("events", []))
    validation_report = tool_bundle.get("validation_report", {})
    request_validation = validation_report.get(
        "request_validation", {"ok": False, "errors": [], "warnings": []})
    result_validation = validation_report.get(
        "result_validation", {"ok": False, "errors": [], "warnings": []})
    tool_metrics = sanitize_json_like(tool_bundle.get("tool_metrics", {}))
    limitations = tool_result.get("limitations") if isinstance(
        tool_result.get("limitations"), list) else []
    fallback_error_message = ""
    if limitations:
        first_limitation = limitations[0]
        if isinstance(first_limitation, dict):
            fallback_error_message = str(first_limitation.get("message") or "")
        elif isinstance(first_limitation, str):
            fallback_error_message = first_limitation

    return {
        "ok": bool(request_validation.get("ok")) and bool(result_validation.get("ok")),
        "execution_ok": bool(raw_tool_output.get("ok")),
        "call_id": call_id,
        "action": dict(action),
        "tool_name": tool_name,
        "request": request,
        "request_validation": request_validation,
        "raw_tool_output": raw_tool_output,
        "tool_result": tool_result,
        "result_validation": result_validation,
        "cache_events": cache_events,
        "artifact_paths": dict(tool_bundle.get("artifact_paths", {})),
        "tool_metrics": tool_metrics,
        "error_message": str(raw_tool_output.get("error_message") or fallback_error_message),
    }
