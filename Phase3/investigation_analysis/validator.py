"""Validation helpers for the Phase 3A Investigation Analysis runtime."""

from __future__ import annotations

import re
from typing import Any


_FORBIDDEN_LANGUAGE_PATTERNS = {
    "prioritization_language": re.compile(
        r"\bprioriti[sz](?:e|ed|ing|ation)?\b|\bbudget\b|\bhighest priority\b",
        re.IGNORECASE,
    ),
    "planning_language": re.compile(
        r"\bplan(?:ning|ned|s)?\b|\btask package\b|\bwork package\b|\bmust-do\b",
        re.IGNORECASE,
    ),
    "routing_language": re.compile(
        r"\broute(?:d|s|ing)?\b|\bworker\b|\bexecutor\b",
        re.IGNORECASE,
    ),
    "execution_language": re.compile(
        r"\bexecute(?:d|s|ing)?\b|\brun(?:ning)?\b the (?:tool|check|worker)",
        re.IGNORECASE,
    ),
    "closure_language": re.compile(
        r"\bclose(?:d|s|ure)?\b|\bsaturat(?:e|ed|ion)\b",
        re.IGNORECASE,
    ),
    "certainty_language": re.compile(
        r"\bconfirmed?\b|\bdefinitive(?:ly)?\b|\bprove[sd]?\b|\bcertif(?:y|ied)\b|\bguarantee(?:d|s)?\b",
        re.IGNORECASE,
    ),
    "verdict_language": re.compile(
        r"\bground truth\b|\bconclusive(?:ly)?\b|\bartifact exists\b|\bfinal verdict\b",
        re.IGNORECASE,
    ),
    "next_step_language": re.compile(
        r"\bnext step\b|\bstart with\b|\bfirst investigate\b|\bshould investigate next\b",
        re.IGNORECASE,
    ),
}


def _error(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _report(
    *,
    ok: bool,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]] | None = None,
    stats: dict[str, Any] | None = None,
    invariants: dict[str, Any] | None = None,
    forbidden_language_hits: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "errors": errors,
        "warnings": warnings or [],
    }
    if stats is not None:
        payload["stats"] = stats
    if invariants is not None:
        payload["invariants"] = invariants
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
    for code, pattern in _FORBIDDEN_LANGUAGE_PATTERNS.items():
        if pattern.search(value):
            hits.append({"field": field_name, "code": code})
    return hits


