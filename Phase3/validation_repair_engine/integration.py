"""Orchestration integration adapter for the Validation Repair Engine.

This module provides the glue code between the existing runner/validator flow
and the repair layer. It implements the exact orchestration contract:

    1. Generate output
    2. Run validator
    3. If validation passes → continue
    4. If validation fails → run Validation Repair Engine
    5. Re-run validator exactly once
    6. If validation passes → continue
    7. Otherwise fail normally

Usage in a runner (pseudocode)::

    from validation_repair_engine.integration import (
        validate_or_repair,
    )

    # --- Step 2: validate ---
    output_validation = validate_hypothesis_set(parsed_output, ...)

    # --- Steps 3-6: repair + re-validate if needed ---
    output_validation, repair_report = validate_or_repair(
        parsed_output=parsed_output,
        output_validation=output_validation,
        validator_fn=validate_hypothesis_set,
        validator_kwargs={...},
    )

    # --- Use output_validation["ok"] as before ---
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from validation_repair_engine import ValidationRepairEngine, RepairReport


def validate_or_repair(
    parsed_output: dict[str, Any],
    output_validation: dict[str, Any],
    validator_fn: Callable[..., dict[str, Any]],
    validator_kwargs: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], RepairReport]:
    """Validate; if failed, repair once and re-validate once.

    Parameters
    ----------
    parsed_output:
        The parsed output dict (may be mutated if repaired).
    output_validation:
        The original validation report from ``validator_fn(parsed_output, **validator_kwargs)``.
    validator_fn:
        The validator callable (e.g. ``validate_hypothesis_set``).
    validator_kwargs:
        Additional keyword arguments to pass to the validator.

    Returns
    -------
    (final_validation_report, repair_report)
    """
    kwargs = dict(validator_kwargs or {})

    # Step 3: validation already passed?  Nothing to do.
    if bool(output_validation.get("ok", False)):
        empty_report = RepairReport(
            repaired_output=parsed_output,
            repairs_applied=[],
            success=False,
            confidence="high",
            reason="Validation passed; no repair needed.",
        )
        return output_validation, empty_report

    # Step 4: validation failed — try repair
    errors = list(output_validation.get("errors", []) or [])
    engine = ValidationRepairEngine()
    repair_report = engine.repair(parsed_output, errors)

    if not repair_report.success:
        # Nothing was repaired — return original failed validation
        return output_validation, repair_report

    # Step 5: re-validate exactly once with repaired output
    repaired_output = repair_report.repaired_output
    re_validated = validator_fn(repaired_output, **kwargs)

    if bool(re_validated.get("ok", False)):
        # Step 6: validation passed after repair
        re_validated["repaired"] = True
        re_validated["repair_report"] = repair_report.to_dict() if hasattr(repair_report, "to_dict") else {
            "repairs_applied": [{
                "field": a.field,
                "repair_type": a.repair_type,
                "reason": a.reason,
            } for a in repair_report.repairs_applied],
            "success": repair_report.success,
        }
        return re_validated, repair_report

    # Step 7: still fails — return the re-validation failure
    return re_validated, repair_report