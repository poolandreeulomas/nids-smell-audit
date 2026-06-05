"""Validation helpers for the Phase 3A Aggregation runtime."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from aggregation.contracts import MAX_UPDATE_FOCUS_CHARS
from worker.contracts import VALID_WORKER_STATUSES


class ValidationSeverity(str, Enum):
    FATAL = "FATAL"
    REPAIRABLE = "REPAIRABLE"
    WARNING = "WARNING"


_WORKER_RESULT_SET_FIELDS = {
    "batch_id",
    "round_id",
    "hypothesis_id",
    "worker_results",
}
_WORKER_RESULT_FIELDS = {
    "task_id",
    "hypothesis_id",
    "status",
    "findings",
    "evidence_refs",
    "contradictions",
    "limitations",
}
_AGGREGATION_HANDOFF_FIELDS = {
    "batch_id",
    "round_id",
    "hypothesis_id",
    "merged_findings",
    "evidence_refs",
    "preserved_contradictions",
    "open_gaps",
    "update_focus",
}
_FORBIDDEN_OUTPUT_PATTERNS = {
    "planning_language": re.compile(r"\bplan(?:ning|ned|s)?\b|\breplan(?:ning|ned|s)?\b|\bstrategy\b", re.IGNORECASE),
    "state_mutation_language": re.compile(r"\bcanonical state\b|\bmutate(?:d|ion)?\b|\bcommit(?:ted)?\b.*\bstate\b|\bstate manager\b|\brefin(?:e|ement|ed)\b", re.IGNORECASE),
    "critic_language": re.compile(r"\bcritic\b|\bprocess quality\b|\bfixation\b|\bmeta[- ]?feedback\b", re.IGNORECASE),
}


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _issue(field: str, message: str, *, severity: ValidationSeverity) -> dict[str, str]:
    return {"field": field, "message": message, "severity": severity.value}


def _report(
    *,
    ok: bool,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
    severity: ValidationSeverity = ValidationSeverity.FATAL,
    repairable: bool = False,
    repaired: bool = False,
    repair_attempts: list[dict[str, Any]] | None = None,
    stats: dict[str, Any] | None = None,
    forbidden_language_hits: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "severity": severity.value,
        "repairable": repairable,
        "repaired": repaired,
        "errors": errors,
        "warnings": warnings or [],
    }
    if repair_attempts is not None:
        payload["repair_attempts"] = repair_attempts
    if stats is not None:
        payload["stats"] = stats
    if forbidden_language_hits is not None:
        payload["forbidden_language_hits"] = forbidden_language_hits
    return payload


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_string_list(value: object, *, allow_empty: bool = True) -> bool:
    if not isinstance(value, list):
        return False
    if not allow_empty and not value:
        return False
    return all(_is_non_empty_string(item) for item in value)


def _collect_forbidden_language(field_name: str, value: object) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return []
    hits: list[dict[str, str]] = []
    for code, pattern in _FORBIDDEN_OUTPUT_PATTERNS.items():
        if pattern.search(value):
            hits.append({"field": field_name, "code": code})
    return hits


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def repair_aggregation_handoff(
    aggregation_handoff: dict[str, Any],
) -> dict[str, Any]:
    raw = aggregation_handoff if isinstance(aggregation_handoff, dict) else {}
    repaired = dict(raw)
    repair_actions: list[dict[str, str]] = []

    repaired["update_focus"] = _normalize_text(repaired.get("update_focus"))

    for field_name in ("merged_findings", "preserved_contradictions", "open_gaps"):
        if not isinstance(repaired.get(field_name), list):
            continue
        normalized_items: list[str] = []
        seen: set[str] = set()
        for item in repaired[field_name]:
            text = _normalize_text(item)
            if not text or text in seen:
                continue
            seen.add(text)
            normalized_items.append(text)
        if normalized_items != list(repaired[field_name]):
            repair_actions.append(
                {
                    "field": field_name,
                    "action": "normalize_list",
                    "reason": "Whitespace and duplicate sentence normalization applied.",
                }
            )
        repaired[field_name] = normalized_items

    return {
        "repaired_output": repaired,
        "repair_actions": repair_actions,
    }


def validate_worker_result_set(
    worker_result_set: dict[str, Any],
    *,
    expected_task_ids: set[str] | None = None,
) -> dict[str, Any]:
    raw = worker_result_set if isinstance(worker_result_set, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(worker_result_set, dict):
        errors.append(_error("worker_result_set",
                      "worker_result_set must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _WORKER_RESULT_SET_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "worker_result_set",
                f"worker_result_set contains unsupported fields: {unsupported_fields}.",
            )
        )

    batch_id = raw.get("batch_id")
    if not _is_non_empty_string(batch_id):
        errors.append(
            _error("batch_id", "batch_id must be a non-empty string."))

    round_id = raw.get("round_id")
    if not _is_non_empty_string(round_id):
        errors.append(
            _error("round_id", "round_id must be a non-empty string."))

    hypothesis_id = raw.get("hypothesis_id")
    normalized_hypothesis_id = str(hypothesis_id).strip(
    ) if _is_non_empty_string(hypothesis_id) else ""
    if not normalized_hypothesis_id:
        errors.append(
            _error("hypothesis_id", "hypothesis_id must be a non-empty string."))

    worker_results = raw.get("worker_results")
    if not isinstance(worker_results, list) or not worker_results:
        errors.append(
            _error("worker_results", "worker_results must be a non-empty list."))
        worker_results = []

    seen_task_ids: set[str] = set()
    evidence_ref_count = 0
    contradiction_count = 0
    limitation_count = 0
    non_success_count = 0

    for index, worker_result in enumerate(worker_results):
        field_prefix = f"worker_results[{index}]"
        if not isinstance(worker_result, dict):
            errors.append(
                _error(field_prefix, "Each worker_result must be an object."))
            continue

        unsupported_worker_fields = sorted(
            set(worker_result.keys()) - _WORKER_RESULT_FIELDS)
        if unsupported_worker_fields:
            errors.append(
                _error(
                    field_prefix,
                    f"worker_result contains unsupported fields: {unsupported_worker_fields}.",
                )
            )

        task_id = worker_result.get("task_id")
        if not _is_non_empty_string(task_id):
            errors.append(_error(f"{field_prefix}.task_id",
                          "task_id must be a non-empty string."))
        else:
            normalized_task_id = str(task_id).strip()
            if normalized_task_id in seen_task_ids:
                errors.append(
                    _error(f"{field_prefix}.task_id", f"Duplicate task_id '{normalized_task_id}'."))
            seen_task_ids.add(normalized_task_id)

        result_hypothesis_id = worker_result.get("hypothesis_id")
        if not _is_non_empty_string(result_hypothesis_id):
            errors.append(_error(
                f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
        elif str(result_hypothesis_id).strip() != normalized_hypothesis_id:
            errors.append(
                _error(
                    f"{field_prefix}.hypothesis_id",
                    f"worker_result hypothesis_id must match '{normalized_hypothesis_id}'.",
                )
            )

        status = worker_result.get("status")
        if status not in VALID_WORKER_STATUSES:
            errors.append(
                _error(
                    f"{field_prefix}.status",
                    f"status must be one of {sorted(VALID_WORKER_STATUSES)}.",
                )
            )
        elif status not in {"completed", "partial"}:
            non_success_count += 1
            warnings.append(_error(
                f"{field_prefix}.status", f"worker_result status is '{status}' and should remain visible downstream."))

        findings = worker_result.get("findings")
        if not _is_string_list(findings):
            errors.append(
                _error(f"{field_prefix}.findings", "findings must be a list of strings."))
            findings = []

        evidence_refs = worker_result.get("evidence_refs")
        if not _is_string_list(evidence_refs):
            errors.append(_error(
                f"{field_prefix}.evidence_refs", "evidence_refs must be a list of strings."))
            evidence_refs = []
        evidence_ref_count += len(evidence_refs)

        contradictions = worker_result.get("contradictions")
        if not _is_string_list(contradictions):
            errors.append(_error(
                f"{field_prefix}.contradictions", "contradictions must be a list of strings."))
            contradictions = []
        contradiction_count += len(contradictions)

        limitations = worker_result.get("limitations")
        if not _is_string_list(limitations):
            errors.append(
                _error(f"{field_prefix}.limitations", "limitations must be a list of strings."))
            limitations = []
        limitation_count += len(limitations)

        if status in {"completed", "partial"} and not findings:
            errors.append(_error(
                f"{field_prefix}.findings", f"status '{status}' requires at least one finding."))
        if status in {"completed", "partial"} and not evidence_refs:
            errors.append(_error(f"{field_prefix}.evidence_refs",
                          f"status '{status}' requires at least one evidence_ref."))
        if status == "failed" and not limitations:
            errors.append(_error(f"{field_prefix}.limitations",
                          "failed worker_result must explain at least one limitation."))

    if expected_task_ids is not None:
        missing_task_ids = sorted(expected_task_ids - seen_task_ids)
        extra_task_ids = sorted(seen_task_ids - expected_task_ids)
        if missing_task_ids:
            errors.append(_error(
                "worker_results", f"Missing worker_results for task_ids: {missing_task_ids}."))
        if extra_task_ids:
            errors.append(_error(
                "worker_results", f"Unexpected worker_results for task_ids: {extra_task_ids}."))

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "worker_result_count": len(worker_results),
            "evidence_ref_count": evidence_ref_count,
            "contradiction_count": contradiction_count,
            "limitation_count": limitation_count,
            "non_success_count": non_success_count,
        },
    )


def validate_aggregation_handoff(
    aggregation_handoff: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
    expected_hypothesis_id: str,
    known_evidence_refs: set[str],
    source_contradictions: set[str],
    source_gap_signal_count: int,
    source_finding_count: int,
) -> dict[str, Any]:
    raw = aggregation_handoff if isinstance(aggregation_handoff, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    repair_attempts: list[dict[str, Any]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not isinstance(aggregation_handoff, dict):
        errors.append(_issue("aggregation_handoff",
                      "aggregation_handoff must be an object.", severity=ValidationSeverity.FATAL))

    unsupported_fields = sorted(set(raw.keys()) - _AGGREGATION_HANDOFF_FIELDS)
    if unsupported_fields:
        errors.append(
            _issue(
                "aggregation_handoff",
                f"aggregation_handoff contains unsupported fields: {unsupported_fields}.",
                severity=ValidationSeverity.FATAL,
            )
        )

    for key, expected_value in (
        ("batch_id", expected_batch_id),
        ("round_id", expected_round_id),
        ("hypothesis_id", expected_hypothesis_id),
    ):
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(_issue(
                key, f"{key} must be a non-empty string.", severity=ValidationSeverity.FATAL))
        elif str(value).strip() != expected_value:
            errors.append(_issue(
                key, f"{key} must match '{expected_value}'.", severity=ValidationSeverity.FATAL))

    merged_findings = raw.get("merged_findings")
    if not _is_string_list(merged_findings):
        errors.append(_issue(
            "merged_findings", "merged_findings must be a list of strings.", severity=ValidationSeverity.FATAL))
        merged_findings = []
    elif source_finding_count > 0 and not merged_findings:
        errors.append(_issue(
            "merged_findings", "merged_findings must not be empty when worker findings are available.", severity=ValidationSeverity.FATAL))

    evidence_refs = raw.get("evidence_refs")
    if not _is_string_list(evidence_refs):
        errors.append(_issue(
            "evidence_refs", "evidence_refs must be a list of strings.", severity=ValidationSeverity.FATAL))
        evidence_refs = []
    else:
        for evidence_ref in evidence_refs:
            if evidence_ref not in known_evidence_refs:
                errors.append(_issue(
                    "evidence_refs", f"Unknown evidence_ref '{evidence_ref}'.", severity=ValidationSeverity.FATAL))
    if merged_findings and not evidence_refs:
        errors.append(_issue(
            "evidence_refs", "merged_findings require at least one evidence_ref.", severity=ValidationSeverity.FATAL))

    preserved_contradictions = raw.get("preserved_contradictions")
    if not _is_string_list(preserved_contradictions):
        errors.append(_issue("preserved_contradictions",
                      "preserved_contradictions must be a list of strings.", severity=ValidationSeverity.FATAL))
        preserved_contradictions = []
    else:
        for contradiction in preserved_contradictions:
            if contradiction not in source_contradictions:
                errors.append(
                    _issue(
                        "preserved_contradictions",
                        f"Unknown preserved_contradiction '{contradiction}'.",
                        severity=ValidationSeverity.FATAL,
                    )
                )
    if source_contradictions and not preserved_contradictions:
        errors.append(_issue("preserved_contradictions",
                      "Source contradictions must remain explicit in the handoff.", severity=ValidationSeverity.FATAL))

    open_gaps = raw.get("open_gaps")
    if not _is_string_list(open_gaps):
        errors.append(_issue(
            "open_gaps", "open_gaps must be a list of strings.", severity=ValidationSeverity.FATAL))
        open_gaps = []
    if source_gap_signal_count > 0 and not open_gaps:
        errors.append(_issue(
            "open_gaps", "open_gaps must remain explicit when source limitations or non-success results exist.", severity=ValidationSeverity.FATAL))

    update_focus = raw.get("update_focus")
    if not _is_non_empty_string(update_focus):
        errors.append(_issue(
            "update_focus", "update_focus must be a non-empty string.", severity=ValidationSeverity.FATAL))
    elif len(str(update_focus).strip()) > MAX_UPDATE_FOCUS_CHARS:
        warnings.append(_issue(
            "update_focus",
            f"update_focus exceeds the recommended {MAX_UPDATE_FOCUS_CHARS} characters; continuing.",
            severity=ValidationSeverity.WARNING,
        ))

    for index, finding in enumerate(merged_findings):
        forbidden_language_hits.extend(_collect_forbidden_language(
            f"merged_findings[{index}]", finding))
    for index, gap in enumerate(open_gaps):
        forbidden_language_hits.extend(
            _collect_forbidden_language(f"open_gaps[{index}]", gap))
    forbidden_language_hits.extend(
        _collect_forbidden_language("update_focus", update_focus))

    if forbidden_language_hits:
        warnings.extend(
            _issue(
                hit["field"], f"Semantic language flag detected ({hit['code']}).", severity=ValidationSeverity.WARNING)
            for hit in forbidden_language_hits
        )

    if known_evidence_refs and len(set(evidence_refs)) < min(1, len(known_evidence_refs)):
        warnings.append(_issue(
            "evidence_refs", "aggregation_handoff retained very little source evidence provenance.", severity=ValidationSeverity.WARNING))

    fatal_errors = [error for error in errors if error.get(
        "severity") == ValidationSeverity.FATAL.value]
    repairable_errors = [error for error in errors if error.get(
        "severity") == ValidationSeverity.REPAIRABLE.value]
    severity = ValidationSeverity.WARNING
    if fatal_errors:
        severity = ValidationSeverity.FATAL
    elif repairable_errors:
        severity = ValidationSeverity.REPAIRABLE

    ok = not fatal_errors and not repairable_errors

    return _report(
        ok=ok,
        errors=errors,
        warnings=warnings,
        severity=severity,
        repairable=bool(repairable_errors),
        repaired=False,
        repair_attempts=repair_attempts,
        stats={
            "merged_finding_count": len(merged_findings),
            "evidence_ref_count": len(evidence_refs),
            "preserved_contradiction_count": len(preserved_contradictions),
            "open_gap_count": len(open_gaps),
        },
        forbidden_language_hits=forbidden_language_hits,
    )
