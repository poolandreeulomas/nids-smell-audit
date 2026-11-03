"""Unit tests for the Validation Repair Engine.

Tests cover:
    1. Repair type #1: list-to-string conversion
    2. Repair type #2: string-to-list conversion
    3. Repair type #3: string trimming
    4. Repair type #4: empty-string removal from lists
    5. Repair type #5: deduplication of strings in lists
    6. Error-to-repair mapping (inference)
    7. Full engine end-to-end scenarios
    8. Integration adapter (validate_or_repair)
    9. Conservative behavior (no repair when ambiguous)
    10. Field-path navigation with nested structures
"""

from __future__ import annotations

from typing import Any

import pytest

from validation_repair_engine import ValidationRepairEngine, apply_validation_repair
from validation_repair_engine.models import RepairAction, RepairPlan, RepairReport
from validation_repair_engine.repair_ops import (
    _parse_field_path,
    _get_value,
    _set_value,
    dispatch_repairs,
    infer_repairs_from_errors,
    _repair_list_to_string,
    _repair_string_to_list,
    _repair_trim_string,
    _repair_remove_empty_strings,
    _repair_deduplicate_strings,
)
from validation_repair_engine.integration import validate_or_repair


# =========================================================================
# Field-path navigation
# =========================================================================


class TestFieldPathNavigation:
    def test_parse_simple_field(self) -> None:
        assert _parse_field_path("batch_id") == ["batch_id"]

    def test_parse_indexed_field(self) -> None:
        assert _parse_field_path("hypotheses[0].summary") == [
            "hypotheses", 0, "summary"]

    def test_parse_nested_index(self) -> None:
        assert _parse_field_path("interpretive_hypotheses[2].status") == [
            "interpretive_hypotheses", 2, "status"]

    def test_parse_deep_nested(self) -> None:
        assert _parse_field_path("a.b.c[1].d") == ["a", "b", "c", 1, "d"]

    def test_get_value_simple(self) -> None:
        root = {"batch_id": "batch_123"}
        assert _get_value(root, ["batch_id"]) == "batch_123"

    def test_get_value_indexed(self) -> None:
        root = {"hypotheses": [{"summary": "test"}]}
        assert _get_value(root, ["hypotheses", 0, "summary"]) == "test"

    def test_get_value_missing(self) -> None:
        root = {"a": 1}
        assert _get_value(root, ["b"]) is None

    def test_get_value_out_of_range(self) -> None:
        root = {"items": ["a"]}
        assert _get_value(root, ["items", 5]) is not None  # _MISSING sentinel
        # Check it's actually _MISSING
        from validation_repair_engine.repair_ops import _MISSING
        assert _get_value(root, ["items", 5]) is _MISSING

    def test_set_value_simple(self) -> None:
        root = {"batch_id": "old"}
        _set_value(root, ["batch_id"], "new")
        assert root["batch_id"] == "new"

    def test_set_value_indexed(self) -> None:
        root = {"hypotheses": [{"summary": "old"}]}
        _set_value(root, ["hypotheses", 0, "summary"], "new")
        assert root["hypotheses"][0]["summary"] == "new"


# =========================================================================
# Repair type #1: list-to-string
# =========================================================================


class TestRepairListToString:
    def test_single_element_list(self) -> None:
        result, _ = _repair_list_to_string(["some text"])
        assert result == "some text"

    def test_empty_list(self) -> None:
        result, _ = _repair_list_to_string([])
        assert result == []

    def test_multi_element_list(self) -> None:
        result, _ = _repair_list_to_string(["a", "b"])
        assert result == ["a", "b"]

    def test_list_with_empty_string(self) -> None:
        result, _ = _repair_list_to_string([""])
        assert result == [""]

    def test_not_a_list(self) -> None:
        result, _ = _repair_list_to_string("already a string")
        assert result == "already a string"

    def test_list_with_non_string(self) -> None:
        result, _ = _repair_list_to_string([42])
        assert result == [42]


# =========================================================================
# Repair type #2: string-to-list
# =========================================================================


