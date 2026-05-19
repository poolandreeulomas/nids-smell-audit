"""Validation helpers for the Phase 3A tools layer."""

from __future__ import annotations

from typing import Any


def _report(*, ok: bool, errors: list[dict[str, str]], warnings: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "ok": ok,
        "errors": errors,
        "warnings": list(warnings or []),
    }


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def validate_tool_capability_record(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not isinstance(record.get("tool_name"), str) or not record["tool_name"].strip():
        errors.append(_error("tool_name", "tool_name must be a non-empty string."))
    if not isinstance(record.get("epistemic_role"), str) or not record["epistemic_role"].strip():
        errors.append(_error("epistemic_role", "epistemic_role must be a non-empty string."))
    scopes = record.get("supported_scopes")
    if not isinstance(scopes, list) or not scopes or not all(isinstance(item, str) and item.strip() for item in scopes):
        errors.append(_error("supported_scopes", "supported_scopes must be a non-empty list of strings."))
    required_inputs = record.get("required_inputs")
    if not isinstance(required_inputs, list) or not all(isinstance(item, str) and item.strip() for item in required_inputs):
        errors.append(_error("required_inputs", "required_inputs must be a list of strings."))
    if not isinstance(record.get("result_shape"), str) or not record["result_shape"].strip():
        errors.append(_error("result_shape", "result_shape must be a non-empty string."))
    if not isinstance(record.get("boundedness_notes"), str) or not record["boundedness_notes"].strip():
        errors.append(_error("boundedness_notes", "boundedness_notes must be a non-empty string."))

    return _report(ok=not errors, errors=errors)


def validate_tool_inventory(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    seen_names: set[str] = set()

    if not isinstance(records, dict) or not records:
        return _report(
            ok=False,
            errors=[_error("inventory", "tool inventory must be a non-empty mapping.")],
        )

    for key, record in records.items():
        if key in seen_names:
            errors.append(_error("inventory", f"duplicate tool name '{key}' in inventory."))
        seen_names.add(key)
        record_report = validate_tool_capability_record(record)
        for item in record_report["errors"]:
            errors.append(_error(f"inventory.{key}.{item['field']}", item["message"]))
        record_name = record.get("tool_name")
        if isinstance(record_name, str) and record_name != key:
            errors.append(_error(f"inventory.{key}.tool_name", "record tool_name must match inventory key."))

    return _report(ok=not errors, errors=errors)


def validate_tool_call_request(
    request: dict[str, Any],
    capability_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    call_id = request.get("call_id")
    tool_name = request.get("tool_name")
    target_scope = request.get("target_scope")
    input_refs = request.get("input_refs")
    preprocessing_profile_ref = request.get("preprocessing_profile_ref")
    execution_constraints = request.get("execution_constraints")

    if not isinstance(call_id, str) or not call_id.strip():
        errors.append(_error("call_id", "call_id must be a non-empty string."))
    if not isinstance(tool_name, str) or not tool_name.strip():
        errors.append(_error("tool_name", "tool_name must be a non-empty string."))
    if not isinstance(target_scope, str) or not target_scope.strip():
        errors.append(_error("target_scope", "target_scope must be a non-empty string."))
    if not isinstance(input_refs, dict):
        errors.append(_error("input_refs", "input_refs must be a dictionary."))
        input_refs = {}
    if not isinstance(preprocessing_profile_ref, str) or not preprocessing_profile_ref.strip():
        errors.append(_error("preprocessing_profile_ref", "preprocessing_profile_ref must be a non-empty string."))
    if not isinstance(execution_constraints, dict):
        errors.append(_error("execution_constraints", "execution_constraints must be a dictionary."))

    if isinstance(tool_name, str) and tool_name.strip():
        record = capability_records.get(tool_name)
        if record is None:
            errors.append(_error("tool_name", f"unknown tool '{tool_name}'."))
        else:
            supported_scopes = set(record.get("supported_scopes") or [])
            if isinstance(target_scope, str) and target_scope not in supported_scopes:
                errors.append(
                    _error(
                        "target_scope",
                        f"target_scope '{target_scope}' is not supported for tool '{tool_name}'.",
                    )
                )

            required_inputs = list(record.get("required_inputs") or [])
            for required_input in required_inputs:
                value = input_refs.get(required_input)
                if value is None or (isinstance(value, str) and not value.strip()):
                    errors.append(
                        _error(
                            f"input_refs.{required_input}",
                            f"required input '{required_input}' is missing.",
                        )
                    )

            if tool_name == "feature_relation" and target_scope == "feature_pair":
                related_feature_name = input_refs.get("related_feature_name")
                if not isinstance(related_feature_name, str) or not related_feature_name.strip():
                    errors.append(
                        _error(
                            "input_refs.related_feature_name",
                            "feature_pair relation requests require related_feature_name.",
                        )
                    )

    return _report(ok=not errors, errors=errors)


def validate_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    if not isinstance(result.get("call_id"), str) or not result["call_id"].strip():
        errors.append(_error("call_id", "call_id must be a non-empty string."))
    if not isinstance(result.get("tool_name"), str) or not result["tool_name"].strip():
        errors.append(_error("tool_name", "tool_name must be a non-empty string."))
    if result.get("status") not in {"ok", "error"}:
        errors.append(_error("status", "status must be 'ok' or 'error'."))
    if not isinstance(result.get("observations"), dict):
        errors.append(_error("observations", "observations must be a dictionary."))
    if not isinstance(result.get("evidence_refs"), list):
        errors.append(_error("evidence_refs", "evidence_refs must be a list."))
    if not isinstance(result.get("limitations"), list):
        errors.append(_error("limitations", "limitations must be a list."))

    return _report(ok=not errors, errors=errors)