"""Tests for the redesigned worker prompt builder with investigation-stage reasoning."""

from __future__ import annotations

from worker.prompt_builder import (
    build_worker_prompt,
    _build_bootstrap_objectives,
    _build_strategy_refinement_objectives,
    _build_evidence_acquisition_objectives,
    _build_interpretation_objectives,
    _build_investigation_review_objectives,
    _build_final_verification_objectives,
    _build_final_synthesis_objectives,
    _build_investigation_stage_objectives,
    _build_investigation_memory,
    _build_coverage_tracking,
    _build_feature_summaries,
    _build_completion_guidance,
    _step_investigation_stage,
)


def test_step_investigation_stage_mapping():
    """Verify that step indices map to correct investigation stages."""
    assert _step_investigation_stage(1, 8) == "bootstrap"
    assert _step_investigation_stage(2, 8) == "strategy_refinement"
    assert _step_investigation_stage(3, 8) == "evidence_acquisition_1"
    assert _step_investigation_stage(4, 8) == "interpretation"
    assert _step_investigation_stage(5, 8) == "evidence_acquisition_2"
    assert _step_investigation_stage(6, 8) == "investigation_review"
    assert _step_investigation_stage(7, 8) == "final_verification"
    assert _step_investigation_stage(8, 8) == "final_synthesis"
    assert _step_investigation_stage(9, 8) == "final_synthesis"


def test_step_investigation_stage_unknown_mapping():
    """Verify that unmapped steps fall back to evidence_acquisition."""
    assert _step_investigation_stage(10, 12) == "evidence_acquisition"


def test_bootstrap_objectives():
    """Verify bootstrap objectives content."""
    objectives = _build_bootstrap_objectives()
    joined = "\n".join(objectives)
    assert "BOOTSTRAP OBJECTIVES" in joined
    assert "Do not request actions" in joined
    assert "Do not draw conclusions" in joined
    assert "initial investigation strategy" in joined


def test_strategy_refinement_objectives():
    """Verify strategy refinement objectives content."""
    objectives = _build_strategy_refinement_objectives()
    joined = "\n".join(objectives)
    assert "STRATEGY REFINEMENT OBJECTIVES" in joined
    assert "highest priority targets" in joined
    assert "Do not request actions" in joined


def test_evidence_acquisition_objectives():
    """Verify evidence acquisition objectives content."""
    objectives = _build_evidence_acquisition_objectives()
    joined = "\n".join(objectives)
    assert "ACTION OBJECTIVES" in joined
    assert "uncertainty reduction" in joined
    assert "task progress" in joined
    assert "verification value" in joined
    assert "direct verification" in joined


def test_interpretation_objectives():
    """Verify interpretation objectives content."""
    objectives = _build_interpretation_objectives()
    joined = "\n".join(objectives)
    assert "INTERPRETATION OBJECTIVES" in joined
    assert "what changed" in joined
    assert "what gained support" in joined
    assert "what weakened" in joined
    assert "Do not summarize" in joined


def test_investigation_review_objectives():
    """Verify investigation review objectives content."""
    objectives = _build_investigation_review_objectives()
    joined = "\n".join(objectives)
    assert "INVESTIGATION REVIEW OBJECTIVES" in joined
    assert "what has been resolved" in joined
    assert "what remains unresolved" in joined


def test_final_verification_objectives():
    """Verify final verification objectives content."""
    objectives = _build_final_verification_objectives()
    joined = "\n".join(objectives)
    assert "FINAL VERIFICATION OBJECTIVES" in joined
    assert "unresolved task questions" in joined
    assert "Avoid exploratory actions" in joined
    assert "Focus on closure" in joined


def test_final_synthesis_objectives():
    """Verify final synthesis objectives content."""
    objectives = _build_final_synthesis_objectives()
    joined = "\n".join(objectives)
    assert "FINAL SYNTHESIS OBJECTIVES" in joined
    assert "evidence quality" in joined
    assert "investigation completeness" in joined
    assert "remaining uncertainty" in joined
    assert "Do not generate new hypotheses" in joined