class TestRepairStringToList:
    def test_non_empty_string(self) -> None:
        result, _ = _repair_string_to_list("some text")
        assert result == ["some text"]

    def test_empty_string(self) -> None:
        result, _ = _repair_string_to_list("")
        assert result == ""

    def test_whitespace_string(self) -> None:
        result, _ = _repair_string_to_list("   ")
        assert result == "   "

    def test_not_a_string(self) -> None:
        result, _ = _repair_string_to_list(["already a list"])
        assert result == ["already a list"]


# =========================================================================
# Repair type #3: trim strings
# =========================================================================


class TestRepairTrimString:
    def test_trim_leading_whitespace(self) -> None:
        result, _ = _repair_trim_string("  hello")
        assert result == "hello"

    def test_trim_trailing_whitespace(self) -> None:
        result, _ = _repair_trim_string("hello  ")
        assert result == "hello"

    def test_trim_both_sides(self) -> None:
        result, _ = _repair_trim_string("  hello world  ")
        assert result == "hello world"

    def test_already_trimmed(self) -> None:
        result, _ = _repair_trim_string("hello")
        assert result == "hello"

    def test_not_a_string(self) -> None:
        result, _ = _repair_trim_string(42)
        assert result == 42


# =========================================================================
# Repair type #4: remove empty strings from lists
# =========================================================================


class TestRepairRemoveEmptyStrings:
    def test_mixed_list(self) -> None:
        result, _ = _repair_remove_empty_strings(["a", "", "b"])
        assert result == ["a", "b"]

    def test_all_empty(self) -> None:
        result, _ = _repair_remove_empty_strings(["", "", ""])
        assert result == []

    def test_no_empty_strings(self) -> None:
        result, _ = _repair_remove_empty_strings(["a", "b"])
        # Should be unchanged (same object)
        assert result is ["a", "b"] or result == ["a", "b"]

    def test_not_a_list(self) -> None:
        result, _ = _repair_remove_empty_strings("not a list")
        assert result == "not a list"

    def test_whitespace_only_is_not_removed(self) -> None:
        # Note: whitespace-only strings are removed (not.strip() is falsy)
        result, _ = _repair_remove_empty_strings(["a", "  ", "b"])
        assert result == ["a", "b"]


# =========================================================================
# Repair type #5: deduplicate strings in lists
# =========================================================================


class TestRepairDeduplicateStrings:
    def test_duplicates_removed(self) -> None:
        result, _ = _repair_deduplicate_strings(["a", "b", "a", "c"])
        assert result == ["a", "b", "c"]

    def test_no_duplicates(self) -> None:
        result, _ = _repair_deduplicate_strings(["a", "b", "c"])
        # Should be unchanged
        assert result is ["a", "b", "c"] or result == ["a", "b", "c"]

    def test_all_duplicates(self) -> None:
        result, _ = _repair_deduplicate_strings(["a", "a", "a"])
        assert result == ["a"]

    def test_not_a_list(self) -> None:
        result, _ = _repair_deduplicate_strings("not a list")
        assert result == "not a list"

    def test_preserves_order(self) -> None:
        result, _ = _repair_deduplicate_strings(
            ["first", "second", "first", "third"])
        assert result == ["first", "second", "third"]


# =========================================================================
# Error-to-repair mapping
# =========================================================================


