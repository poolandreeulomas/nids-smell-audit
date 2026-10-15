"""Auto-repair for append-only state persistence failures.

The LLM may accidentally omit previously existing items from append-only
fields (evidence_refs, merged_findings, open_gaps, preserved_contradictions).
These are not reasoning failures — they are output-size / copy errors.
This module restores missing items deterministically before validation runs.
"""

from __future__ import annotations

from typing import Any


_APPEND_ONLY_FIELDS = (
    "evidence_refs",
    "merged_findings",
    "open_gaps",
    "preserved_contradictions",
)

# evidence_refs is always repaired regardless of applied_updates, because
# evidence traceability is a non-negotiable integrity requirement.  The
# other three fields may be intentionally reduced when the state delta
# explicitly declares a corresponding applied_updates entry.
_ALWAYS_REPAIRED_FIELDS = frozenset({"evidence_refs"})


def _normalized_string_set(values: object) -> set[str]:
    """Return a deduplicated, stripped set of strings from a list-like value."""
    if not isinstance(values, list):
        return set()
    result: set[str] = set()
    for item in values:
        if isinstance(item, str) and item.strip():
            result.add(item.strip())
    return result


def _normalized_string_list(values: object) -> list[str]:
    """Return a deduplicated, ordered list of stripped strings."""
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            result.append(stripped)
    return result


def _collect_explicitly_updated_fields(
    state_delta_record: dict[str, Any],
) -> frozenset[str]:
    """Return the set of field names declared in applied_updates.

    A field listed in applied_updates signals that the state delta
    intentionally modifies that field (possibly removing prior items).
    Repair must not silently re-add items the LLM explicitly removed in that
    case, because doing so would override the intended update.
    """
    applied_updates = state_delta_record.get("applied_updates")
    if not isinstance(applied_updates, list):
        return frozenset()
    updated: set[str] = set()
    for update in applied_updates:
        if isinstance(update, dict):
            field_name = update.get("field")
            if isinstance(field_name, str) and field_name.strip():
                updated.add(field_name.strip())
    return frozenset(updated)


def enforce_append_only_invariants(
    state_delta_record: dict[str, Any],
    *,
    current_hypothesis: dict[str, Any],
    aggregation_handoff: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restore missing append-only items and return the repaired record + repair events.

    For each append-only field, the required set is:

        required = current_hypothesis[field] ∪ aggregation_handoff[field]

    If the LLM-produced record is missing any required items, they are
    appended while preserving the existing ordering.

    Exception: if the field is not in _ALWAYS_REPAIRED_FIELDS *and* the
    state delta's applied_updates explicitly lists that field as updated,
    repair is skipped.  This allows the validator to accept a legitimate
    reduction (e.g. resolving a contradiction) without the repair layer
    undoing the intended change.

    Returns
    -------
    repaired : dict
        A shallow copy of *state_delta_record* with missing items restored.
    repair_events : list[dict]
        One entry per repaired field, suitable for traceability.
    """
    repaired = dict(state_delta_record)
    repair_events: list[dict[str, Any]] = []

    current = current_hypothesis if isinstance(current_hypothesis, dict) else {}
    handoff = aggregation_handoff if isinstance(aggregation_handoff, dict) else {}

    # Determine which fields are explicitly declared as updated by the LLM.
    # For those non-mandatory fields, repair is skipped so that the validator
    # can evaluate the intended update on its own merits.
    explicitly_updated = _collect_explicitly_updated_fields(state_delta_record)

    for field in _APPEND_ONLY_FIELDS:
        # Always repair evidence_refs to preserve evidence traceability.
        # For other fields, skip repair when the delta explicitly declares an
        # update for that field — the validator will accept or reject it.
        if field not in _ALWAYS_REPAIRED_FIELDS and field in explicitly_updated:
            continue

        required = _normalized_string_set(current.get(field))
        required |= _normalized_string_set(handoff.get(field))

        produced_list = _normalized_string_list(repaired.get(field))
        produced_set = set(produced_list)

        missing = sorted(required - produced_set)
        if not missing:
            continue

        # Preserve existing ordering, then append missing items.
        restored = list(produced_list) + missing
        # Remove any accidental duplicates while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for item in restored:
            if item not in seen:
                seen.add(item)
                deduped.append(item)

        repaired[field] = deduped
        repair_events.append({
            "field": field,
            "repair_type": "auto_append_missing",
            "added_items": missing,
        })

    return repaired, repair_events