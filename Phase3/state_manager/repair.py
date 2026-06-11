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

    for field in _APPEND_ONLY_FIELDS:
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