def test_stage_objectives_routing():
    """Verify stage objectives routing returns correct content for each stage."""
    assert "BOOTSTRAP" in "\n".join(_build_investigation_stage_objectives("bootstrap"))
    assert "STRATEGY" in "\n".join(_build_investigation_stage_objectives("strategy_refinement"))
    assert "ACTION" in "\n".join(_build_investigation_stage_objectives("evidence_acquisition_1"))
    assert "INTERPRETATION" in "\n".join(_build_investigation_stage_objectives("interpretation"))
    assert "ACTION" in "\n".join(_build_investigation_stage_objectives("evidence_acquisition_2"))
    assert "REVIEW" in "\n".join(_build_investigation_stage_objectives("investigation_review"))
    assert "FINAL VERIFICATION" in "\n".join(_build_investigation_stage_objectives("final_verification"))
    assert "FINAL SYNTHESIS" in "\n".join(_build_investigation_stage_objectives("final_synthesis"))
    assert "ACTION" in "\n".join(_build_investigation_stage_objectives("unknown_stage"))


def test_investigation_memory_defaults():
    """Verify investigation memory produces defaults when no memory provided."""
    memory = _build_investigation_memory(None)
    assert memory["task_goal"] == "Not yet defined."
    assert memory["current_strategy"] == "Not yet defined."
    assert memory["high_priority_targets"] == []
    assert memory["verified_targets"] == []
    assert memory["remaining_targets"] == []
    assert memory["open_questions"] == []
    assert memory["completion_criteria"] == []
    assert memory["constraints"] == []


def test_investigation_memory_with_data():
    """Verify investigation memory preserves provided data."""
    provided = {
        "task_goal": "Verify shortcut signals in URG Flag Count.",
        "current_strategy": "Prioritize direct verification of low-entropy features.",
        "high_priority_targets": ["URG Flag Count", "Destination Port"],
        "verified_targets": ["URG Flag Count"],
        "remaining_targets": ["Destination Port"],
        "open_questions": ["Does Destination Port behave as a shortcut?"],
        "completion_criteria": ["Confirm or reject shortcut status."],
        "constraints": ["Stay within bounded local context."],
    }
    memory = _build_investigation_memory(provided)
    assert memory["task_goal"] == provided["task_goal"]
    assert memory["current_strategy"] == provided["current_strategy"]
    assert memory["high_priority_targets"] == provided["high_priority_targets"]
    assert memory["verified_targets"] == provided["verified_targets"]
    assert memory["remaining_targets"] == provided["remaining_targets"]
    assert memory["open_questions"] == provided["open_questions"]
    assert memory["completion_criteria"] == provided["completion_criteria"]
    assert memory["constraints"] == provided["constraints"]


def test_coverage_tracking_defaults():
    """Verify coverage tracking produces empty lists when no memory."""
    coverage = _build_coverage_tracking(None)
    assert coverage["verified_targets"] == []
    assert coverage["remaining_targets"] == []


def test_coverage_tracking_with_data():
    """Verify coverage tracking extracts from memory."""
    memory = {
        "verified_targets": ["URG Flag Count"],
        "remaining_targets": ["Destination Port"],
    }
    coverage = _build_coverage_tracking(memory)
    assert coverage["verified_targets"] == ["URG Flag Count"]
    assert coverage["remaining_targets"] == ["Destination Port"]


def test_completion_guidance():
    """Verify completion guidance content."""
    guidance = _build_completion_guidance()
    joined = "\n".join(guidance)
    assert "COMPLETION GUIDANCE" in joined
    assert "high-priority targets remain unverified" in joined
    assert "direct verification opportunities" in joined
    assert "key task questions remain unresolved" in joined
    assert "Coverage supports task completion" in joined
    assert "Coverage is not itself the task objective" in joined


def test_feature_summaries_empty():
    """Verify feature summaries handles empty context."""
    summaries = _build_feature_summaries([])
    assert summaries == []


