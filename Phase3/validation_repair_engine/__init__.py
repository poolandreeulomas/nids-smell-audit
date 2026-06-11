"""Validation Repair Engine: deterministic post-validation structural repair layer.

This module provides a completely new component that runs OUTSIDE all existing
validators. It performs a very small set of structural type-mismatch repairs
that frequently occur in LLM outputs, without modifying any validator logic,
existing validation rules, schemas, contracts, or prompts.

Design principles:
    - Deterministic: identical inputs always produce identical outputs.
    - Schema-agnostic: no knowledge of phase-specific schemas.
    - Validator-driven: repairs are inferred from validator error messages.
    - Conservative: if a repair cannot be performed with complete certainty,
      the value is left unchanged and validation is allowed to fail.
    - Non-semantic: never invents or rewrites semantic content.
"""

from __future__ import annotations

from typing import Any

from validation_repair_engine.models import RepairAction, RepairPlan, RepairReport
from validation_repair_engine.repair_ops import (
    REPAIR_REGISTRY,
    dispatch_repairs,
    infer_repairs_from_errors,
)

__all__ = [
    "ValidationRepairEngine",
    "ValidationRepairEngineError",
    "RepairAction",
    "RepairPlan",
    "RepairReport",
]


class ValidationRepairEngineError(Exception):
    """Raised when the repair engine encounters an internal error."""


class ValidationRepairEngine:
    """A deterministic post-validation structural repair layer.

    This engine:
        1. Takes the parsed (but invalid) output + validator error messages.
        2. Infers safe, deterministic repairs from validator error messages.
        3. Applies only provably safe structural repairs.
        4. Returns a repair report + the repaired output (or original if no repair).
        5. Does NOT loop or retry — at most one repair pass.
    """

    def __init__(self) -> None:
        self._registry = REPAIR_REGISTRY

    def repair(
        self,
        parsed_output: dict[str, Any],
        errors: list[dict[str, str]],
    ) -> RepairReport:
        """Attempt to repair *parsed_output* guided by validator *errors*.

        Parameters
        ----------
        parsed_output:
            The full parsed output dict from an LLM component. This is the
            same dict that was fed to the validator.
        errors:
            List of validator error dicts, each containing at minimum:
                {"field": "<field-path>", "message": "<error-message>"}

        Returns
        -------
        RepairReport with:
            - repaired_output: the output after repairs (or original if none).
            - repairs_applied: list of RepairAction describing what was done.
            - success: True if the engine was able to apply repairs.
            - confidence: 'high' | 'low' — high means all repairs were
              deterministic and safe; low means some repairs may be
              speculative (should not automatically re-validate).
        """
        if not isinstance(parsed_output, dict):
            return RepairReport(
                repaired_output=parsed_output,
                repairs_applied=[],
                success=False,
                confidence="low",
                reason="Cannot repair non-dict top-level value.",
            )

        if not isinstance(errors, list):
            return RepairReport(
                repaired_output=parsed_output,
                repairs_applied=[],
                success=False,
                confidence="low",
                reason="Errors input must be a list.",
            )

        plans = infer_repairs_from_errors(errors)
        if not plans:
            return RepairReport(
                repaired_output=parsed_output,
                repairs_applied=[],
                success=False,
                confidence="high",
                reason="No repairable errors found.",
            )

        repaired_output, repairs_applied = dispatch_repairs(
            parsed_output, plans
        )

        if not repairs_applied:
            return RepairReport(
                repaired_output=repaired_output,
                repairs_applied=[],
                success=False,
                confidence="high",
                reason="No repairs could be applied deterministically.",
            )

        return RepairReport(
            repaired_output=repaired_output,
            repairs_applied=repairs_applied,
            success=True,
            confidence="high",
        )


# Convenience function for orchestration integration
def apply_validation_repair(
    parsed_output: dict[str, Any],
    errors: list[dict[str, str]],
) -> RepairReport:
    """One-shot repair: create engine, repair once, return report.

    This is the primary integration point for orchestration code.
    """
    engine = ValidationRepairEngine()
    return engine.repair(parsed_output, errors)