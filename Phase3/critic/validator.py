"""Validation helpers for the Phase 3A Critic runtime."""

from __future__ import annotations

import re
from typing import Any

from critic.contracts import (
    MAX_CRITIC_OBSERVATIONS,
    MAX_OBSERVED_ISSUE_CHARS,
    MAX_PROMPT_SNIPPET_CHARS,
    MAX_RATIONALE_CHARS,
    MAX_SUGGESTION_CHARS,
    VALID_MODULE_NAMES,
    VALID_OBSERVATION_TYPES,
    VALID_PRIORITIES,
    VALID_TARGET_MODULES,
)


_CRITIC_CONTEXT_FIELDS = {
    "critic_input_min",
    "semantic_landscape_summary",
    "hypothesis_universe",
    "investigation_history",
    "ranking_history",
    "investigation_outcomes",
    "active_hypothesis_gaps",
}
_CRITIC_INPUT_MIN_FIELDS = {
    "batch_id",
    "round_id",
}
_SEMANTIC_LANDSCAPE_REGION_FIELDS = {
    "region_id",
    "kind",
    "status",
}
_HYPOTHESIS_UNIVERSE_ITEM_FIELDS = {
    "hypothesis_id",
    "status",
    "one_line_summary",
}
_ACTIVE_GAP_ITEM_FIELDS = {
    "hypothesis_id",
    "open_gaps",
}
_INVESTIGATION_HISTORY_FIELDS = {
    "round_id",
    "selected_hypothesis_ids",
    "state_version_start",
    "state_version_end",
}
_RANKING_HISTORY_FIELDS = {
    "round_id",
    "candidate_hypothesis_ids",
    "selected_hypothesis_ids",
}
_INVESTIGATION_OUTCOME_FIELDS = {
    "round_id",
    "hypothesis_id",
    "revision_delta",
    "new_findings_count",
    "resolved_gaps_count",
    "state_change_summary",
}
_CRITIC_OBSERVATIONS_PAYLOAD_FIELDS = {
    "batch_id",
    "round_id",
    "critic_observations",
}
_CRITIC_OBSERVATION_FIELDS = {
    "observation_id",
    "observation_type",
    "target_module",
    "priority",
    "hypothesis_ids",
    "rationale",
    "guidance",
    "prompt_snippet",
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


_VALID_REGION_KINDS = {
    "redundancy_region",
    "dependency_region",
    "concentration_region",
    "low_diversity_region",
    "localized_separability_region",
    "representation_sensitive_region",
    "topology_motif_region",
    "mixed_structural_region",
}


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
        errors.append(
            _error("critic_context", "critic_context must be an object."))

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
        errors.append(_error("critic_input_min",
                      "critic_input_min must be an object."))
        critic_input_min = {}
    else:
        unsupported_fields = sorted(
            set(critic_input_min.keys()) - _CRITIC_INPUT_MIN_FIELDS)
        if unsupported_fields:
            errors.append(_error(
                "critic_input_min", f"critic_input_min contains unsupported fields: {unsupported_fields}."))

    for key, expected_value in (("batch_id", expected_batch_id), ("round_id", expected_round_id)):
        value = critic_input_min.get(key)
        if not _is_non_empty_string(value):
            errors.append(
                _error(f"critic_input_min.{key}", f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(
                _error(f"critic_input_min.{key}", f"{key} must match '{expected_value}'."))

    # Validate compressed semantic landscape: {"regions": [...]}
    semantic_landscape_summary = raw.get("semantic_landscape_summary")
    region_count = 0
    if not isinstance(semantic_landscape_summary, dict):
        errors.append(_error("semantic_landscape_summary",
                      "semantic_landscape_summary must be an object."))
        semantic_landscape_summary = {}
    else:
        unsupported_fields = sorted(
            set(semantic_landscape_summary.keys()) - {"regions"})
        if unsupported_fields:
            errors.append(_error("semantic_landscape_summary",
                          f"semantic_landscape_summary must only contain 'regions'. Found: {unsupported_fields}."))
        regions = semantic_landscape_summary.get("regions")
        if not isinstance(regions, list):
            errors.append(_error("semantic_landscape_summary.regions",
                          "regions must be a list."))
            regions = []
        else:
            seen_region_ids: set[str] = set()
            for index, region in enumerate(regions):
                field_prefix = f"semantic_landscape_summary.regions[{index}]"
                if not isinstance(region, dict):
                    errors.append(_error(field_prefix, "Each region must be an object."))
                    continue
                unsupported = sorted(set(region.keys()) - _SEMANTIC_LANDSCAPE_REGION_FIELDS)
                if unsupported:
                    errors.append(_error(field_prefix, f"Unsupported fields: {unsupported}."))
                region_id = region.get("region_id")
                if not _is_non_empty_string(region_id):
                    errors.append(_error(f"{field_prefix}.region_id", "region_id must be a non-empty string."))
                else:
                    normalized_id = str(region_id).strip()
                    if normalized_id in seen_region_ids:
                        errors.append(_error(f"{field_prefix}.region_id", "region_id must be unique."))
                    seen_region_ids.add(normalized_id)
                kind = region.get("kind")
                if not _is_non_empty_string(kind):
                    errors.append(_error(f"{field_prefix}.kind", "kind must be a non-empty string."))
                elif str(kind).strip() not in _VALID_REGION_KINDS:
                    errors.append(_error(f"{field_prefix}.kind",
                                  f"kind must be a valid region kind. Got: '{kind}'."))
                status = region.get("status")
                if not _is_non_empty_string(status):
                    errors.append(_error(f"{field_prefix}.status", "status must be a non-empty string."))
            region_count = len(regions)

    # Validate lightweight hypothesis universe: [{hypothesis_id, status, one_line_summary}]
    def _validate_hypothesis_universe() -> list[dict[str, Any]]:
        items = raw.get("hypothesis_universe")
        if not isinstance(items, list):
            errors.append(_error("hypothesis_universe", "hypothesis_universe must be a list."))
            return []
        if not items:
            errors.append(_error("hypothesis_universe", "hypothesis_universe must be a non-empty list."))
        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(items):
            field_prefix = f"hypothesis_universe[{index}]"
            if not isinstance(item, dict):
                errors.append(_error(field_prefix, "Each item must be an object."))
                continue
            unsupported = sorted(set(item.keys()) - _HYPOTHESIS_UNIVERSE_ITEM_FIELDS)
            if unsupported:
                errors.append(_error(field_prefix, f"Unsupported fields: {unsupported}."))
            hypothesis_id = item.get("hypothesis_id")
            if not _is_non_empty_string(hypothesis_id):
                errors.append(_error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
            else:
                normalized_id = str(hypothesis_id).strip()
                if normalized_id in seen_ids:
                    errors.append(_error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be unique."))
                seen_ids.add(normalized_id)
            if not _is_non_empty_string(item.get("status")):
                errors.append(_error(f"{field_prefix}.status", "status must be a non-empty string."))
            if not _is_non_empty_string(item.get("one_line_summary")):
                errors.append(_error(f"{field_prefix}.one_line_summary", "one_line_summary must be a non-empty string."))
            elif len(str(item.get("one_line_summary")).strip()) > 200:
                errors.append(_error(f"{field_prefix}.one_line_summary", "one_line_summary must be at most 200 characters."))
            normalized.append(item)
        return normalized

    hypothesis_universe = _validate_hypothesis_universe()

    # Validate active_hypothesis_gaps: [{hypothesis_id, open_gaps}]
    def _validate_active_gaps() -> list[dict[str, Any]]:
        items = raw.get("active_hypothesis_gaps")
        if not isinstance(items, list):
            errors.append(_error("active_hypothesis_gaps", "active_hypothesis_gaps must be a list."))
            return []
        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, item in enumerate(items):
            field_prefix = f"active_hypothesis_gaps[{index}]"
            if not isinstance(item, dict):
                errors.append(_error(field_prefix, "Each item must be an object."))
                continue
            unsupported = sorted(set(item.keys()) - _ACTIVE_GAP_ITEM_FIELDS)
            if unsupported:
                errors.append(_error(field_prefix, f"Unsupported fields: {unsupported}."))
            hypothesis_id = item.get("hypothesis_id")
            if not _is_non_empty_string(hypothesis_id):
                errors.append(_error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
            else:
                normalized_id = str(hypothesis_id).strip()
                if normalized_id in seen_ids:
                    errors.append(_error(f"{field_prefix}.hypothesis_id", "hypothesis_id must be unique."))
                seen_ids.add(normalized_id)
            open_gaps = _string_list(item.get("open_gaps"))
            if open_gaps is None:
                errors.append(_error(f"{field_prefix}.open_gaps", "open_gaps must be a list of non-empty strings."))
            elif not open_gaps:
                errors.append(_error(f"{field_prefix}.open_gaps", "open_gaps must be a non-empty list."))
            normalized.append(item)
        return normalized

    active_hypothesis_gaps = _validate_active_gaps()

    def _validate_history_list(field_name: str, required_fields: set[str]) -> list[dict[str, Any]]:
        items = raw.get(field_name)
        if not isinstance(items, list) or not items:
            errors.append(
                _error(field_name, f"{field_name} must be a non-empty list."))
            return []
        normalized_items: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            field_prefix = f"{field_name}[{index}]"
            if not isinstance(item, dict):
                errors.append(
                    _error(field_prefix, "Each item must be an object."))
                continue
            unsupported_fields = sorted(set(item.keys()) - required_fields)
            if unsupported_fields:
                errors.append(
                    _error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
            round_value = item.get("round_id")
            if not _is_non_empty_string(round_value):
                errors.append(
                    _error(f"{field_prefix}.round_id", "round_id must be a non-empty string."))
            elif str(round_value).strip() != expected_round_id:
                errors.append(_error(
                    f"{field_prefix}.round_id", f"round_id must match '{expected_round_id}'."))
            normalized_items.append(item)
        return normalized_items

    investigation_history = _validate_history_list(
        "investigation_history", _INVESTIGATION_HISTORY_FIELDS)
    ranking_history = _validate_history_list(
        "ranking_history", _RANKING_HISTORY_FIELDS)

    investigation_outcomes = raw.get("investigation_outcomes")
    if not isinstance(investigation_outcomes, list) or not investigation_outcomes:
        errors.append(_error("investigation_outcomes",
                      "investigation_outcomes must be a non-empty list."))
        investigation_outcomes = []
    else:
        for index, item in enumerate(investigation_outcomes):
            field_prefix = f"investigation_outcomes[{index}]"
            if not isinstance(item, dict):
                errors.append(
                    _error(field_prefix, "Each item must be an object."))
                continue
            unsupported_fields = sorted(
                set(item.keys()) - _INVESTIGATION_OUTCOME_FIELDS)
            if unsupported_fields:
                errors.append(
                    _error(field_prefix, f"Unsupported fields: {unsupported_fields}."))
            if not _is_non_empty_string(item.get("round_id")):
                errors.append(
                    _error(f"{field_prefix}.round_id", "round_id must be a non-empty string."))
            elif str(item.get("round_id")).strip() != expected_round_id:
                errors.append(_error(
                    f"{field_prefix}.round_id", f"round_id must match '{expected_round_id}'."))
            if not _is_non_empty_string(item.get("hypothesis_id")):
                errors.append(_error(
                    f"{field_prefix}.hypothesis_id", "hypothesis_id must be a non-empty string."))
            if _int_value(item.get("revision_delta")) is None:
                errors.append(
                    _error(f"{field_prefix}.revision_delta", "revision_delta must be an integer."))
            for key in ("new_findings_count", "resolved_gaps_count"):
                value = _int_value(item.get(key))
                if value is None or value < 0:
                    errors.append(
                        _error(f"{field_prefix}.{key}", f"{key} must be a non-negative integer."))
            if not _is_non_empty_string(item.get("state_change_summary")):
                errors.append(_error(f"{field_prefix}.state_change_summary",
                              "state_change_summary must be a non-empty string."))

    # Cross-checks: hypothesis_ids in history/ranking/outcomes must exist in universe
    known_ids = {str(item.get("hypothesis_id", "") or "").strip()
                 for item in hypothesis_universe if _is_non_empty_string(item.get("hypothesis_id"))}
    for field_name in ("investigation_history", "ranking_history"):
        for index, item in enumerate(raw.get(field_name, []) if isinstance(raw.get(field_name), list) else []):
            if not isinstance(item, dict):
                continue
            for key in ("selected_hypothesis_ids", "candidate_hypothesis_ids"):
                ids = _string_list(item.get(key))
                if ids is None:
                    continue
                for hypothesis_id in ids:
                    if known_ids and hypothesis_id not in known_ids:
                        errors.append(_error(
                            f"{field_name}[{index}].{key}", f"Unknown hypothesis_id '{hypothesis_id}'."))

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "semantic_landscape_region_count": region_count,
            "hypothesis_universe_count": len(hypothesis_universe),
            "investigation_history_count": len(investigation_history),
            "ranking_history_count": len(ranking_history),
            "investigation_outcome_count": len(investigation_outcomes),
            "active_hypothesis_gap_count": len(active_hypothesis_gaps),
        },
    )


def validate_critic_observations_payload(
    critic_observations_payload: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
    known_hypothesis_ids: set[str],
    allowed_target_modules: set[str] | None = None,
) -> dict[str, Any]:
    raw = critic_observations_payload if isinstance(
        critic_observations_payload, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    forbidden_language_hits: list[dict[str, str]] = []
    allowed_modules = set(allowed_target_modules or VALID_TARGET_MODULES)

    if not isinstance(critic_observations_payload, dict):
        errors.append(_error("critic_observations_payload",
                      "critic_observations_payload must be an object."))

    unsupported_fields = sorted(
        set(raw.keys()) - _CRITIC_OBSERVATIONS_PAYLOAD_FIELDS)
    if unsupported_fields:
        errors.append(
            _error(
                "critic_observations_payload",
                f"critic_observations_payload contains unsupported fields: {unsupported_fields}.",
            )
        )

    for key, expected_value in (("batch_id", expected_batch_id), ("round_id", expected_round_id)):
        value = raw.get(key)
        if not _is_non_empty_string(value):
            errors.append(_error(key, f"{key} must be a non-empty string."))
        elif str(value).strip() != expected_value:
            errors.append(_error(key, f"{key} must match '{expected_value}'."))

    critic_observations = raw.get("critic_observations")
    if not isinstance(critic_observations, list):
        errors.append(_error("critic_observations",
                      "critic_observations must be a list."))
        critic_observations = []
    elif len(critic_observations) > MAX_CRITIC_OBSERVATIONS:
        errors.append(
            _error(
                "critic_observations",
                f"critic_observations must contain no more than {MAX_CRITIC_OBSERVATIONS} items.",
            )
        )

    seen_ids: set[str] = set()
    for index, observation_item in enumerate(critic_observations):
        field_prefix = f"critic_observations[{index}]"
        if not isinstance(observation_item, dict):
            errors.append(
                _error(field_prefix, "Each critic_observation item must be an object."))
            continue
        unsupported_fields = sorted(
            set(observation_item.keys()) - _CRITIC_OBSERVATION_FIELDS)
        if unsupported_fields:
            errors.append(
                _error(field_prefix, f"Unsupported fields: {unsupported_fields}."))

        observation_id = observation_item.get("observation_id")
        if not _is_non_empty_string(observation_id):
            errors.append(_error(
                f"{field_prefix}.observation_id", "observation_id must be a non-empty string."))
        else:
            normalized_id = str(observation_id).strip()
            if normalized_id in seen_ids:
                errors.append(
                    _error(f"{field_prefix}.observation_id", "observation_id must be unique."))
            seen_ids.add(normalized_id)

        observation_type = observation_item.get("observation_type")
        if not _is_non_empty_string(observation_type):
            errors.append(_error(f"{field_prefix}.observation_type",
                          "observation_type must be a non-empty string."))
        elif str(observation_type).strip() not in VALID_OBSERVATION_TYPES:
            errors.append(_error(f"{field_prefix}.observation_type",
                          f"observation_type must be one of {sorted(VALID_OBSERVATION_TYPES)}."))

        target_module = observation_item.get("target_module")
        if not _is_non_empty_string(target_module):
            errors.append(_error(
                f"{field_prefix}.target_module", "target_module must be a non-empty string."))
        elif str(target_module).strip() not in VALID_TARGET_MODULES:
            errors.append(_error(f"{field_prefix}.target_module",
                          f"target_module must be one of {sorted(VALID_TARGET_MODULES)}."))
        elif str(target_module).strip() not in allowed_modules:
            errors.append(
                _error(
                    f"{field_prefix}.target_module",
                    f"target_module must be one of the allowed runtime targets: {sorted(allowed_modules)}.",
                )
            )

        priority = observation_item.get("priority")
        if not _is_non_empty_string(priority):
            errors.append(
                _error(f"{field_prefix}.priority", "priority must be a non-empty string."))
        elif str(priority).strip() not in VALID_PRIORITIES:
            errors.append(_error(
                f"{field_prefix}.priority", f"priority must be one of {sorted(VALID_PRIORITIES)}."))

        hypothesis_ids = _string_list(observation_item.get("hypothesis_ids"))
        if hypothesis_ids is None:
            errors.append(_error(
                f"{field_prefix}.hypothesis_ids", "hypothesis_ids must be a list of strings."))
            hypothesis_ids = []
        else:
            for hypothesis_id in hypothesis_ids:
                if hypothesis_id not in known_hypothesis_ids:
                    errors.append(_error(
                        f"{field_prefix}.hypothesis_ids", f"Unknown hypothesis_id '{hypothesis_id}'."))

        rationale = observation_item.get("rationale")
        if not _is_non_empty_string(rationale):
            errors.append(
                _error(f"{field_prefix}.rationale", "rationale must be a non-empty string."))
        elif len(str(rationale).strip()) > MAX_RATIONALE_CHARS:
            errors.append(
                _error(
                    f"{field_prefix}.rationale",
                    f"rationale must stay under {MAX_RATIONALE_CHARS} characters.",
                )
            )

        guidance = observation_item.get("guidance")
        if not _is_non_empty_string(guidance):
            errors.append(
                _error(f"{field_prefix}.guidance", "guidance must be a non-empty string."))

        prompt_snippet = observation_item.get("prompt_snippet")
        if not _is_non_empty_string(prompt_snippet):
            errors.append(_error(
                f"{field_prefix}.prompt_snippet", "prompt_snippet must be a non-empty string."))
        elif len(str(prompt_snippet).strip()) > MAX_PROMPT_SNIPPET_CHARS:
            errors.append(
                _error(
                    f"{field_prefix}.prompt_snippet",
                    f"prompt_snippet must stay under {MAX_PROMPT_SNIPPET_CHARS} characters.",
                )
            )
        forbidden_language_hits.extend(
            _collect_forbidden_language(
                f"{field_prefix}.prompt_snippet", prompt_snippet)
        )

    if forbidden_language_hits:
        warnings.extend(
            _error(hit["field"],
                   f"Semantic language flag detected ({hit['code']}).")
            for hit in forbidden_language_hits
        )

    snippet_lengths = [
        len(str(item.get("prompt_snippet", "") or "").strip())
        for item in critic_observations
        if isinstance(item, dict)
    ]
    average_snippet_length = round(
        sum(snippet_lengths) / len(snippet_lengths), 3) if snippet_lengths else 0.0

    return _report(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        stats={
            "observation_count": len(critic_observations),
            "observations_committed": not errors,
            "average_prompt_snippet_length": average_snippet_length,
        },
        forbidden_language_hits=forbidden_language_hits,
    )