def test_feature_summaries_from_context():
    """Verify feature summaries extracts from local context records."""
    records = [
        {
            "context_ref": "ctx_a",
            "feature_names": ["URG Flag Count", "Destination Port"],
            "source_items": [
                {"summary": "low_variance detected", "source_kind": "compressed_region"},
                {"summary": "variance_ratio high", "source_kind": "compressed_region"},
            ],
        }
    ]
    summaries = _build_feature_summaries(records)
    assert len(summaries) == 2
    feature_names = {s["feature"] for s in summaries}
    assert "URG Flag Count" in feature_names
    assert "Destination Port" in feature_names


def test_feature_summaries_prefers_structured_signals():
    """Verify feature_summary source_kind uses structured signal parsing."""
    records = [
        {
            "context_ref": "ctx_a",
            "feature_names": ["URG Flag Count"],
            "source_items": [
                {"summary": "low_variance, low_diversity", "source_kind": "feature_summary"},
            ],
        }
    ]
    summaries = _build_feature_summaries(records)
    assert len(summaries) == 1
    signals = summaries[0]["signals"]
    assert "low_variance" in signals
    assert "low_diversity" in signals


def test_bootstrap_stage_prompt_has_feature_summaries():
    """Verify bootstrap stage includes feature summaries section."""
    prompt = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification", "feature_analysis"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[
            {
                "context_ref": "ctx_a",
                "feature_names": ["URG Flag Count"],
                "feature_groups": [],
                "locality": {},
                "source_items": [{"source_kind": "compressed_region", "source_id": "r1", "summary": "low_variance"}],
            }
        ],
        action_guidance=[
            {"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""},
            {"action_class": "feature_analysis", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""},
        ],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=1,
    )
    assert "FEATURE_SUMMARIES" in prompt
    assert "INVESTIGATION_MEMORY" in prompt
    assert "BOOTSTRAP" in prompt


def test_non_bootstrap_stage_no_feature_summaries():
    """Verify non-bootstrap stages do not include feature summaries."""
    prompt = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[],
        action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=4,
    )
    assert "FEATURE_SUMMARIES" not in prompt
    assert "INVESTIGATION_MEMORY" in prompt


def test_coverage_tracking_starts_at_step_5():
    """Verify coverage tracking appears starting at step 5."""
    for step in [5, 6, 7, 8]:
        prompt = build_worker_prompt(
            batch_id="batch_001",
            round_id="round_001",
            worker_task={
                "task_id": "task_001",
                "hypothesis_id": "hyp_001",
                "task_scope": "Check for shortcut signals.",
                "allowed_actions": ["shortcut_verification"],
                "local_context_refs": ["ctx_a"],
                "stop_conditions": [],
            },
            local_context_records=[],
            action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
            tool_events=[],
            budget_rules={"max_steps": 8, "max_retries": 1},
            current_step=step,
        )
        assert "COVERAGE_TRACKING" in prompt, f"Step {step} should have coverage tracking"


def test_no_coverage_tracking_before_step_5():
    """Verify coverage tracking does not appear before step 5."""
    for step in [1, 2, 3, 4]:
        prompt = build_worker_prompt(
            batch_id="batch_001",
            round_id="round_001",
            worker_task={
                "task_id": "task_001",
                "hypothesis_id": "hyp_001",
                "task_scope": "Check for shortcut signals.",
                "allowed_actions": ["shortcut_verification"],
                "local_context_refs": ["ctx_a"],
                "stop_conditions": [],
            },
            local_context_records=[],
            action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
            tool_events=[],
            budget_rules={"max_steps": 8, "max_retries": 1},
            current_step=step,
        )
        assert "COVERAGE_TRACKING" not in prompt, f"Step {step} should NOT have coverage tracking"


