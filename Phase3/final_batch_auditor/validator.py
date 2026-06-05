"""Validation helpers for the Phase 3A Final Batch Auditor runtime."""

from __future__ import annotations

import re
from typing import Any

from final_batch_auditor.contracts import (
    MAX_LIST_ITEMS,
    MAX_LIST_ITEM_CHARS,
    MAX_SUMMARY_CHARS,
    VALID_ROUND_COMPONENT_NAMES,
)


_AUDIT_CONTEXT_FIELDS = {
    "final_audit_input",
    "final_state_summary",
    "round_history_summary",
    "process_signal_summary",
}
_FINAL_AUDIT_INPUT_FIELDS = {
    "batch_id",
    "final_state_ref",
    "round_artifact_refs",
    "hypothesis_history_refs",
}
_ROUND_ARTIFACT_REF_FIELDS = {
    "round_id",
    "component_name",
    "artifact_kind",
    "artifact_ref",
}
_HISTORY_REF_FIELDS = {
    "hypothesis_id",
    "round_id",
    "history_ref",
}
_FINAL_STATE_SUMMARY_FIELDS = {
    "batch_id",
    "state_version",
    "substrate_region_count",
    "hypothesis_count",
    "active_hypothesis_count",
    "revision_count",
    "hypothesis_snapshots",
}
_HYPOTHESIS_SNAPSHOT_FIELDS = {
    "hypothesis_id",
    "status",
    "summary",
    "evidence_refs",
    "open_gaps",
    "preserved_contradictions",
    "merged_findings",
    "last_updated_round",
    "revision_count",
}
_ROUND_SUMMARY_FIELDS = {
    "round_id",
    "hypothesis_id",
    "state_version",
    "status",
    "summary",
    "contradiction_count",
    "open_gap_count",
    "overlap_group_count",
    "critic_observation_count",
    "traceability_refs",
}
_PROCESS_SIGNAL_SUMMARY_FIELDS = {
    "batch_id",
    "state_version",
    "round_count",
    "critic_run_count",
    "terminal_gate_expected",
    "warning_codes",
}
_DEBUGGING_AUDIT_REPORT_FIELDS = {
    "batch_id",
    "trajectory_summary",
    "hypothesis_summary",
    "surviving_contradictions",
    "open_pressures",
    "failure_summary",
    "traceability_refs",
}
_FORBIDDEN_TEXT_PATTERNS = {
    "future_round_guidance": re.compile(r"\bnext round\b|\bfuture round\b|\bsubsequent round\b", re.IGNORECASE),
    "control_language": re.compile(r"\brerank\b|\breplan\b|\breroute\b|\bdispatch\b|\bexecute\b|\binvoke\b|\bcall\b.+\btool\b", re.IGNORECASE),
    "state_mutation": re.compile(r"\bmutate\b.+\bstate\b|\bupdate\b.+\bcanonical state\b|\bmark\b.+\bresolved\b|\bclose\b.+\bhypothesis\b", re.IGNORECASE),
    "truth_authority": re.compile(r"\bconfirmed\b|\bproven\b|\bground truth\b|\bdefinitive\b", re.IGNORECASE),
    "polished_reporting": re.compile(r"\bexecutive summary\b|\bresearch report\b|\bpublication\b", re.IGNORECASE),
}


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _report(
    *,
    ok: bool,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
    stats: dict[str, Any] | None = None,
    forbidden_language_hits: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings or [],
    }
    if stats is not None:
        payload["stats"] = stats
    if forbidden_language_hits is not None:
        payload["forbidden_language_hits"] = forbidden_language_hits
    return payload


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object, *, allow_empty: bool = True) -> list[str] | None:
    if not isinstance(value, list):
        return None

    normalized: list[str] = []
    for item in value:
        if not _is_non_empty_string(item):
            return None
        normalized.append(str(item).strip())

    if not allow_empty and not normalized:
        return None
    return list(dict.fromkeys(normalized))


def _int_value(value: object) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _collect_forbidden_language(field_name: str, value: object) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return []

    hits: list[dict[str, str]] = []
    for code, pattern in _FORBIDDEN_TEXT_PATTERNS.items():
        if pattern.search(value):
            hits.append({"field": field_name, "code": code})
    return hits


