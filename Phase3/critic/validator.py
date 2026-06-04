"""Validation helpers for the Phase 3A Critic runtime."""

from __future__ import annotations

import re
from typing import Any

from critic.contracts import (
    MAX_MODULE_FEEDBACK_ITEMS,
    MAX_OBSERVED_ISSUE_CHARS,
    MAX_SUGGESTION_CHARS,
    VALID_MODULE_NAMES,
)


_CRITIC_CONTEXT_FIELDS = {
    "critic_input_min",
    "refined_state_summary",
    "module_behavior_summaries",
    "process_signal_summary",
}
_CRITIC_INPUT_MIN_FIELDS = {
    "batch_id",
    "round_id",
    "state_summary_ref",
    "module_artifact_refs",
    "process_signal_refs",
}
_MODULE_ARTIFACT_REF_FIELDS = {
    "module_name",
    "artifact_kind",
    "artifact_ref",
}
_PROCESS_SIGNAL_REF_FIELDS = {
    "signal_name",
    "signal_ref",
}
_REFINED_STATE_SUMMARY_FIELDS = {
    "batch_id",
    "round_id",
    "hypothesis_id",
    "state_version",
    "summary",
    "status",
    "evidence_refs",
    "open_gaps",
    "preserved_contradictions",
    "merged_findings",
    "last_updated_round",
}
_MODULE_BEHAVIOR_SUMMARY_FIELDS = {
    "module_name",
    "status",
    "behavior_summary",
    "evidence_refs",
    "warning_signals",
}
_PROCESS_SIGNAL_SUMMARY_FIELDS = {
    "batch_id",
    "round_id",
    "is_final_round",
    "state_committed",
    "validation_ok",
    "applied_update_count",
    "remaining_open_gap_count",
    "warning_codes",
}
_CRITIC_FEEDBACK_PAYLOAD_FIELDS = {
    "batch_id",
    "round_id",
    "module_feedback",
}
_MODULE_FEEDBACK_FIELDS = {
    "module_name",
    "observed_issue",
    "evidence_refs",
    "suggestion",
}
_FORBIDDEN_SUGGESTION_PATTERNS = {
    "planning_directive": re.compile(r"\breplan\b|\brerank\b|\bdispatch\b|\bdecompose\b", re.IGNORECASE),
    "execution_directive": re.compile(r"\bexecute\b|\binvoke\b|\bcall\b.+\btool\b|\buse\b.+\btool\b", re.IGNORECASE),
    "state_mutation": re.compile(r"\bupdate\b.+\bstate\b|\bmutate\b.+\bstate\b|\bset\b.+\bstatus\b|\bmark\b.+\bresolved\b|\bclose\b.+\bhypothesis\b", re.IGNORECASE),
    "truth_authority": re.compile(r"\bconfirmed\b|\bproven\b|\bis true\b|\bare true\b", re.IGNORECASE),
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
    for code, pattern in _FORBIDDEN_SUGGESTION_PATTERNS.items():
        if pattern.search(value):
            hits.append({"field": field_name, "code": code})
    return hits


def validate_critic_input_bundle(
    critic_context: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
) -> dict[str, Any]:
    raw = critic_context if isinstance(critic_context, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(critic_context, dict):
        errors.append(_error("critic_context", "critic_context must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _CRITIC_CONTEXT_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "critic_context",
                f"critic_context contains unsupported fields: {unsupported_fields}.",
            )
        )

    critic_input_min = raw.get("critic_input_min")
    if not isinstance(critic_input_min, dict):
        errors.append(_error("critic_input_min", "critic_input_min must be an object."))
        critic_input_min = {}
    else:
        unsupported_fields = sorted(set(critic_input_min.keys()) - _CRITIC_INPUT_MIN_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(
                    "critic_input_min",
                    f"critic_input_min contains unsupported fields: {unsupported_fields}.",
                )
            )

    for key, expected_value in (("batch_id", expected_batch_id), ("round_id", expected_round_id)):
        value = critic_input_min.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(f"critic_input_min.{key}", f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(f"critic_input_min.{key}", f"{key} must match '{expected_value}'."))

    state_summary_ref = critic_input_min.get("state_summary_ref")
    if not _is_non_empty_string(state_summary_ref):
        errors.append(_error("critic_input_min.state_summary_ref", "state_summary_ref must be a non-empty string."))

    module_artifact_refs = critic_input_min.get("module_artifact_refs")
    if not isinstance(module_artifact_refs, list) or not module_artifact_refs:
        errors.append(_error("critic_input_min.module_artifact_refs", "module_artifact_refs must be a non-empty list."))
        module_artifact_refs = []
    for index, artifact_ref in enumerate(module_artifact_refs):
        field_prefix = f"critic_input_min.module_artifact_refs[{index}]"
        if not isinstance(artifact_ref, dict):
            errors.append(_error(field_prefix, "Each module_artifact_ref must be an object."))
            continue
        unsupported_fields = sorted(set(artifact_ref.keys()) - _MODULE_ARTIFACT_REF_FIELDS)
        if unsupported_fields:
            errors.append(_error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
        module_name = artifact_ref.get("module_name")
        if not _is_non_empty_string(module_name):
            errors.append(_error(f"{field_prefix}.module_name", "module_name must be a non-empty string."))
        elif str(module_name).strip() not in VALID_MODULE_NAMES:
            errors.append(_error(f"{field_prefix}.module_name", f"module_name must be one of {sorted(VALID_MODULE_NAMES)}."))
        for key in ("artifact_kind", "artifact_ref"):
            value = artifact_ref.get(key)
            if not _is_non_empty_string(value):
                errors.append(_error(f"{field_prefix}.{key}", f"{key} must be a non-empty string."))

    process_signal_refs = critic_input_min.get("process_signal_refs")
    if not isinstance(process_signal_refs, list) or not process_signal_refs:
        errors.append(_error("critic_input_min.process_signal_refs", "process_signal_refs must be a non-empty list."))
        process_signal_refs = []
    for index, signal_ref in enumerate(process_signal_refs):
        field_prefix = f"critic_input_min.process_signal_refs[{index}]"
        if not isinstance(signal_ref, dict):
            errors.append(_error(field_prefix, "Each process_signal_ref must be an object."))
            continue
        unsupported_fields = sorted(set(signal_ref.keys()) - _PROCESS_SIGNAL_REF_FIELDS)
        if unsupported_fields:
            errors.append(_error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
        for key in ("signal_name", "signal_ref"):
            value = signal_ref.get(key)
            if not _is_non_empty_string(value):
                errors.append(_error(f"{field_prefix}.{key}", f"{key} must be a non-empty string."))

    refined_state_summary = raw.get("refined_state_summary")
    if not isinstance(refined_state_summary, dict):
        errors.append(_error("refined_state_summary", "refined_state_summary must be an object."))
        refined_state_summary = {}
    else:
        unsupported_fields = sorted(set(refined_state_summary.keys()) - _REFINED_STATE_SUMMARY_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(
                    "refined_state_summary",
                    f"refined_state_summary contains unsupported fields: {unsupported_fields}.",
                )
            )

    for key, expected_value in (("batch_id", expected_batch_id), ("round_id", expected_round_id)):
        value = refined_state_summary.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(f"refined_state_summary.{key}", f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(f"refined_state_summary.{key}", f"{key} must match '{expected_value}'."))

    if not _is_non_empty_string(refined_state_summary.get("hypothesis_id")):
        errors.append(_error("refined_state_summary.hypothesis_id", "hypothesis_id must be a non-empty string."))
    if not _is_non_empty_string(refined_state_summary.get("summary")):
        errors.append(_error("refined_state_summary.summary", "summary must be a non-empty string."))
    if not _is_non_empty_string(refined_state_summary.get("status")):
        errors.append(_error("refined_state_summary.status", "status must be a non-empty string."))
    state_version = _int_value(refined_state_summary.get("state_version"))
    if state_version is None or state_version < 1:
        errors.append(_error("refined_state_summary.state_version", "state_version must be an integer greater than or equal to 1."))
    evidence_refs = _string_list(refined_state_summary.get("evidence_refs"), allow_empty=False)
    if evidence_refs is None:
        errors.append(_error("refined_state_summary.evidence_refs", "evidence_refs must be a non-empty list of strings."))
    for list_field in ("open_gaps", "preserved_contradictions", "merged_findings"):
        normalized_list = _string_list(refined_state_summary.get(list_field))
        if normalized_list is None:
            errors.append(_error(f"refined_state_summary.{list_field}", f"{list_field} must be a list of strings."))

    module_behavior_summaries = raw.get("module_behavior_summaries")
    if not isinstance(module_behavior_summaries, list) or not module_behavior_summaries:
        errors.append(_error("module_behavior_summaries", "module_behavior_summaries must be a non-empty list."))
        module_behavior_summaries = []
    for index, summary in enumerate(module_behavior_summaries):
        field_prefix = f"module_behavior_summaries[{index}]"
        if not isinstance(summary, dict):
            errors.append(_error(field_prefix, "Each module_behavior_summary must be an object."))
            continue
        unsupported_fields = sorted(set(summary.keys()) - _MODULE_BEHAVIOR_SUMMARY_FIELDS)
        if unsupported_fields:
            errors.append(_error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
        module_name = summary.get("module_name")
        if not _is_non_empty_string(module_name):
            errors.append(_error(f"{field_prefix}.module_name", "module_name must be a non-empty string."))
        elif str(module_name).strip() not in VALID_MODULE_NAMES:
            errors.append(_error(f"{field_prefix}.module_name", f"module_name must be one of {sorted(VALID_MODULE_NAMES)}."))
        for key in ("status", "behavior_summary"):
            value = summary.get(key)
            if not _is_non_empty_string(value):
                errors.append(_error(f"{field_prefix}.{key}", f"{key} must be a non-empty string."))
        evidence_refs = _string_list(summary.get("evidence_refs"))
        if evidence_refs is None:
            errors.append(_error(f"{field_prefix}.evidence_refs", "evidence_refs must be a list of strings."))
        warning_signals = _string_list(summary.get("warning_signals"))
        if warning_signals is None:
            errors.append(_error(f"{field_prefix}.warning_signals", "warning_signals must be a list of strings."))

    process_signal_summary = raw.get("process_signal_summary")
    if not isinstance(process_signal_summary, dict):
        errors.append(_error("process_signal_summary", "process_signal_summary must be an object."))
        process_signal_summary = {}
    else:
        unsupported_fields = sorted(set(process_signal_summary.keys()) - _PROCESS_SIGNAL_SUMMARY_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(
                    "process_signal_summary",
                    f"process_signal_summary contains unsupported fields: {unsupported_fields}.",
                )
            )

    for key, expected_value in (("batch_id", expected_batch_id), ("round_id", expected_round_id)):
        value = process_signal_summary.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(f"process_signal_summary.{key}", f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(f"process_signal_summary.{key}", f"{key} must match '{expected_value}'."))
    for key in ("is_final_round", "state_committed", "validation_ok"):
        if not isinstance(process_signal_summary.get(key), bool):
            errors.append(_error(f"process_signal_summary.{key}", f"{key} must be a boolean."))
    for key in ("applied_update_count", "remaining_open_gap_count"):
        value = _int_value(process_signal_summary.get(key))
        if value is None or value < 0:
            errors.append(_error(f"process_signal_summary.{key}", f"{key} must be a non-negative integer."))
    warning_codes = _string_list(process_signal_summary.get("warning_codes"))
    if warning_codes is None:
        errors.append(_error("process_signal_summary.warning_codes", "warning_codes must be a list of strings."))

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "module_artifact_ref_count": len(module_artifact_refs),
            "process_signal_ref_count": len(process_signal_refs),
            "module_behavior_summary_count": len(module_behavior_summaries),
        },
    )


def validate_critic_feedback_payload(
    critic_feedback_payload: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
    known_evidence_refs: set[str],
    allowed_module_names: set[str] | None = None,
) -> dict[str, Any]:
    raw = critic_feedback_payload if isinstance(critic_feedback_payload, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []
    allowed_modules = set(allowed_module_names or VALID_MODULE_NAMES)

    if not isinstance(critic_feedback_payload, dict):
        errors.append(_error("critic_feedback_payload", "critic_feedback_payload must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _CRITIC_FEEDBACK_PAYLOAD_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "critic_feedback_payload",
                f"critic_feedback_payload contains unsupported fields: {unsupported_fields}.",
            )
        )

    for key, expected_value in (("batch_id", expected_batch_id), ("round_id", expected_round_id)):
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(key, f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(key, f"{key} must match '{expected_value}'."))

    module_feedback = raw.get("module_feedback")
    if not isinstance(module_feedback, list) or not module_feedback:
        errors.append(_error("module_feedback", "module_feedback must be a non-empty list."))
        module_feedback = []
    elif len(module_feedback) > MAX_MODULE_FEEDBACK_ITEMS:
        errors.append(
            _error(
                "module_feedback",
                f"module_feedback must contain no more than {MAX_MODULE_FEEDBACK_ITEMS} items.",
            )
        )

    for index, feedback_item in enumerate(module_feedback):
        field_prefix = f"module_feedback[{index}]"
        if not isinstance(feedback_item, dict):
            errors.append(_error(field_prefix, "Each module_feedback item must be an object."))
            continue
        unsupported_fields = sorted(set(feedback_item.keys()) - _MODULE_FEEDBACK_FIELDS)
        if unsupported_fields:
            errors.append(_error(field_prefix, f"Unsupported fields: {unsupported_fields}."))

        module_name = feedback_item.get("module_name")
        if not _is_non_empty_string(module_name):
            errors.append(_error(f"{field_prefix}.module_name", "module_name must be a non-empty string."))
        elif str(module_name).strip() not in VALID_MODULE_NAMES:
            errors.append(_error(f"{field_prefix}.module_name", f"module_name must be one of {sorted(VALID_MODULE_NAMES)}."))
        elif str(module_name).strip() not in allowed_modules:
            errors.append(
                _error(
                    f"{field_prefix}.module_name",
                    f"module_name must target one of the observed modules: {sorted(allowed_modules)}.",
                )
            )

        observed_issue = feedback_item.get("observed_issue")
        if not _is_non_empty_string(observed_issue):
            errors.append(_error(f"{field_prefix}.observed_issue", "observed_issue must be a non-empty string."))
        elif len(str(observed_issue).strip()) > MAX_OBSERVED_ISSUE_CHARS:
            errors.append(
                _error(
                    f"{field_prefix}.observed_issue",
                    f"observed_issue must stay under {MAX_OBSERVED_ISSUE_CHARS} characters.",
                )
            )

        evidence_refs = _string_list(feedback_item.get("evidence_refs"), allow_empty=False)
        if evidence_refs is None:
            errors.append(_error(f"{field_prefix}.evidence_refs", "evidence_refs must be a non-empty list of strings."))
            evidence_refs = []
        else:
            for evidence_ref in evidence_refs:
                if evidence_ref not in known_evidence_refs:
                    errors.append(_error(f"{field_prefix}.evidence_refs", f"Unknown evidence_ref '{evidence_ref}'."))

        suggestion = feedback_item.get("suggestion")
        if not _is_non_empty_string(suggestion):
            errors.append(_error(f"{field_prefix}.suggestion", "suggestion must be a non-empty string."))
        elif len(str(suggestion).strip()) > MAX_SUGGESTION_CHARS:
            errors.append(
                _error(
                    f"{field_prefix}.suggestion",
                    f"suggestion must stay under {MAX_SUGGESTION_CHARS} characters.",
                )
            )
        forbidden_language_hits.extend(
            _collect_forbidden_language(f"{field_prefix}.observed_issue", observed_issue)
        )
        forbidden_language_hits.extend(
            _collect_forbidden_language(f"{field_prefix}.suggestion", suggestion)
        )

    if forbidden_language_hits:
        warnings.extend(
            _error(hit["field"], f"Semantic language flag detected ({hit['code']}).")
            for hit in forbidden_language_hits
        )

    suggestion_lengths = [
        len(str(item.get("suggestion", "") or "").strip())
        for item in module_feedback
        if isinstance(item, dict)
    ]
    average_suggestion_length = round(
        sum(suggestion_lengths) / len(suggestion_lengths),
        3,
    ) if suggestion_lengths else 0.0

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "module_feedback_count": len(module_feedback),
            "average_suggestion_length": average_suggestion_length,
        },
        forbidden_language_hits=forbidden_language_hits,
    )