def validate_analysis_context_min(analysis_context_min: dict[str, Any]) -> dict[str, Any]:
    raw = analysis_context_min if isinstance(analysis_context_min, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(analysis_context_min, dict):
        errors.append(_error("analysis_context_min", "analysis_context_min must be an object."))

    partition_context_ref = raw.get("partition_context_ref")
    if not isinstance(partition_context_ref, dict):
        errors.append(_error("partition_context_ref", "partition_context_ref must be an object."))
        partition_context_ref = {}

    for key in ("semantics", "expected_properties", "epistemic_warnings", "investigation_guidance"):
        value = partition_context_ref.get(key)
        if not isinstance(value, list):
            errors.append(_error(f"partition_context_ref.{key}", f"{key} must be a list."))
            continue
        if not all(_is_non_empty_string(item) for item in value):
            errors.append(
                _error(
                    f"partition_context_ref.{key}",
                    f"{key} must contain only non-empty strings.",
                )
            )

    artifact_framing_refs = raw.get("artifact_framing_refs")
    if not isinstance(artifact_framing_refs, list) or not artifact_framing_refs:
        errors.append(_error("artifact_framing_refs", "artifact_framing_refs must be a non-empty list."))
        artifact_framing_refs = []

    for index, framing_ref in enumerate(artifact_framing_refs):
        field_prefix = f"artifact_framing_refs[{index}]"
        if not isinstance(framing_ref, dict):
            errors.append(_error(field_prefix, "Each artifact framing ref must be an object."))
            continue
        if not _is_non_empty_string(framing_ref.get("framing_id")):
            errors.append(_error(f"{field_prefix}.framing_id", "framing_id must be a non-empty string."))
        if not _is_non_empty_string(framing_ref.get("label")):
            errors.append(_error(f"{field_prefix}.label", "label must be a non-empty string."))
        if not _is_non_empty_string(framing_ref.get("description")):
            errors.append(_error(f"{field_prefix}.description", "description must be a non-empty string."))

    return _report(
        ok=not errors,
        errors=errors,
        stats={"artifact_framing_count": len(artifact_framing_refs)},
    )


def validate_analysis_iteration_context_min(
    analysis_iteration_context_min: dict[str, Any] | None,
) -> dict[str, Any]:
    if analysis_iteration_context_min in (None, {}):
        return _report(ok=True, errors=[], stats={"mode": "initial"})

    raw = analysis_iteration_context_min if isinstance(analysis_iteration_context_min, dict) else {}
    errors: list[dict[str, str]] = []

    if not isinstance(analysis_iteration_context_min, dict):
        errors.append(
            _error(
                "analysis_iteration_context_min",
                "analysis_iteration_context_min must be an object when provided.",
            )
        )

    initial_hypothesis_set_ref = raw.get("initial_hypothesis_set_ref")
    if not isinstance(initial_hypothesis_set_ref, dict):
        errors.append(
            _error(
                "initial_hypothesis_set_ref",
                "initial_hypothesis_set_ref must be an object when iteration context is provided.",
            )
        )
        initial_hypothesis_set_ref = {}

    if not _is_non_empty_string(initial_hypothesis_set_ref.get("analysis_id")):
        errors.append(
            _error(
                "initial_hypothesis_set_ref.analysis_id",
                "analysis_id must be a non-empty string.",
            )
        )

    hypothesis_refs = initial_hypothesis_set_ref.get("hypothesis_refs")
    if not isinstance(hypothesis_refs, list) or not hypothesis_refs:
        errors.append(
            _error(
                "initial_hypothesis_set_ref.hypothesis_refs",
                "hypothesis_refs must be a non-empty list.",
            )
        )
        hypothesis_refs = []

    for index, hypothesis_ref in enumerate(hypothesis_refs):
        field_prefix = f"initial_hypothesis_set_ref.hypothesis_refs[{index}]"
        if not isinstance(hypothesis_ref, dict):
            errors.append(_error(field_prefix, "Each hypothesis ref must be an object."))
            continue
        if not _is_non_empty_string(hypothesis_ref.get("hypothesis_id")):
            errors.append(
                _error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string.")
            )
        if not _is_non_empty_string(hypothesis_ref.get("summary")):
            errors.append(_error(f"{field_prefix}.summary", "summary must be a non-empty string."))

    current_state_ref = raw.get("current_state_ref")
    if not isinstance(current_state_ref, dict):
        errors.append(
            _error(
                "current_state_ref",
                "current_state_ref must be an object when iteration context is provided.",
            )
        )
        current_state_ref = {}

    if not _is_non_empty_string(current_state_ref.get("state_id")):
        errors.append(_error("current_state_ref.state_id", "state_id must be a non-empty string."))
    if not _is_string_list(current_state_ref.get("state_notes")):
        errors.append(_error("current_state_ref.state_notes", "state_notes must be a list of strings."))

    return _report(
        ok=not errors,
        errors=errors,
        stats={
            "mode": "rerun",
            "prior_hypothesis_count": len(hypothesis_refs),
        },
    )


def _compute_overlap_pair_count(hypotheses: list[dict[str, Any]]) -> int:
    overlap_pair_count = 0
    normalized_evidence_refs: list[set[str]] = []
    for hypothesis in hypotheses:
        evidence_refs = hypothesis.get("evidence_refs") if isinstance(hypothesis, dict) else []
        normalized_evidence_refs.append(set(item for item in evidence_refs if isinstance(item, str)))

    for left_index, left in enumerate(normalized_evidence_refs):
        if not left:
            continue
        for right in normalized_evidence_refs[left_index + 1 :]:
            if left.intersection(right):
                overlap_pair_count += 1
    return overlap_pair_count


def validate_hypothesis_set(
    hypothesis_set: dict[str, Any],
    *,
    valid_evidence_ids: set[str] | None = None,
    expected_batch_id: str | None = None,
) -> dict[str, Any]:
    raw = hypothesis_set if isinstance(hypothesis_set, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []

    if not isinstance(hypothesis_set, dict):
        errors.append(_error("hypothesis_set", "hypothesis_set must be an object."))

    if not _is_non_empty_string(raw.get("analysis_id")):
        errors.append(_error("analysis_id", "analysis_id must be a non-empty string."))

    batch_id = raw.get("batch_id")
    if not _is_non_empty_string(batch_id):
        errors.append(_error("batch_id", "batch_id must be a non-empty string."))
    elif expected_batch_id and str(batch_id).strip() != expected_batch_id:
        errors.append(_error("batch_id", f"batch_id must match '{expected_batch_id}'."))

    hypotheses = raw.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        errors.append(_error("hypotheses", "hypotheses must be a non-empty list."))
        hypotheses = []
    elif len(hypotheses) > 10:
        errors.append(_error("hypotheses", "hypotheses may contain at most 10 entries."))

    seen_hypothesis_ids: set[str] = set()
    distinct_evidence_refs: set[str] = set()
    total_open_questions = 0

    for index, hypothesis in enumerate(hypotheses):
        field_prefix = f"hypotheses[{index}]"
        if not isinstance(hypothesis, dict):
            errors.append(_error(field_prefix, "Each hypothesis must be an object."))
            continue

        hypothesis_id = hypothesis.get("hypothesis_id")
        if not _is_non_empty_string(hypothesis_id):
            errors.append(_error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
        else:
            normalized_hypothesis_id = str(hypothesis_id).strip()
            if normalized_hypothesis_id in seen_hypothesis_ids:
                errors.append(
                    _error(
                        f"{field_prefix}.hypothesis_id",
                        f"Duplicate hypothesis_id '{normalized_hypothesis_id}'.",
                    )
                )
            seen_hypothesis_ids.add(normalized_hypothesis_id)

        summary = hypothesis.get("summary")
        if not _is_non_empty_string(summary):
            errors.append(_error(f"{field_prefix}.summary", "summary must be a non-empty string."))
        else:
            forbidden_language_hits.extend(_collect_forbidden_language(f"{field_prefix}.summary", summary))

        evidence_refs = hypothesis.get("evidence_refs")
        if not _is_string_list(evidence_refs, allow_empty=False):
            errors.append(
                _error(
                    f"{field_prefix}.evidence_refs",
                    "evidence_refs must be a non-empty list of strings.",
                )
            )
            evidence_refs = []

        open_questions = hypothesis.get("open_questions")
        if not _is_string_list(open_questions, allow_empty=False):
            errors.append(
                _error(
                    f"{field_prefix}.open_questions",
                    "open_questions must be a non-empty list of strings.",
                )
            )
            open_questions = []
        else:
            total_open_questions += len(open_questions)
            for question_index, open_question in enumerate(open_questions):
                forbidden_language_hits.extend(
                    _collect_forbidden_language(
                        f"{field_prefix}.open_questions[{question_index}]",
                        open_question,
                    )
                )

        for evidence_ref in evidence_refs:
            distinct_evidence_refs.add(evidence_ref)
            if valid_evidence_ids is not None and evidence_ref not in valid_evidence_ids:
                errors.append(
                    _error(
                        f"{field_prefix}.evidence_refs",
                        f"Unknown evidence_ref '{evidence_ref}'.",
                    )
                )

    for hit in forbidden_language_hits:
        warnings.append(
            _error(
                hit["field"],
                f"Semantic language flag detected ({hit['code']}).",
            )
        )

    stats = {
        "hypothesis_count": len(hypotheses),
        "open_question_count": total_open_questions,
        "distinct_evidence_ref_count": len(distinct_evidence_refs),
        "overlap_pair_count": _compute_overlap_pair_count(hypotheses),
    }
    invariants = {
        "bounded_hypothesis_count": len(hypotheses) <= 10,
        "grounded_only": all(error["message"].startswith("Unknown evidence_ref") is False for error in errors),
        "open_questions_present": total_open_questions >= len(hypotheses),
        "non_empty_hypothesis_space": len(hypotheses) > 0,
    }

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats=stats,
        invariants=invariants,
        forbidden_language_hits=forbidden_language_hits,
    )