def validate_final_batch_audit_input(
    audit_context: dict[str, Any],
    *,
    expected_batch_id: str,
) -> dict[str, Any]:
    raw = audit_context if isinstance(audit_context, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(audit_context, dict):
        errors.append(
            _error("audit_context", "audit_context must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _AUDIT_CONTEXT_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "audit_context",
                f"audit_context contains unsupported fields: {unsupported_fields}.",
            )
        )

    final_audit_input = raw.get("final_audit_input")
    if not isinstance(final_audit_input, dict):
        errors.append(_error("final_audit_input",
                      "final_audit_input must be an object."))
        final_audit_input = {}
    else:
        unsupported_fields = sorted(
            set(final_audit_input.keys()) - _FINAL_AUDIT_INPUT_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(
                    "final_audit_input",
                    f"final_audit_input contains unsupported fields: {unsupported_fields}.",
                )
            )

    batch_id = final_audit_input.get("batch_id")
    if not _is_non_empty_string(batch_id):
        errors.append(_error("final_audit_input.batch_id",
                      "batch_id must be a non-empty string."))
    elif str(batch_id).strip() != expected_batch_id:
        errors.append(
            _error(
                "final_audit_input.batch_id",
                f"batch_id must match '{expected_batch_id}'.",
            )
        )

    final_state_ref = final_audit_input.get("final_state_ref")
    if not _is_non_empty_string(final_state_ref):
        errors.append(
            _error("final_audit_input.final_state_ref",
                   "final_state_ref must be a non-empty string.")
        )

    round_artifact_refs = final_audit_input.get("round_artifact_refs")
    if not isinstance(round_artifact_refs, list) or not round_artifact_refs:
        errors.append(
            _error(
                "final_audit_input.round_artifact_refs",
                "round_artifact_refs must be a non-empty list.",
            )
        )
        round_artifact_refs = []
    for index, item in enumerate(round_artifact_refs):
        field_prefix = f"final_audit_input.round_artifact_refs[{index}]"
        if not isinstance(item, dict):
            errors.append(
                _error(field_prefix, "Each round_artifact_ref must be an object."))
            continue
        unsupported_fields = sorted(
            set(item.keys()) - _ROUND_ARTIFACT_REF_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
        for key in ("round_id", "artifact_kind", "artifact_ref"):
            if not _is_non_empty_string(item.get(key)):
                errors.append(
                    _error(f"{field_prefix}.{key}", f"{key} must be a non-empty string."))
        component_name = item.get("component_name")
        if not _is_non_empty_string(component_name):
            errors.append(_error(
                f"{field_prefix}.component_name", "component_name must be a non-empty string."))
        elif str(component_name).strip() not in VALID_ROUND_COMPONENT_NAMES:
            errors.append(
                _error(
                    f"{field_prefix}.component_name",
                    f"component_name must be one of {sorted(VALID_ROUND_COMPONENT_NAMES)}.",
                )
            )

    hypothesis_history_refs = final_audit_input.get("hypothesis_history_refs")
    if not isinstance(hypothesis_history_refs, list) or not hypothesis_history_refs:
        errors.append(
            _error(
                "final_audit_input.hypothesis_history_refs",
                "hypothesis_history_refs must be a non-empty list.",
            )
        )
        hypothesis_history_refs = []
    for index, item in enumerate(hypothesis_history_refs):
        field_prefix = f"final_audit_input.hypothesis_history_refs[{index}]"
        if not isinstance(item, dict):
            errors.append(
                _error(field_prefix, "Each hypothesis_history_ref must be an object."))
            continue
        unsupported_fields = sorted(set(item.keys()) - _HISTORY_REF_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
        for key in ("hypothesis_id", "round_id", "history_ref"):
            if not _is_non_empty_string(item.get(key)):
                errors.append(
                    _error(f"{field_prefix}.{key}", f"{key} must be a non-empty string."))

    final_state_summary = raw.get("final_state_summary")
    if not isinstance(final_state_summary, dict):
        errors.append(_error("final_state_summary",
                      "final_state_summary must be an object."))
        final_state_summary = {}
    else:
        unsupported_fields = sorted(
            set(final_state_summary.keys()) - _FINAL_STATE_SUMMARY_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(
                    "final_state_summary",
                    f"final_state_summary contains unsupported fields: {unsupported_fields}.",
                )
            )

    summary_batch_id = final_state_summary.get("batch_id")
    if not _is_non_empty_string(summary_batch_id):
        errors.append(_error("final_state_summary.batch_id",
                      "batch_id must be a non-empty string."))
    elif str(summary_batch_id).strip() != expected_batch_id:
        errors.append(
            _error(
                "final_state_summary.batch_id",
                f"batch_id must match '{expected_batch_id}'.",
            )
        )

    for key in (
        "state_version",
        "substrate_region_count",
        "hypothesis_count",
        "active_hypothesis_count",
        "revision_count",
    ):
        value = _int_value(final_state_summary.get(key))
        if value is None or value < 0:
            errors.append(_error(
                f"final_state_summary.{key}", f"{key} must be an integer greater than or equal to 0."))

    hypothesis_snapshots = final_state_summary.get("hypothesis_snapshots")
    if not isinstance(hypothesis_snapshots, list) or not hypothesis_snapshots:
        errors.append(
            _error(
                "final_state_summary.hypothesis_snapshots",
                "hypothesis_snapshots must be a non-empty list.",
            )
        )
        hypothesis_snapshots = []
    for index, item in enumerate(hypothesis_snapshots):
        field_prefix = f"final_state_summary.hypothesis_snapshots[{index}]"
        if not isinstance(item, dict):
            errors.append(
                _error(field_prefix, "Each hypothesis snapshot must be an object."))
            continue
        unsupported_fields = sorted(
            set(item.keys()) - _HYPOTHESIS_SNAPSHOT_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
        for key in ("hypothesis_id", "status", "summary", "last_updated_round"):
            if key == "last_updated_round":
                if item.get(key) is not None and not isinstance(item.get(key), str):
                    errors.append(
                        _error(f"{field_prefix}.{key}", f"{key} must be a string."))
            elif not _is_non_empty_string(item.get(key)):
                errors.append(
                    _error(f"{field_prefix}.{key}", f"{key} must be a non-empty string."))
        for list_field in (
            "evidence_refs",
            "open_gaps",
            "preserved_contradictions",
            "merged_findings",
        ):
            normalized = _string_list(item.get(list_field))
            if normalized is None:
                errors.append(_error(
                    f"{field_prefix}.{list_field}", f"{list_field} must be a list of strings."))
        revision_count = _int_value(item.get("revision_count"))
        if revision_count is None or revision_count < 0:
            errors.append(_error(f"{field_prefix}.revision_count",
                          "revision_count must be an integer greater than or equal to 0."))

    round_history_summary = raw.get("round_history_summary")
    if not isinstance(round_history_summary, list) or not round_history_summary:
        errors.append(_error("round_history_summary",
                      "round_history_summary must be a non-empty list."))
        round_history_summary = []
    for index, item in enumerate(round_history_summary):
        field_prefix = f"round_history_summary[{index}]"
        if not isinstance(item, dict):
            errors.append(
                _error(field_prefix, "Each round history summary must be an object."))
            continue
        unsupported_fields = sorted(set(item.keys()) - _ROUND_SUMMARY_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
        for key in ("round_id", "hypothesis_id", "status", "summary"):
            if not _is_non_empty_string(item.get(key)):
                errors.append(
                    _error(f"{field_prefix}.{key}", f"{key} must be a non-empty string."))
        for key in (
            "state_version",
            "contradiction_count",
            "open_gap_count",
            "overlap_group_count",
            "critic_observation_count",
        ):
            value = _int_value(item.get(key))
            if value is None or value < 0:
                errors.append(_error(
                    f"{field_prefix}.{key}", f"{key} must be an integer greater than or equal to 0."))
        refs = _string_list(item.get("traceability_refs"), allow_empty=False)
        if refs is None:
            errors.append(_error(f"{field_prefix}.traceability_refs",
                          "traceability_refs must be a non-empty list of strings."))

    process_signal_summary = raw.get("process_signal_summary")
    if not isinstance(process_signal_summary, dict):
        errors.append(_error("process_signal_summary",
                      "process_signal_summary must be an object."))
        process_signal_summary = {}
    else:
        unsupported_fields = sorted(
            set(process_signal_summary.keys()) - _PROCESS_SIGNAL_SUMMARY_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(
                    "process_signal_summary",
                    f"process_signal_summary contains unsupported fields: {unsupported_fields}.",
                )
            )

    process_batch_id = process_signal_summary.get("batch_id")
    if not _is_non_empty_string(process_batch_id):
        errors.append(_error("process_signal_summary.batch_id",
                      "batch_id must be a non-empty string."))
    elif str(process_batch_id).strip() != expected_batch_id:
        errors.append(
            _error(
                "process_signal_summary.batch_id",
                f"batch_id must match '{expected_batch_id}'.",
            )
        )

    for key in ("state_version", "round_count", "critic_run_count"):
        value = _int_value(process_signal_summary.get(key))
        if value is None or value < 0:
            errors.append(_error(
                f"process_signal_summary.{key}", f"{key} must be an integer greater than or equal to 0."))
    if not isinstance(process_signal_summary.get("terminal_gate_expected"), bool):
        errors.append(_error("process_signal_summary.terminal_gate_expected",
                      "terminal_gate_expected must be a boolean."))
    warning_codes = _string_list(process_signal_summary.get("warning_codes"))
    if warning_codes is None:
        errors.append(_error("process_signal_summary.warning_codes",
                      "warning_codes must be a list of strings."))

    return _report(ok=not errors, errors=errors, warnings=warnings)


def validate_debugging_audit_report(
    debugging_audit_report: dict[str, Any],
    *,
    expected_batch_id: str,
    known_traceability_refs: set[str],
) -> dict[str, Any]:
    raw = debugging_audit_report if isinstance(
        debugging_audit_report, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not isinstance(debugging_audit_report, dict):
        errors.append(_error("debugging_audit_report",
                      "debugging_audit_report must be an object."))

    unsupported_fields = sorted(
        set(raw.keys()) - _DEBUGGING_AUDIT_REPORT_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "debugging_audit_report",
                f"debugging_audit_report contains unsupported fields: {unsupported_fields}.",
            )
        )

    batch_id = raw.get("batch_id")
    if not _is_non_empty_string(batch_id):
        errors.append(_error("debugging_audit_report.batch_id",
                      "batch_id must be a non-empty string."))
    elif str(batch_id).strip() != expected_batch_id:
        errors.append(
            _error(
                "debugging_audit_report.batch_id",
                f"batch_id must match '{expected_batch_id}'.",
            )
        )

    for key in ("trajectory_summary", "hypothesis_summary", "failure_summary"):
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(
                _error(f"debugging_audit_report.{key}", f"{key} must be a non-empty string."))
            continue
        if len(str(value).strip()) > MAX_SUMMARY_CHARS:
            errors.append(
                _error(
                    f"debugging_audit_report.{key}",
                    f"{key} must be at most {MAX_SUMMARY_CHARS} characters.",
                )
            )
        forbidden_language_hits.extend(_collect_forbidden_language(
            f"debugging_audit_report.{key}", value))

    for list_field in ("surviving_contradictions", "open_pressures"):
        values = _string_list(raw.get(list_field))
        if values is None:
            errors.append(_error(
                f"debugging_audit_report.{list_field}", f"{list_field} must be a list of strings."))
            continue
        if len(values) > MAX_LIST_ITEMS:
            errors.append(
                _error(
                    f"debugging_audit_report.{list_field}",
                    f"{list_field} must contain at most {MAX_LIST_ITEMS} items.",
                )
            )
        for index, item in enumerate(values):
            if len(item) > MAX_LIST_ITEM_CHARS:
                errors.append(
                    _error(
                        f"debugging_audit_report.{list_field}[{index}]",
                        f"items must be at most {MAX_LIST_ITEM_CHARS} characters.",
                    )
                )
            forbidden_language_hits.extend(
                _collect_forbidden_language(
                    f"debugging_audit_report.{list_field}[{index}]",
                    item,
                )
            )

    traceability_refs = _string_list(
        raw.get("traceability_refs"), allow_empty=False)
    if traceability_refs is None:
        errors.append(
            _error(
                "debugging_audit_report.traceability_refs",
                "traceability_refs must be a non-empty list of strings.",
            )
        )
        traceability_refs = []
    else:
        if len(traceability_refs) > MAX_LIST_ITEMS:
            errors.append(
                _error(
                    "debugging_audit_report.traceability_refs",
                    f"traceability_refs must contain at most {MAX_LIST_ITEMS} items.",
                )
            )
        unknown_refs = sorted(set(traceability_refs) -
                              set(known_traceability_refs))
        if unknown_refs:
            errors.append(
                _error(
                    "debugging_audit_report.traceability_refs",
                    f"traceability_refs contains unknown refs: {unknown_refs}.",
                )
            )

    if forbidden_language_hits:
        warnings.append(
            _error(
                "debugging_audit_report",
                "Semantic language flags detected in debugging_audit_report.",
            )
        )

    stats = {
        "contradiction_count": len(_string_list(raw.get("surviving_contradictions")) or []),
        "open_pressure_count": len(_string_list(raw.get("open_pressures")) or []),
        "traceability_ref_count": len(traceability_refs),
    }
    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats=stats,
        forbidden_language_hits=forbidden_language_hits,
    )