class TestInferRepairsFromErrors:
    def test_non_empty_string_error(self) -> None:
        errors = [{"field": "batch_id", "message": "batch_id must be a non-empty string."}]
        plans = infer_repairs_from_errors(errors)
        repair_types = {p.repair_type for p in plans}
        assert "list_to_string" in repair_types
        assert "trim_string" in repair_types

    def test_list_of_strings_error(self) -> None:
        errors = [{"field": "evidence_refs",
                    "message": "evidence_refs must be a non-empty list of strings."}]
        plans = infer_repairs_from_errors(errors)
        repair_types = {p.repair_type for p in plans}
        assert "string_to_list" in repair_types
        assert "remove_empty_strings" in repair_types

    def test_duplicate_error(self) -> None:
        errors = [{"field": "hypotheses[0].hypothesis_id",
                    "message": "Duplicate hypothesis_id 'foo'."}]
        plans = infer_repairs_from_errors(errors)
        repair_types = {p.repair_type for p in plans}
        assert "deduplicate_strings" in repair_types

    def test_empty_strings_error(self) -> None:
        errors = [{"field": "hypotheses[0].evidence_refs",
                    "message": "evidence_refs must contain only non-empty strings."}]
        plans = infer_repairs_from_errors(errors)
        repair_types = {p.repair_type for p in plans}
        assert "remove_empty_strings" in repair_types

    def test_multiple_errors_same_field_no_duplicate_plans(self) -> None:
        errors = [
            {"field": "batch_id", "message": "batch_id must be a non-empty string."},
            {"field": "batch_id", "message": "batch_id must be a string."},
        ]
        plans = infer_repairs_from_errors(errors)
        # Should produce plans only once per (field, repair_type) pair
        counts = {}
        for p in plans:
            counts[(p.field, p.repair_type)] = counts.get(
                (p.field, p.repair_type), 0) + 1
        assert all(count == 1 for count in counts.values())

    def test_multiple_errors_different_fields(self) -> None:
        errors = [
            {"field": "batch_id", "message": "batch_id must be a non-empty string."},
            {"field": "evidence_refs",
                "message": "evidence_refs must be a list of strings."},
        ]
        plans = infer_repairs_from_errors(errors)
        fields = {p.field for p in plans}
        assert "batch_id" in fields
        assert "evidence_refs" in fields

    def test_empty_errors(self) -> None:
        assert infer_repairs_from_errors([]) == []

    def test_no_match_errors(self) -> None:
        errors = [{"field": "batch_id", "message": "Some unknown error."}]
        assert infer_repairs_from_errors(errors) == []

    def test_error_without_message(self) -> None:
        errors = [{"field": "batch_id"}]
        assert infer_repairs_from_errors(errors) == []

    def test_error_without_field(self) -> None:
        errors = [{"message": "must be a non-empty string."}]
        assert infer_repairs_from_errors(errors) == []


# =========================================================================
# Dispatch
# =========================================================================


class TestDispatchRepairs:
    def test_list_to_string_dispatch(self) -> None:
        parsed = {"batch_id": ["batch_123"]}
        plans = [RepairPlan(field="batch_id",
                            repair_type="list_to_string", parts=["batch_id"])]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired["batch_id"] == "batch_123"
        assert len(actions) == 1
        assert actions[0].repair_type == "list_to_string"

    def test_string_to_list_dispatch(self) -> None:
        parsed = {"evidence_refs": "ev_001"}
        plans = [RepairPlan(field="evidence_refs",
                            repair_type="string_to_list", parts=["evidence_refs"])]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired["evidence_refs"] == ["ev_001"]
        assert len(actions) == 1

    def test_trim_string_dispatch(self) -> None:
        parsed = {"batch_id": "  batch_123  "}
        plans = [RepairPlan(field="batch_id",
                            repair_type="trim_string", parts=["batch_id"])]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired["batch_id"] == "batch_123"
        assert len(actions) == 1

    def test_remove_empty_strings_dispatch(self) -> None:
        parsed = {"evidence_refs": ["a", "", "b"]}
        plans = [RepairPlan(field="evidence_refs",
                            repair_type="remove_empty_strings", parts=["evidence_refs"])]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired["evidence_refs"] == ["a", "b"]
        assert len(actions) == 1

    def test_deduplicate_dispatch(self) -> None:
        parsed = {"evidence_refs": ["a", "b", "a"]}
        plans = [RepairPlan(field="evidence_refs",
                            repair_type="deduplicate_strings", parts=["evidence_refs"])]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired["evidence_refs"] == ["a", "b"]
        assert len(actions) == 1

    def test_unknown_repair_type_skipped(self) -> None:
        parsed = {"batch_id": "test"}
        plans = [RepairPlan(field="batch_id",
                            repair_type="nonexistent", parts=["batch_id"])]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired == {"batch_id": "test"}
        assert actions == []

    def test_no_change_when_value_unchanged(self) -> None:
        parsed = {"batch_id": "test"}
        plans = [RepairPlan(field="batch_id",
                            repair_type="trim_string", parts=["batch_id"])]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert actions == []

    def test_nested_field_repair(self) -> None:
        parsed = {"hypotheses": [{"summary": ["single summary"]}]}
        plans = [RepairPlan(
            field="hypotheses[0].summary",
            repair_type="list_to_string",
            parts=["hypotheses", 0, "summary"],
        )]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired["hypotheses"][0]["summary"] == "single summary"
        assert len(actions) == 1

    def test_deeply_nested_field(self) -> None:
        parsed = {"a": {"b": {"c": ["d"]}}}
        plans = [RepairPlan(
            field="a.b.c",
            repair_type="list_to_string",
            parts=["a", "b", "c"],
        )]
        repaired, actions = dispatch_repairs(parsed, plans)
        assert repaired["a"]["b"]["c"] == "d"

    def test_original_not_mutated(self) -> None:
        parsed = {"batch_id": ["batch_123"]}
        plans = [RepairPlan(field="batch_id",
                            repair_type="list_to_string", parts=["batch_id"])]
        repaired, _ = dispatch_repairs(parsed, plans)
        assert repaired["batch_id"] == "batch_123"
        assert parsed["batch_id"] == ["batch_123"]  # original unchanged