def test_completion_guidance_at_steps_7_and_8():
    """Verify completion guidance appears at steps 7 and 8."""
    for step in [7, 8]:
        prompt = build_worker_prompt(
            batch_id="batch_001",
            round_id="round_001",
            worker_task={
                "task_id": "task_001",
                "hypothesis_id": "hyp_001",
                "task_scope": "Check for shortcut signals.",
                "allowed_actions": ["shortcut_verification"],
                "local_context_refs": ["ctx_a"],
                "stop_conditions": [],
            },
            local_context_records=[],
            action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
            tool_events=[],
            budget_rules={"max_steps": 8, "max_retries": 1},
            current_step=step,
        )
        assert "COMPLETION GUIDANCE" in prompt, f"Step {step} should have completion guidance"


def test_no_completion_guidance_before_step_7():
    """Verify completion guidance does not appear before step 7."""
    for step in [1, 2, 3, 4, 5, 6]:
        prompt = build_worker_prompt(
            batch_id="batch_001",
            round_id="round_001",
            worker_task={
                "task_id": "task_001",
                "hypothesis_id": "hyp_001",
                "task_scope": "Check for shortcut signals.",
                "allowed_actions": ["shortcut_verification"],
                "local_context_refs": ["ctx_a"],
                "stop_conditions": [],
            },
            local_context_records=[],
            action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
            tool_events=[],
            budget_rules={"max_steps": 8, "max_retries": 1},
            current_step=step,
        )
        assert "COMPLETION GUIDANCE" not in prompt, f"Step {step} should NOT have completion guidance"


def test_investigation_stage_label_in_prompt():
    """Verify investigation stage label appears in prompt."""
    prompt = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[],
        action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=1,
    )
    assert "INVESTIGATION_STAGE" in prompt
    assert "Bootstrap" in prompt
    prompt2 = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[],
        action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=5,
    )
    assert "Evidence Acquisition 2" in prompt2


def test_investigation_memory_passed_through():
    """Verify investigation memory is reflected in prompt when provided."""
    memory = {
        "task_goal": "Check if URG Flag Count is a shortcut.",
        "current_strategy": "Verify low-diversity features directly.",
        "high_priority_targets": ["URG Flag Count"],
        "verified_targets": [],
        "remaining_targets": ["URG Flag Count"],
        "open_questions": ["Is URG Flag Count a shortcut?"],
    }
    prompt = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[],
        action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=3,
        investigation_memory=memory,
    )
    assert memory["task_goal"] in prompt
    assert memory["current_strategy"] in prompt


def test_investigation_memory_is_reference_not_update():
    """Verify investigation memory language says 'Use as reference' not 'Update'."""
    prompt = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[],
        action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=3,
    )
    assert "Use INVESTIGATION_MEMORY as the current investigation reference" in prompt
    # Should NOT use "Update it" language
    assert "Update it" not in prompt


def test_output_contracts_unchanged():
    """Verify all output contracts remain exactly as before."""
    prompt = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[],
        action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=3,  # action stage
    )
    # Action contract unchanged
    assert "action_class must be one of the allowed action classes." in prompt
    assert "context_ref must be one of the allowed local_context_refs." in prompt
    assert "related_feature_name must be a non-empty string when present." in prompt
    assert "related_feature_name is OPTIONAL." in prompt
    assert "IF NOT REQUIRED, OMIT THE FIELD COMPLETELY." in prompt

    # Final synthesis contract unchanged
    prompt_final = build_worker_prompt(
        batch_id="batch_001",
        round_id="round_001",
        worker_task={
            "task_id": "task_001",
            "hypothesis_id": "hyp_001",
            "task_scope": "Check for shortcut signals.",
            "allowed_actions": ["shortcut_verification"],
            "local_context_refs": ["ctx_a"],
            "stop_conditions": [],
        },
        local_context_records=[],
        action_guidance=[{"action_class": "shortcut_verification", "supported_scopes": ["feature"], "required_inputs": ["feature_name"], "boundedness_notes": ""}],
        tool_events=[],
        budget_rules={"max_steps": 8, "max_retries": 1},
        current_step=8,
    )
    assert "status must be one of: completed, partial, failed, inconclusive." in prompt_final