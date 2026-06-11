"""Data models for the Validation Repair Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RepairAction:
    """A single deterministic repair operation that was applied.

    Attributes
    ----------
    field:
        The dotted field path that was repaired (e.g. "hypotheses[0].summary").
    repair_type:
        Machine-readable repair code (e.g. "list_to_string", "string_to_list",
        "trim_string", "remove_empty_strings", "deduplicate_strings").
    before:
        The value before repair.
    after:
        The value after repair.
    reason:
        Human-readable explanation.
    """

    field: str
    repair_type: str
    before: Any
    after: Any
    reason: str


@dataclass(frozen=True)
class RepairPlan:
    """A plan to repair a single field.

    Attributes
    ----------
    field:
        The dotted field path to repair.
    repair_type:
        The type of repair to apply.
    parts:
        The parsed field path parts for navigation.
    """

    field: str
    repair_type: str
    parts: list[str | int] = field(default_factory=list)


@dataclass(frozen=True)
class RepairReport:
    """The result of a repair attempt.

    Attributes
    ----------
    repaired_output:
        The output after repairs (or the original if no repair was possible).
    repairs_applied:
        List of RepairAction describing what was done.
    success:
        True if at least one repair was applied.
    confidence:
        'high' if all repairs were deterministic and safe.
        'low' if some repairs were speculative.
    reason:
        Summary explanation of the repair outcome.
    """

    repaired_output: Any
    repairs_applied: list[RepairAction] = field(default_factory=list)
    success: bool = False
    confidence: str = "low"
    reason: str = ""