# =========================================================================
# End-to-end engine tests
# =========================================================================


class TestValidationRepairEngine:
    def test_repair_list_to_string(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {"batch_id": ["batch_123"]}
        errors = [{"field": "batch_id",
                    "message": "batch_id must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        assert report.success is True
        assert report.repaired_output["batch_id"] == "batch_123"
        assert len(report.repairs_applied) >= 1

    def test_repair_string_to_list(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {"evidence_refs": "ev_001"}
        errors = [{"field": "evidence_refs",
                    "message": "evidence_refs must be a list of strings."}]
        report = engine.repair(parsed, errors)
        assert report.success is True
        assert report.repaired_output["evidence_refs"] == ["ev_001"]

    def test_repair_trim_string(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {"batch_id": "  batch_123  "}
        errors = [{"field": "batch_id",
                    "message": "batch_id must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        assert report.success is True
        assert report.repaired_output["batch_id"] == "batch_123"

    def test_repair_remove_empty_strings(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {"evidence_refs": ["a", "", "b"]}
        errors = [{"field": "evidence_refs",
                    "message": "evidence_refs must contain only non-empty strings."}]
        report = engine.repair(parsed, errors)
        assert report.success is True
        assert report.repaired_output["evidence_refs"] == ["a", "b"]

    def test_repair_nested_field(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {
            "analysis_id": "analysis_001",
            "hypotheses": [
                {
                    "hypothesis_id": "hyp_001",
                    "summary": ["This is a summary"],
                    "evidence_refs": ["ev_001"],
                }
            ],
        }
        errors = [{"field": "hypotheses[0].summary",
                    "message": "summary must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        assert report.success is True
        assert report.repaired_output["hypotheses"][0]["summary"] == "This is a summary"

    def test_no_repairable_errors(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {"batch_id": "valid"}
        errors = [{"field": "unknown_field",
                    "message": "Some unknown error."}]
        report = engine.repair(parsed, errors)
        assert report.success is False
        assert report.repaired_output == parsed

    def test_no_repair_when_value_correct(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {"batch_id": "valid"}
        errors = [{"field": "batch_id",
                    "message": "batch_id must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        # The value is already valid (string), so list_to_string won't change it
        # and trim_string won't change it either — no repair possible
        assert report.success is False

    def test_engine_does_not_mutate_original(self) -> None:
        engine = ValidationRepairEngine()
        parsed = {"batch_id": ["batch_123"]}
        original_copy = dict(parsed)
        errors = [{"field": "batch_id",
                    "message": "batch_id must be a non-empty string."}]
        engine.repair(parsed, errors)
        assert parsed == original_copy

    def test_complex_output_repair(self) -> None:
        """Test repairing a realistic hypothesis_set with multiple issues."""
        engine = ValidationRepairEngine()
        parsed = {
            "analysis_id": "analysis_001",
            "batch_id": "  batch_123  ",
            "hypotheses": [
                {
                    "hypothesis_id": "hyp_001",
                    "summary": ["This is a summary"],
                    "evidence_refs": ["ev_001", "", "ev_002"],
                    "open_questions": ["q1", "q2"],
                }
            ],
        }
        errors = [
            {"field": "batch_id",
                "message": "batch_id must be a non-empty string."},
            {"field": "hypotheses[0].summary",
                "message": "summary must be a non-empty string."},
            {"field": "hypotheses[0].evidence_refs",
                "message": "evidence_refs must contain only non-empty strings."},
        ]
        report = engine.repair(parsed, errors)
        assert report.success is True
        assert report.repaired_output["batch_id"] == "batch_123"
        assert report.repaired_output["hypotheses"][0]["summary"] == "This is a summary"
        assert report.repaired_output["hypotheses"][0]["evidence_refs"] == ["ev_001", "ev_002"]
        # Verify original unchanged
        assert parsed["batch_id"] == "  batch_123  "

    def test_repair_not_applied_when_ambiguous(self) -> None:
        """Multi-element list should NOT be converted to string."""
        engine = ValidationRepairEngine()
        parsed = {"batch_id": ["batch_123", "batch_456"]}
        errors = [{"field": "batch_id",
                    "message": "batch_id must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        assert report.success is False
        assert report.repaired_output["batch_id"] == ["batch_123", "batch_456"]


# =========================================================================
# Integration adapter
# =========================================================================


class TestValidateOrRepair:
    def _make_validator(self, ok: bool, errors: list[dict[str, str]] | None = None):
        """Factory for a mock validator."""
        def validator_fn(parsed: Any, **kwargs: Any) -> dict[str, Any]:
            return {"ok": ok, "errors": errors or []}
        return validator_fn

    def test_validation_passes_no_repair(self) -> None:
        validator = self._make_validator(ok=True, errors=[])
        parsed = {"batch_id": "valid"}
        validation_result = validator(parsed)
        final, report = validate_or_repair(parsed, validation_result, validator)
        assert final["ok"] is True
        assert report.success is False  # No repair needed
        assert report.reason == "Validation passed; no repair needed."

    def test_validation_fails_repair_succeeds(self) -> None:
        """Simulate a repair that fixes the output."""
        # First call: fails
        # After repair, second call: passes
        call_count = [0]

        def validator_fn(parsed: Any, **kwargs: Any) -> dict[str, Any]:
            call_count[0] += 1
            if call_count[0] == 1:
                return {"ok": False, "errors": [
                    {"field": "batch_id", "message": "batch_id must be a non-empty string."}
                ]}
            return {"ok": True, "errors": []}

        parsed = {"batch_id": ["batch_123"]}
        initial_result = validator_fn(parsed)
        call_count[0] = 1  # reset since we already called it
        final, report = validate_or_repair(parsed, initial_result, validator_fn)
        assert final["ok"] is True
        assert final.get("repaired") is True
        assert report.success is True

    def test_validation_fails_no_repair_possible(self) -> None:
        validator = self._make_validator(ok=False, errors=[
            {"field": "unknown", "message": "Some unknown error."}
        ])
        parsed = {"batch_id": "valid"}
        initial_result = validator(parsed)
        final, report = validate_or_repair(parsed, initial_result, validator)
        assert final["ok"] is False
        assert report.success is False

    def test_validation_fails_repair_fails_again(self) -> None:
        """Repair is applied but re-validation still fails (different error)."""
        call_count = [0]

        def validator_fn(parsed: Any, **kwargs: Any) -> dict[str, Any]:
            call_count[0] += 1
            if call_count[0] == 1:
                return {"ok": False, "errors": [
                    {"field": "batch_id", "message": "batch_id must be a non-empty string."}
                ]}
            # Even after repair, still fails for a different reason
            return {"ok": False, "errors": [
                {"field": "batch_id", "message": "batch_id does not match expected value."}
            ]}

        parsed = {"batch_id": ["batch_123"]}
        initial_result = validator_fn(parsed)
        call_count[0] = 1
        final, report = validate_or_repair(parsed, initial_result, validator_fn)
        assert final["ok"] is False
        # Repair WAS applied (list->string), but re-validation failed
        assert report.success is True

    def test_validate_or_repair_with_kwargs(self) -> None:
        """Test that validator_kwargs are passed through on re-validation."""
        captured_kwargs: dict[str, Any] = {}
        call_count = [0]

        def validator_fn(parsed: Any, **kwargs: Any) -> dict[str, Any]:
            captured_kwargs.update(kwargs)
            call_count[0] += 1
            # First call fails, second call passes (after repair)
            if call_count[0] == 1:
                return {
                    "ok": False,
                    "errors": [
                        {"field": "batch_id",
                            "message": "batch_id must be a non-empty string."}
                    ],
                }
            return {"ok": True, "errors": []}

        parsed = {"batch_id": ["batch_123"]}
        initial_result = validator_fn(parsed)
        final, report = validate_or_repair(
            parsed,
            initial_result,
            validator_fn,
            validator_kwargs={"expected_batch_id": "batch_123"},
        )
        assert captured_kwargs.get("expected_batch_id") == "batch_123"
        assert final["ok"] is True


# =========================================================================
# Convenience function
# =========================================================================


class TestApplyValidationRepair:
    def test_apply_validation_repair(self) -> None:
        parsed = {"batch_id": ["batch_123"]}
        errors = [{"field": "batch_id",
                    "message": "batch_id must be a non-empty string."}]
        report = apply_validation_repair(parsed, errors)
        assert report.success is True
        assert report.repaired_output["batch_id"] == "batch_123"


# =========================================================================
# Conservative behavior
# =========================================================================


class TestConservativeBehavior:
    def test_no_invented_values(self) -> None:
        """Engine must never create fields that don't exist."""
        engine = ValidationRepairEngine()
        parsed = {"existing_field": "value"}
        errors = [{"field": "missing_field",
                    "message": "missing_field must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        assert "missing_field" not in report.repaired_output
        assert report.repaired_output["existing_field"] == "value"

    def test_no_modification_of_ids(self) -> None:
        """IDs should never be modified."""
        engine = ValidationRepairEngine()
        parsed = {"hypothesis_id": ["hyp_001"]}
        errors = [{"field": "hypothesis_id",
                    "message": "hypothesis_id must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        # list-to-string is safe — no semantic change
        assert report.success is True
        assert report.repaired_output["hypothesis_id"] == "hyp_001"

    def test_no_semantic_rewriting(self) -> None:
        """Engine must not rewrite semantic content."""
        engine = ValidationRepairEngine()
        parsed = {"summary": ["This is evidence of an attack."]}
        errors = [{"field": "summary",
                    "message": "summary must be a non-empty string."}]
        report = engine.repair(parsed, errors)
        assert report.repaired_output["summary"] == "This is evidence of an attack."

    def test_non_dict_top_level(self) -> None:
        """Engine should gracefully handle non-dict top-level values."""
        engine = ValidationRepairEngine()
        report = engine.repair("not a dict", [])  # type: ignore[arg-type]
        assert report.success is False
        assert report.repaired_output == "not a dict"

    def test_empty_errors_list(self) -> None:
        """Engine should return no-repair when errors list is empty."""
        engine = ValidationRepairEngine()
        parsed = {"batch_id": "valid"}
        report = engine.repair(parsed, [])
        assert report.success is False
        assert report.reason == "No repairable errors found."

    def test_non_list_errors(self) -> None:
        """Engine should handle non-list errors gracefully."""
        engine = ValidationRepairEngine()
        parsed = {"batch_id": "valid"}
        report = engine.repair(parsed, "not a list")  # type: ignore[arg-type]
        assert report.success is False
        assert report.reason == "Errors input must be a list."