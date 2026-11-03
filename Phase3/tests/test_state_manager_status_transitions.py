"""Tests for the State Manager status-transition validation.

Verifies that the semantic transition policy correctly:
- Allows all evidence-driven transitions (unresolved -> partially_absorbed, etc.)
- Rejects only structurally dangerous transitions (merged -> anything else)
- Preserves schema and evidence-grounding validation.
"""

from __future__ import annotations

from state_manager.validator import (
    _compute_allowed_shifts,
    validate_state_delta_record,
)
from state_manager.contracts import VALID_HYPOTHESIS_STATUSES


class TestComputeAllowedShifts:
    """Unit tests for _compute_allowed_shifts."""

    def test_unresolved_allows_partially_absorbed(self) -> None:
        """unresolved -> partially_absorbed must be allowed."""
        allowed = _compute_allowed_shifts("unresolved")
        assert "partially_absorbed" in allowed

    def test_unresolved_allows_active(self) -> None:
        """unresolved -> active must be allowed."""
        allowed = _compute_allowed_shifts("unresolved")
        assert "active" in allowed

    def test_unresolved_allows_uncertain(self) -> None:
        """unresolved -> uncertain must be allowed."""
        allowed = _compute_allowed_shifts("unresolved")
        assert "uncertain" in allowed

    def test_active_allows_weakened(self) -> None:
        """active -> weakened must be allowed."""
        allowed = _compute_allowed_shifts("active")
        assert "weakened" in allowed

    def test_active_allows_uncertain(self) -> None:
        """active -> uncertain must be allowed."""
        allowed = _compute_allowed_shifts("active")
        assert "uncertain" in allowed

    def test_uncertain_allows_active(self) -> None:
        """uncertain -> active must be allowed."""
        allowed = _compute_allowed_shifts("uncertain")
        assert "active" in allowed

    def test_partially_absorbed_allows_active(self) -> None:
        """partially_absorbed -> active must be allowed."""
        allowed = _compute_allowed_shifts("partially_absorbed")
        assert "active" in allowed

    def test_merged_rejects_everything_else(self) -> None:
        """merged -> anything other than merged must be rejected."""
        allowed = _compute_allowed_shifts("merged")
        assert allowed == {"merged"}
        for status in VALID_HYPOTHESIS_STATUSES:
            if status == "merged":
                continue
            assert status not in allowed, (
                f"merged -> {status} should be rejected"
            )

    def test_all_non_merged_statuses_accept_all_transitions(self) -> None:
        """Every non-merged status should be able to reach every valid status."""
        excluded = {"merged"}
        for status in VALID_HYPOTHESIS_STATUSES:
            if status in excluded:
                continue
            allowed = _compute_allowed_shifts(status)
            for target in VALID_HYPOTHESIS_STATUSES:
                assert target in allowed, (
                    f"{status} -> {target} should be allowed"
                )

    def test_unresolved_allows_reopened(self) -> None:
        """unresolved -> reopened must be allowed."""
        allowed = _compute_allowed_shifts("unresolved")
        assert "reopened" in allowed

    def test_weakened_allows_active(self) -> None:
        """weakened -> active must be allowed."""
        allowed = _compute_allowed_shifts("weakened")
        assert "active" in allowed

    def test_weakened_allows_unresolved(self) -> None:
        """weakened -> unresolved must be allowed."""
        allowed = _compute_allowed_shifts("weakened")
        assert "unresolved" in allowed

    def test_uncertain_allows_weakened(self) -> None:
        """uncertain -> weakened must be allowed."""
        allowed = _compute_allowed_shifts("uncertain")
        assert "weakened" in allowed

    def test_uncertain_allows_reopened(self) -> None:
        """uncertain -> reopened must be allowed."""
        allowed = _compute_allowed_shifts("uncertain")
        assert "reopened" in allowed

    def test_partially_absorbed_allows_uncertain(self) -> None:
        """partially_absorbed -> uncertain must be allowed."""
        allowed = _compute_allowed_shifts("partially_absorbed")
        assert "uncertain" in allowed

    def test_partially_absorbed_allows_weakened(self) -> None:
        """partially_absorbed -> weakened must be allowed."""
        allowed = _compute_allowed_shifts("partially_absorbed")
        assert "weakened" in allowed

    def test_active_allows_partially_absorbed(self) -> None:
        """active -> partially_absorbed must be allowed."""
        allowed = _compute_allowed_shifts("active")
        assert "partially_absorbed" in allowed

    def test_dormant_allows_reopened(self) -> None:
        """dormant -> reopened must be allowed."""
        allowed = _compute_allowed_shifts("dormant")
        assert "reopened" in allowed

    def test_emerging_allows_active(self) -> None:
        """emerging -> active must be allowed."""
        allowed = _compute_allowed_shifts("emerging")
        assert "active" in allowed


