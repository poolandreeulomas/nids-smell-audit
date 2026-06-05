"""Minimal Phase 3A tool contracts.

These helpers keep the coordination surface small while remaining JSON-friendly
for artifact persistence and CLI inspection.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "phase3a.tools.v1"


def _clone_json_like(value: Any) -> Any:
    try:
        return deepcopy(value)
    except Exception:
        return value


def build_tool_capability_record(
    *,
    tool_name: str,
    epistemic_role: str,
    supported_scopes: list[str],
    required_inputs: list[str],
    result_shape: str,
    boundedness_notes: str,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "epistemic_role": epistemic_role,
        "supported_scopes": list(supported_scopes),
        "required_inputs": list(required_inputs),
        "result_shape": result_shape,
        "boundedness_notes": boundedness_notes,
    }


def build_tool_call_request(
    *,
    call_id: str,
    tool_name: str,
    target_scope: str,
    input_refs: dict[str, Any],
    preprocessing_profile_ref: str,
    execution_constraints: dict[str, Any],
) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "tool_name": tool_name,
        "target_scope": target_scope,
        "input_refs": _clone_json_like(input_refs),
        "preprocessing_profile_ref": preprocessing_profile_ref,
        "execution_constraints": _clone_json_like(execution_constraints),
    }


def build_tool_result(
    *,
    call_id: str,
    tool_name: str,
    status: str,
    observations: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "tool_name": tool_name,
        "status": status,
        "observations": _clone_json_like(observations),
        "evidence_refs": _clone_json_like(evidence_refs),
        "limitations": _clone_json_like(limitations),
    }


def normalize_legacy_tool_result(
    *,
    call_id: str,
    tool_name: str,
    legacy_result: dict[str, Any],
    evidence_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence = dict(legacy_result.get("evidence") or {})
    observations: dict[str, Any] = {
        "feature_name": legacy_result.get("feature_name"),
        "value": legacy_result.get("value"),
        "signals": list(evidence.get("signals", []) or []),
        "metrics": dict(evidence.get("metrics", {}) or {}),
        "support": dict(evidence.get("support", {}) or {}),
        "provenance": dict(evidence.get("provenance", {}) or {}),
    }
    if evidence.get("feature"):
        observations["feature"] = evidence["feature"]
    if "skipped" in legacy_result:
        observations["skipped"] = bool(legacy_result.get("skipped"))
    if legacy_result.get("reason") is not None:
        observations["reason"] = legacy_result.get("reason")

    limitations: list[dict[str, Any]] = []
    if not legacy_result.get("ok", False):
        limitations.append(
            {
                "code": legacy_result.get("error_code") or "RUNTIME_ERROR",
                "message": legacy_result.get("error_message") or "Tool execution failed.",
            }
        )

    return build_tool_result(
        call_id=call_id,
        tool_name=tool_name,
        status="ok" if legacy_result.get("ok", False) else "error",
        observations=observations,
        evidence_refs=list(evidence_refs or []),
        limitations=limitations,
    )


def build_request_failure_result(
    *,
    call_id: str,
    tool_name: str,
    code: str,
    message: str,
    evidence_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_tool_result(
        call_id=call_id,
        tool_name=tool_name,
        status="error",
        observations={},
        evidence_refs=list(evidence_refs or []),
        limitations=[{"code": code, "message": message}],
    )
