"""Validation helpers for the Phase 3A State Manager runtime."""

from __future__ import annotations

import re
from typing import Any

from state_manager.contracts import MAX_UPDATE_FOCUS_CHARS, VALID_HYPOTHESIS_STATUSES


_CANONICAL_STATE_FIELDS = {
    "batch_id",
    "state_version",
    "structural_substrate",
    "interpretive_hypotheses",
    "revision_log",
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
_STATE_DELTA_RECORD_FIELDS = {
    "batch_id",
    "round_id",
    "hypothesis_id",
    "summary",
    "status",
    "evidence_refs",
    "preserved_contradictions",
    "open_gaps",
    "merged_findings",
    "update_focus",
    "applied_updates",
}
_ALLOWED_APPLIED_UPDATE_FIELDS = {
    "summary",
    "status",
    "evidence_refs",
    "preserved_contradictions",
    "open_gaps",
    "merged_findings",
    "update_focus",
}
_ALLOWED_STATUS_SHIFTS = {
    "unresolved": {"unresolved", "emerging", "active", "weakened", "reopened", "uncertain"},
    "emerging": {"emerging", "active", "weakened", "dormant", "reopened", "merged", "partially_absorbed", "uncertain"},
    "active": {"active", "weakened", "dormant", "reopened", "merged", "partially_absorbed", "uncertain"},
    "weakened": {"weakened", "active", "dormant", "reopened", "merged", "partially_absorbed", "uncertain"},
    "dormant": {"dormant", "reopened", "merged", "partially_absorbed", "uncertain"},
    "reopened": {"reopened", "active", "weakened", "dormant", "merged", "partially_absorbed", "uncertain"},
    "merged": {"merged"},
    "partially_absorbed": {"partially_absorbed", "merged", "reopened", "active", "weakened", "uncertain"},
    "uncertain": {"uncertain", "active", "weakened", "dormant", "reopened", "merged", "partially_absorbed"},
}
_FORBIDDEN_OUTPUT_PATTERNS = {
    "planning_language": re.compile(r"\bplan(?:ning|ned|s)?\b|\bstrategy\b|\brout(?:e|ing|er)\b", re.IGNORECASE),
    "aggregation_language": re.compile(r"\bworker\b|\bre-?aggregat(?:e|ion)\b", re.IGNORECASE),
    "critic_language": re.compile(r"\bcritic\b|\bprocess quality\b|\bfixation\b|\bmeta[- ]?feedback\b", re.IGNORECASE),
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
    for code, pattern in _FORBIDDEN_OUTPUT_PATTERNS.items():
        if pattern.search(value):
            hits.append({"field": field_name, "code": code})
    return hits


def validate_canonical_batch_state(
    canonical_batch_state: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_hypothesis_id: str,
    expected_state_version: int | None = None,
) -> dict[str, Any]:
    raw = canonical_batch_state if isinstance(canonical_batch_state, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(canonical_batch_state, dict):
        errors.append(_error("canonical_batch_state", "canonical_batch_state must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _CANONICAL_STATE_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "canonical_batch_state",
                f"canonical_batch_state contains unsupported fields: {unsupported_fields}.",
            )
        )

    batch_id = raw.get("batch_id")
    if not _is_non_empty_string(batch_id):
        errors.append(_error("batch_id", "batch_id must be a non-empty string."))
    elif str(batch_id).strip() != expected_batch_id:
        errors.append(_error("batch_id", f"batch_id must match '{expected_batch_id}'."))

    state_version = _int_value(raw.get("state_version"))
    if state_version is None or state_version < 1:
        errors.append(_error("state_version", "state_version must be an integer greater than or equal to 1."))
    elif expected_state_version is not None and state_version != expected_state_version:
        errors.append(
            _error(
                "state_version",
                f"state_version must match the expected prior version '{expected_state_version}'.",
            )
        )

    structural_substrate = raw.get("structural_substrate")
    if not isinstance(structural_substrate, dict):
        errors.append(_error("structural_substrate", "structural_substrate must be an object."))
        structural_substrate = {}
    substrate_batch_id = structural_substrate.get("batch_id")
    if substrate_batch_id and str(substrate_batch_id).strip() != expected_batch_id:
        errors.append(_error("structural_substrate.batch_id", "structural_substrate batch_id must match the canonical batch state."))

    interpretive_hypotheses = raw.get("interpretive_hypotheses")
    if not isinstance(interpretive_hypotheses, list) or not interpretive_hypotheses:
        errors.append(_error("interpretive_hypotheses", "interpretive_hypotheses must be a non-empty list."))
        interpretive_hypotheses = []

    seen_hypothesis_ids: set[str] = set()
    target_found = False
    for index, hypothesis in enumerate(interpretive_hypotheses):
        field_prefix = f"interpretive_hypotheses[{index}]"
        if not isinstance(hypothesis, dict):
            errors.append(_error(field_prefix, "Each interpretive_hypothesis must be an object."))
            continue

        hypothesis_id = hypothesis.get("hypothesis_id")
        if not _is_non_empty_string(hypothesis_id):
            errors.append(_error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
            continue
        normalized_hypothesis_id = str(hypothesis_id).strip()
        if normalized_hypothesis_id in seen_hypothesis_ids:
            errors.append(_error(f"{field_prefix}.hypothesis_id", f"Duplicate hypothesis_id '{normalized_hypothesis_id}'."))
        seen_hypothesis_ids.add(normalized_hypothesis_id)
        if normalized_hypothesis_id == expected_hypothesis_id:
            target_found = True

        summary = hypothesis.get("summary")
        if not _is_non_empty_string(summary):
            errors.append(_error(f"{field_prefix}.summary", "summary must be a non-empty string."))

        status = hypothesis.get("status")
        if not _is_non_empty_string(status):
            errors.append(_error(f"{field_prefix}.status", "status must be a non-empty string."))
        elif str(status).strip() not in VALID_HYPOTHESIS_STATUSES:
            errors.append(
                _error(
                    f"{field_prefix}.status",
                    f"status must be one of {sorted(VALID_HYPOTHESIS_STATUSES)}.",
                )
            )

        evidence_refs = _string_list(hypothesis.get("evidence_refs"), allow_empty=False)
        if evidence_refs is None:
            errors.append(_error(f"{field_prefix}.evidence_refs", "evidence_refs must be a non-empty list of strings."))

        for list_field in ("open_gaps", "preserved_contradictions", "merged_findings"):
            normalized_list = _string_list(hypothesis.get(list_field))
            if normalized_list is None:
                errors.append(_error(f"{field_prefix}.{list_field}", f"{list_field} must be a list of strings."))

    if not target_found:
        errors.append(_error("interpretive_hypotheses", f"target hypothesis_id '{expected_hypothesis_id}' is not present in canonical_batch_state."))

    revision_log = raw.get("revision_log")
    if not isinstance(revision_log, list):
        errors.append(_error("revision_log", "revision_log must be a list."))
        revision_log = []

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "state_version": state_version or 0,
            "hypothesis_count": len(interpretive_hypotheses),
            "revision_count": len(revision_log),
        },
    )


def validate_aggregation_handoff_input(
    aggregation_handoff: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
    expected_hypothesis_id: str,
) -> dict[str, Any]:
    raw = aggregation_handoff if isinstance(aggregation_handoff, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(aggregation_handoff, dict):
        errors.append(_error("aggregation_handoff", "aggregation_handoff must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _AGGREGATION_HANDOFF_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "aggregation_handoff",
                f"aggregation_handoff contains unsupported fields: {unsupported_fields}.",
            )
        )

    for key, expected_value in (
        ("batch_id", expected_batch_id),
        ("round_id", expected_round_id),
        ("hypothesis_id", expected_hypothesis_id),
    ):
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(key, f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(key, f"{key} must match '{expected_value}'."))

    merged_findings = _string_list(raw.get("merged_findings"), allow_empty=False)
    if merged_findings is None:
        errors.append(_error("merged_findings", "merged_findings must be a non-empty list of strings."))
        merged_findings = []

    evidence_refs = _string_list(raw.get("evidence_refs"), allow_empty=False)
    if evidence_refs is None:
        errors.append(_error("evidence_refs", "evidence_refs must be a non-empty list of strings."))
        evidence_refs = []

    preserved_contradictions = _string_list(raw.get("preserved_contradictions"))
    if preserved_contradictions is None:
        errors.append(_error("preserved_contradictions", "preserved_contradictions must be a list of strings."))
        preserved_contradictions = []

    open_gaps = _string_list(raw.get("open_gaps"))
    if open_gaps is None:
        errors.append(_error("open_gaps", "open_gaps must be a list of strings."))
        open_gaps = []

    update_focus = raw.get("update_focus")
    if not _is_non_empty_string(update_focus):
        errors.append(_error("update_focus", "update_focus must be a non-empty string."))
    elif len(str(update_focus).strip()) > MAX_UPDATE_FOCUS_CHARS:
        warnings.append(
            _error(
                "update_focus",
                f"update_focus exceeds the recommended {MAX_UPDATE_FOCUS_CHARS} characters; continuing.",
            )
        )

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "merged_finding_count": len(merged_findings),
            "evidence_ref_count": len(evidence_refs),
            "preserved_contradiction_count": len(preserved_contradictions),
            "open_gap_count": len(open_gaps),
        },
    )


def validate_state_delta_record(
    state_delta_record: dict[str, Any],
    *,
    current_hypothesis: dict[str, Any],
    aggregation_handoff: dict[str, Any],
    known_evidence_refs: set[str],
) -> dict[str, Any]:
    raw = state_delta_record if isinstance(state_delta_record, dict) else {}
    current = current_hypothesis if isinstance(current_hypothesis, dict) else {}
    handoff = aggregation_handoff if isinstance(aggregation_handoff, dict) else {}

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not isinstance(state_delta_record, dict):
        errors.append(_error("state_delta_record", "state_delta_record must be an object."))

    unsupported_fields = sorted(set(raw.keys()) - _STATE_DELTA_RECORD_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "state_delta_record",
                f"state_delta_record contains unsupported fields: {unsupported_fields}.",
            )
        )

    for key in ("batch_id", "round_id", "hypothesis_id"):
        expected_value = str(handoff.get(key, "") or "").strip()
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(key, f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(key, f"{key} must match '{expected_value}'."))

    summary = raw.get("summary")
    if not _is_non_empty_string(summary):
        errors.append(_error("summary", "summary must be a non-empty string."))

    status = raw.get("status")
    current_status = str(current.get("status", "unresolved") or "unresolved").strip() or "unresolved"
    if not _is_non_empty_string(status):
        errors.append(_error("status", "status must be a non-empty string."))
    else:
        normalized_status = str(status).strip()
        if normalized_status not in VALID_HYPOTHESIS_STATUSES:
            errors.append(_error("status", f"status must be one of {sorted(VALID_HYPOTHESIS_STATUSES)}."))
        elif normalized_status not in _ALLOWED_STATUS_SHIFTS.get(current_status, VALID_HYPOTHESIS_STATUSES):
            errors.append(
                _error(
                    "status",
                    f"status shift from '{current_status}' to '{normalized_status}' is not allowed.",
                )
            )

    evidence_refs = _string_list(raw.get("evidence_refs"), allow_empty=False)
    if evidence_refs is None:
        errors.append(_error("evidence_refs", "evidence_refs must be a non-empty list of strings."))
        evidence_refs = []
    else:
        required_evidence_refs = set(_string_list(current.get("evidence_refs")) or [])
        required_evidence_refs.update(_string_list(handoff.get("evidence_refs")) or [])
        missing_evidence_refs = sorted(required_evidence_refs - set(evidence_refs))
        if missing_evidence_refs:
            errors.append(
                _error(
                    "evidence_refs",
                    f"state_delta_record dropped required evidence_refs: {missing_evidence_refs}.",
                )
            )
        for evidence_ref in evidence_refs:
            if evidence_ref not in known_evidence_refs:
                errors.append(_error("evidence_refs", f"Unknown evidence_ref '{evidence_ref}'."))

    applied_updates = raw.get("applied_updates")
    if not isinstance(applied_updates, list) or not applied_updates:
        errors.append(_error("applied_updates", "applied_updates must be a non-empty list."))
        applied_updates = []

    updated_fields: set[str] = set()
    for index, update in enumerate(applied_updates):
        field_prefix = f"applied_updates[{index}]"
        if not isinstance(update, dict):
            errors.append(_error(field_prefix, "Each applied_update must be an object."))
            continue
        field_name = update.get("field")
        if not _is_non_empty_string(field_name):
            errors.append(_error(f"{field_prefix}.field", "field must be a non-empty string."))
        else:
            normalized_field_name = str(field_name).strip()
            if normalized_field_name not in _ALLOWED_APPLIED_UPDATE_FIELDS:
                errors.append(
                    _error(
                        f"{field_prefix}.field",
                        f"field must be one of {sorted(_ALLOWED_APPLIED_UPDATE_FIELDS)}.",
                    )
                )
            else:
                updated_fields.add(normalized_field_name)
        reason = update.get("reason")
        if not _is_non_empty_string(reason):
            errors.append(_error(f"{field_prefix}.reason", "reason must be a non-empty string."))

    preserved_contradictions = _string_list(raw.get("preserved_contradictions"))
    if preserved_contradictions is None:
        errors.append(_error("preserved_contradictions", "preserved_contradictions must be a list of strings."))
        preserved_contradictions = []
    else:
        required_contradictions = set(_string_list(current.get("preserved_contradictions")) or [])
        required_contradictions.update(_string_list(handoff.get("preserved_contradictions")) or [])
        missing_contradictions = sorted(required_contradictions - set(preserved_contradictions))
        if missing_contradictions and "preserved_contradictions" not in updated_fields:
            errors.append(
                _error(
                    "preserved_contradictions",
                    "state_delta_record removed prior contradictions without an explicit preserved_contradictions update: "
                    f"{missing_contradictions}.",
                )
            )

    open_gaps = _string_list(raw.get("open_gaps"))
    if open_gaps is None:
        errors.append(_error("open_gaps", "open_gaps must be a list of strings."))
        open_gaps = []
    else:
        required_open_gaps = set(_string_list(current.get("open_gaps")) or [])
        required_open_gaps.update(_string_list(handoff.get("open_gaps")) or [])
        missing_open_gaps = sorted(required_open_gaps - set(open_gaps))
        if missing_open_gaps and "open_gaps" not in updated_fields:
            errors.append(
                _error(
                    "open_gaps",
                    "state_delta_record removed prior open_gaps without an explicit open_gaps update: "
                    f"{missing_open_gaps}.",
                )
            )

    merged_findings = _string_list(raw.get("merged_findings"), allow_empty=False)
    if merged_findings is None:
        errors.append(_error("merged_findings", "merged_findings must be a non-empty list of strings."))
        merged_findings = []
    else:
        required_findings = set(_string_list(current.get("merged_findings")) or [])
        required_findings.update(_string_list(handoff.get("merged_findings")) or [])
        missing_findings = sorted(required_findings - set(merged_findings))
        if missing_findings and "merged_findings" not in updated_fields:
            errors.append(
                _error(
                    "merged_findings",
                    "state_delta_record removed prior merged_findings without an explicit merged_findings update: "
                    f"{missing_findings}.",
                )
            )

    update_focus = raw.get("update_focus")
    if not _is_non_empty_string(update_focus):
        errors.append(_error("update_focus", "update_focus must be a non-empty string."))
    elif len(str(update_focus).strip()) > MAX_UPDATE_FOCUS_CHARS:
        errors.append(
            _error(
                "update_focus",
                f"update_focus must stay under {MAX_UPDATE_FOCUS_CHARS} characters.",
            )
        )

    forbidden_text_fields = [
        ("summary", summary),
        ("update_focus", update_focus),
    ]
    for index, finding in enumerate(merged_findings):
        forbidden_text_fields.append((f"merged_findings[{index}]", finding))
    for index, gap in enumerate(open_gaps):
        forbidden_text_fields.append((f"open_gaps[{index}]", gap))
    for index, contradiction in enumerate(preserved_contradictions):
        forbidden_text_fields.append((f"preserved_contradictions[{index}]", contradiction))
    for index, update in enumerate(applied_updates):
        if isinstance(update, dict):
            forbidden_text_fields.append((f"applied_updates[{index}].reason", update.get("reason")))

    for field_name, value in forbidden_text_fields:
        forbidden_language_hits.extend(_collect_forbidden_language(field_name, value))

    if forbidden_language_hits:
        warnings.extend(
            _error(hit["field"], f"Semantic language flag detected ({hit['code']}).")
            for hit in forbidden_language_hits
        )

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "applied_update_count": len(applied_updates),
            "evidence_ref_count": len(evidence_refs),
            "preserved_contradiction_count": len(preserved_contradictions),
            "open_gap_count": len(open_gaps),
            "merged_finding_count": len(merged_findings),
        },
        forbidden_language_hits=forbidden_language_hits,
    )