class TestValidateStateDeltaRecordStatus:
    """Integration-level tests: validate_state_delta_record status validation."""

    _HANDOFF_TEMPLATE = {
        "batch_id": "test_batch",
        "round_id": "test_round",
        "hypothesis_id": "H1",
        "summary": "Test summary",
        "status": None,  # filled per test
        "evidence_refs": ["ev1"],
        "preserved_contradictions": [],
        "open_gaps": [],
        "merged_findings": ["finding1"],
        "update_focus": "Test focus",
        "applied_updates": [
            {"field": "status", "reason": "Evidence-driven transition"}
        ],
    }

    _CURRENT_HYPOTHESIS_TEMPLATE = {
        "hypothesis_id": "H1",
        "summary": "Current summary",
        "status": None,  # filled per test
        "evidence_refs": ["ev1"],
        "preserved_contradictions": [],
        "open_gaps": [],
        "merged_findings": ["finding1"],
    }

    def _run_validation(
        self, current_status: str, new_status: str
    ) -> dict:
        handoff = dict(self._HANDOFF_TEMPLATE)
        handoff["status"] = new_status
        current = dict(self._CURRENT_HYPOTHESIS_TEMPLATE)
        current["status"] = current_status
        return validate_state_delta_record(
            state_delta_record=handoff,
            current_hypothesis=current,
            aggregation_handoff={
                "batch_id": "test_batch",
                "round_id": "test_round",
                "hypothesis_id": "H1",
                "merged_findings": ["finding1"],
                "evidence_refs": ["ev1"],
                "preserved_contradictions": [],
                "open_gaps": [],
                "update_focus": "Test focus",
            },
            known_evidence_refs={"ev1"},
        )

    # --- Specific required transitions (Step 4 of task) ---

    def test_unresolved_to_partially_absorbed_passes(self) -> None:
        """unresolved -> partially_absorbed must pass validate_state_delta_record."""
        result = self._run_validation("unresolved", "partially_absorbed")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert not status_errors, (
            f"unresolved -> partially_absorbed should pass, got: {status_errors}"
        )

    def test_unresolved_to_active_passes(self) -> None:
        """unresolved -> active must pass validate_state_delta_record."""
        result = self._run_validation("unresolved", "active")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert not status_errors, (
            f"unresolved -> active should pass, got: {status_errors}"
        )

    def test_active_to_weakened_passes(self) -> None:
        """active -> weakened must pass validate_state_delta_record."""
        result = self._run_validation("active", "weakened")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert not status_errors, (
            f"active -> weakened should pass, got: {status_errors}"
        )

    def test_active_to_uncertain_passes(self) -> None:
        """active -> uncertain must pass validate_state_delta_record."""
        result = self._run_validation("active", "uncertain")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert not status_errors, (
            f"active -> uncertain should pass, got: {status_errors}"
        )

    def test_partially_absorbed_to_active_passes(self) -> None:
        """partially_absorbed -> active must pass validate_state_delta_record."""
        result = self._run_validation("partially_absorbed", "active")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert not status_errors, (
            f"partially_absorbed -> active should pass, got: {status_errors}"
        )

    def test_uncertain_to_active_passes(self) -> None:
        """uncertain -> active must pass validate_state_delta_record."""
        result = self._run_validation("uncertain", "active")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert not status_errors, (
            f"uncertain -> active should pass, got: {status_errors}"
        )

    # --- Strict rejection of structurally dangerous transitions ---

    def test_merged_to_active_fails(self) -> None:
        """merged -> active must be rejected by validate_state_delta_record."""
        result = self._run_validation("merged", "active")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert status_errors, (
            "merged -> active should be rejected"
        )

    def test_merged_to_uncertain_fails(self) -> None:
        """merged -> uncertain must be rejected by validate_state_delta_record."""
        result = self._run_validation("merged", "uncertain")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert status_errors

    def test_merged_to_weakened_fails(self) -> None:
        """merged -> weakened must be rejected by validate_state_delta_record."""
        result = self._run_validation("merged", "weakened")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert status_errors

    def test_merged_to_unresolved_fails(self) -> None:
        """merged -> unresolved must be rejected by validate_state_delta_record."""
        result = self._run_validation("merged", "unresolved")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert status_errors

    def test_merged_to_merged_passes(self) -> None:
        """merged -> merged must still pass (self-transition is fine)."""
        result = self._run_validation("merged", "merged")
        status_errors = [e for e in result["errors"] if e["field"] == "status"]
        assert not status_errors, (
            f"merged -> merged should pass, got: {status_errors}"
        )