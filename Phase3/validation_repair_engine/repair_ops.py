"""Repair operations for the Validation Repair Engine.

This module implements all allowed deterministic structural repairs:

    #1  list[str] → string  (when list has exactly 1 non-empty string)
    #2  string → list[str]   (wrap single string in a list)
    #3  trim strings         (strip whitespace from string values)
    #4  remove empty strings from lists
    #5  deduplicate strings in lists (optional)
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Callable

from validation_repair_engine.models import RepairAction, RepairPlan

# ---------------------------------------------------------------------------
# Field-path navigation
# ---------------------------------------------------------------------------

_PARSE_BRACKET = re.compile(r"\[(\d+)\]")


def _parse_field_path(path: str) -> list[str | int]:
    """Parse a dotted field path into a list of keys and indices.

    Examples
    --------
    "hypotheses[0].summary"          → ["hypotheses", 0, "summary"]
    "batch_id"                       → ["batch_id"]
    "interpretive_hypotheses[2].status" → ["interpretive_hypotheses", 2, "status"]
    """
    parts: list[str | int] = []
    for segment in path.split("."):
        match = _PARSE_BRACKET.search(segment)
        if match and not segment.startswith("["):
            # e.g. "hypotheses[0]"
            name = segment[: match.start()]
            parts.append(name)
            parts.append(int(match.group(1)))
        else:
            # Plain segment or bracket-only (shouldn't happen but be safe)
            parts.append(segment)
    return parts


def _get_value(root: dict[str, Any], parts: list[str | int]) -> Any:
    """Navigate *parts* into *root* and return the value."""
    current: Any = root
    for part in parts:
        if isinstance(current, dict) and isinstance(part, str):
            current = current.get(part)
        elif isinstance(current, list) and isinstance(part, int):
            try:
                current = current[part]
            except IndexError:
                return _MISSING
        else:
            return _MISSING
    return current


def _set_value(root: dict[str, Any], parts: list[str | int], value: Any) -> None:
    """Navigate *parts* into *root* and set *value* (mutating *root*)."""
    current: Any = root
    for i, part in enumerate(parts[:-1]):
        next_part = parts[i + 1]
        if isinstance(current, dict) and isinstance(part, str):
            if isinstance(next_part, int):
                # Ensure the list exists
                if part not in current or not isinstance(current[part], list):
                    current[part] = []
                current = current[part]
            else:
                current = current.setdefault(part, {})
        elif isinstance(current, list) and isinstance(part, int):
            try:
                current = current[part]
            except IndexError:
                return  # Cannot navigate — value is unchanged
        else:
            return  # Cannot navigate — value is unchanged

    last = parts[-1]
    if isinstance(current, dict) and isinstance(last, str):
        current[last] = value
    elif isinstance(current, list) and isinstance(last, int):
        if 0 <= last < len(current):
            current[last] = value


_MISSING = object()

# ---------------------------------------------------------------------------
# Repair type #1: list[str] → string
# ---------------------------------------------------------------------------


def _repair_list_to_string(
    value: object,
) -> tuple[object, RepairAction | None]:
    """Convert ``["some text"]`` → ``"some text"``.

    Only when:
        - value is a list
        - list has exactly 1 element
        - that element is a non-empty string
    """
    if not isinstance(value, list):
        return value, None
    if len(value) != 1:
        return value, None
    single = value[0]
    if not isinstance(single, str) or not single.strip():
        return value, None
    return single, None


# ---------------------------------------------------------------------------
# Repair type #2: string → list[str]
# ---------------------------------------------------------------------------


def _repair_string_to_list(
    value: object,
) -> tuple[object, RepairAction | None]:
    """Convert ``"some text"`` → ``["some text"]``.

    Only when:
        - value is a non-empty string
    """
    if not isinstance(value, str) or not value.strip():
        return value, None
    return [value], None


# ---------------------------------------------------------------------------
# Repair type #3: trim strings
# ---------------------------------------------------------------------------


def _repair_trim_string(
    value: object,
) -> tuple[object, RepairAction | None]:
    """Trim whitespace from a string value.

    Only when:
        - value is a string
        - the trimmed version differs from the original
    """
    if not isinstance(value, str):
        return value, None
    trimmed = value.strip()
    if trimmed == value:
        return value, None
    return trimmed, None


# ---------------------------------------------------------------------------
# Repair type #4: remove empty-string elements from lists
# ---------------------------------------------------------------------------


def _repair_remove_empty_strings(
    value: object,
) -> tuple[object, RepairAction | None]:
    """Remove empty-string elements from a list.

    Only when:
        - value is a list
        - at least one element is an empty string
    """
    if not isinstance(value, list):
        return value, None
    original_len = len(value)
    cleaned = [item for item in value if not (isinstance(item, str) and not item.strip())]
    if len(cleaned) == original_len:
        return value, None
    return cleaned, None


# ---------------------------------------------------------------------------
# Repair type #5: deduplicate strings in lists (optional)
# ---------------------------------------------------------------------------


def _repair_deduplicate_strings(
    value: object,
) -> tuple[object, RepairAction | None]:
    """Deduplicate identical string entries in a list.

    Only when:
        - value is a list
        - at least one string appears more than once
        - order is preserved (first occurrence kept)
    """
    if not isinstance(value, list):
        return value, None
    seen: set[str] = set()
    deduped: list[object] = []
    changed = False
    for item in value:
        if isinstance(item, str):
            if item in seen:
                changed = True
                continue
            seen.add(item)
        deduped.append(item)
    if not changed:
        return value, None
    return deduped, None


# ---------------------------------------------------------------------------
# Error-to-repair mapping  (validator-driven inference)
# ---------------------------------------------------------------------------

# Patterns that signal a field should be a non-empty string (type #2: wrap in list)
_STRING_TO_LIST_PATTERNS: list[re.Pattern] = [
    re.compile(r"must be a non-empty list of strings", re.IGNORECASE),
    re.compile(r"must be a list of strings", re.IGNORECASE),
    re.compile(r"must be a list$", re.IGNORECASE),
    re.compile(r"must be a non-empty list", re.IGNORECASE),
    re.compile(r"must be a list", re.IGNORECASE),
]

# Patterns that signal a field should be a non-empty string (type #1: unbox from list)
_LIST_TO_STRING_PATTERNS: list[re.Pattern] = [
    re.compile(r"must be a non-empty string", re.IGNORECASE),
    re.compile(r"must be a string", re.IGNORECASE),
    re.compile(r"must be an object", re.IGNORECASE),
]

# Patterns that signal a field is a string but has leading/trailing whitespace (type #3)
_TRIM_STRING_PATTERNS: list[re.Pattern] = [
    re.compile(r"must be a non-empty string", re.IGNORECASE),
    re.compile(r"must be a string", re.IGNORECASE),
]

# Patterns for empty-string removal (type #4)
_REMOVE_EMPTY_PATTERNS: list[re.Pattern] = [
    re.compile(r"must contain only non-empty strings", re.IGNORECASE),
    re.compile(r"must be a non-empty list of strings", re.IGNORECASE),
    re.compile(r"must be a list of strings", re.IGNORECASE),
]

# Patterns for deduplication (type #5)
_DEDUP_PATTERNS: list[re.Pattern] = [
    re.compile(r"duplicate", re.IGNORECASE),
]


def _matches_any(message: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(message) for p in patterns)


def infer_repairs_from_errors(
    errors: list[dict[str, str]],
) -> list[RepairPlan]:
    """Map validator errors to repair plans.

    For each error, infer which repair type(s) to attempt based on the
    validator error message. Multiple plans may target the same field with
    different repair types (they'll be applied in order).
    """
    plans: list[RepairPlan] = []
    seen: set[tuple[str, str]] = set()  # (field, repair_type) dedup

    for error in errors:
        field = error.get("field", "")
        message = error.get("message", "")

        if not field or not message:
            continue

        # Parse field path once
        parts = _parse_field_path(field)

        # Determine candidate repair types
        candidates: list[str] = []

        # If the error says "must be a non-empty string" etc., try unboxing
        # from a list (repair #1) AND trimming (repair #3)
        if _matches_any(message, _LIST_TO_STRING_PATTERNS):
            candidates.append("list_to_string")
            candidates.append("trim_string")

        # If the error says "must be a list of strings", try wrapping a
        # single string in a list (repair #2)
        if _matches_any(message, _STRING_TO_LIST_PATTERNS):
            candidates.append("string_to_list")

        # If the error says "must contain only non-empty strings", try
        # removing empty strings (repair #4)
        if _matches_any(message, _REMOVE_EMPTY_PATTERNS):
            candidates.append("remove_empty_strings")

        if _matches_any(message, _DEDUP_PATTERNS):
            candidates.append("deduplicate_strings")

        for repair_type in candidates:
            key = (field, repair_type)
            if key not in seen:
                seen.add(key)
                plans.append(
                    RepairPlan(
                        field=field,
                        repair_type=repair_type,
                        parts=parts,
                    )
                )

    return plans


# ---------------------------------------------------------------------------
# Registry: repair_type → callable
# ---------------------------------------------------------------------------

REPAIR_REGISTRY: dict[str, Callable[[object], tuple[object, RepairAction | None]]] = {
    "list_to_string": _repair_list_to_string,
    "string_to_list": _repair_string_to_list,
    "trim_string": _repair_trim_string,
    "remove_empty_strings": _repair_remove_empty_strings,
    "deduplicate_strings": _repair_deduplicate_strings,
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_repairs(
    parsed_output: dict[str, Any],
    plans: list[RepairPlan],
) -> tuple[dict[str, Any], list[RepairAction]]:
    """Apply repair plans to parsed output.

    Returns (repaired_output, repairs_applied).
    The output is deep-copied before mutation.
    """
    repaired = deepcopy(parsed_output)
    repairs_applied: list[RepairAction] = []

    for plan in plans:
        repair_fn = REPAIR_REGISTRY.get(plan.repair_type)
        if repair_fn is None:
            continue

        value = _get_value(repaired, plan.parts)
        if value is _MISSING:
            continue

        new_value, _ = repair_fn(value)
        if new_value is not value and new_value != value:
            _set_value(repaired, plan.parts, new_value)
            repairs_applied.append(
                RepairAction(
                    field=plan.field,
                    repair_type=plan.repair_type,
                    before=value,
                    after=new_value,
                    reason=_repair_reason(plan.repair_type),
                )
            )

    return repaired, repairs_applied


def _repair_reason(repair_type: str) -> str:
    reasons = {
        "list_to_string": "List with exactly 1 non-empty string was unboxed to a string.",
        "string_to_list": "Single string was wrapped in a list.",
        "trim_string": "String was trimmed of leading/trailing whitespace.",
        "remove_empty_strings": "Empty-string elements were removed from list.",
        "deduplicate_strings": "Duplicate string entries were removed from list (first occurrence kept).",
    }
    return reasons.get(repair_type, f"Repair '{repair_type}' applied.")