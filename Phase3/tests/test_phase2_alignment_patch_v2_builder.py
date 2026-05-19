import os
import re

from prompts.builder import (
    _build_redundancy_components,
    _get_candidate_component_penalty,
    _get_component_exploration,
    _get_recent_mechanism_cooldown,
    _get_recent_mechanism_penalty,
    _get_recent_mechanism_streak,
    _get_mechanism_penalty,
    _get_mechanism_usage_counts,
    build_prompt,
    extract_overview_facts,
    filter_candidates_by_reconfirmation,
    is_reconfirming_known_fact,
)
from state.schema import EvidenceBlock
from state.store import add_evidence, init_state


def _extract_section(prompt_text: str, header: str) -> str:
    marker = f"{header}:\n"
    start = prompt_text.find(marker)
    if start < 0:
        return ""
    remainder = prompt_text[start + len(marker):]
    next_break = remainder.find("\n\n")
    if next_break < 0:
        return remainder.strip()
    return remainder[:next_break].strip()


def test_prompt_support_is_not_inflated_across_multiple_evidence_blocks():
    state = init_state(
        run_id="support_fix",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )
    add_evidence(
        state,
        "f1",
        EvidenceBlock(
            feature="f1",
            signals=["low_cardinality"],
            metrics={"cardinality_ratio": 0.1},
            support={"total_samples": 6, "per_class": {
                "BENIGN": 2, "ATTACK": 4}},
            provenance={"tool": "cardinality_analysis", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f1",
        EvidenceBlock(
            feature="f1",
            signals=["near_constant"],
            metrics={"unique_values": 2},
            support={"total_samples": 6, "per_class": {
                "BENIGN": 2, "ATTACK": 4}},
            provenance={"tool": "feature_summary", "step": 2},
            status="active",
        ),
    )

    prompt_text = build_prompt(
        state, ["cardinality_analysis", "feature_summary"])
    analyzed_section = _extract_section(
        prompt_text, "ALREADY_ANALYZED_FEATURES")

    assert "total_samples=6" in analyzed_section
    assert "total_samples=12" not in analyzed_section


def test_mixed_additional_candidates_are_balanced_and_change_with_coverage():
    summaries = {
        "f_low1": {"unique_values": 2, "cardinality_ratio": 0.01, "skewness": 0.1, "redundancy": []},
        "f_low2": {"unique_values": 3, "cardinality_ratio": 0.02, "skewness": 0.2, "redundancy": []},
        "f_skew1": {"unique_values": 20, "cardinality_ratio": 0.5, "skewness": 4.5, "redundancy": []},
        "f_skew2": {"unique_values": 25, "cardinality_ratio": 0.6, "skewness": 3.8, "redundancy": []},
        "f_red1": {
            "unique_values": 15,
            "cardinality_ratio": 0.3,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_red2", "correlation": 0.98}],
        },
        "f_red2": {
            "unique_values": 15,
            "cardinality_ratio": 0.35,
            "skewness": 0.2,
            "redundancy": [{"feature": "f_red1", "correlation": 0.98}],
        },
    }
    state = init_state(
        run_id="overview_mix",
        objective="test",
        max_steps=1,
        available_features=list(summaries),
        metadata={"compact_feature_index": summaries},
    )

    prompt_initial = build_prompt(
        state,
        [
            "distribution_analysis",
            "cardinality_analysis",
            "feature_relation",
            "duplication_analysis",
        ],
    )
    candidates_initial = _extract_section(
        prompt_initial, "ADDITIONAL_CANDIDATES")
    candidate_lines_initial = [
        line for line in candidates_initial.splitlines() if line.startswith("-")]

    assert 3 <= len(candidate_lines_initial) <= 4
    assert any(
        "dataset-level duplication" in line for line in candidate_lines_initial)
    assert any(
        "Inspect low-cardinality behavior" in line and "f_low" in line
        for line in candidate_lines_initial
    )
    assert any(
        "Check distribution anomaly" in line and "f_skew" in line
        for line in candidate_lines_initial
    )
    assert any(
        "Test dependency between" in line and "f_red" in line
        for line in candidate_lines_initial
    )

    add_evidence(
        state,
        "f_low1",
        EvidenceBlock(
            feature="f_low1",
            signals=["low_cardinality"],
            metrics={"cardinality_ratio": 0.01},
            support={"total_samples": 10},
            provenance={"tool": "cardinality_analysis", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_skew1",
        EvidenceBlock(
            feature="f_skew1",
            signals=["high_skew"],
            metrics={"skewness": 4.5},
            support={"total_samples": 10},
            provenance={"tool": "feature_summary", "step": 1},
            status="active",
        ),
    )

    prompt_after = build_prompt(
        state,
        [
            "distribution_analysis",
            "cardinality_analysis",
            "feature_relation",
            "duplication_analysis",
        ],
    )
    candidates_after = _extract_section(prompt_after, "ADDITIONAL_CANDIDATES")

    assert candidates_initial != candidates_after
    assert "f_low1" not in candidates_after
    assert "f_skew1" not in candidates_after


def test_partition_context_is_injected_before_overview_and_instructions(monkeypatch):
    state = init_state(
        run_id="partition_context",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )
    monkeypatch.setenv("NIDS_DATASET_PATH", "Thursday-Morning-WebAttacks.csv")

    prompt_text = build_prompt(state, ["feature_summary"])
    context_section = _extract_section(prompt_text, "PARTITION_CONTEXT")

    assert "application-layer interactions" in context_section
    assert "detect anomalies" not in context_section.lower()
    assert prompt_text.index("STRICT_OUTPUT_RULES:\n") < prompt_text.index(
        "OBJECTIVE:\n")
    assert prompt_text.index("OBJECTIVE:\n") < prompt_text.index(
        "DECISION_CRITERIA:\n")
    assert prompt_text.index("DECISION_CRITERIA:\n") < prompt_text.index(
        "STRATEGY:\n")
    assert prompt_text.index("STRATEGY:\n") < prompt_text.index(
        "CONTEXT:\n")
    assert prompt_text.index("CONTEXT:\n") < prompt_text.index(
        "PARTITION_CONTEXT:\n")
    assert prompt_text.index(
        "PARTITION_CONTEXT:\n") < prompt_text.index("OVERVIEW:\n")


def test_partition_context_block_remains_present_when_context_is_unavailable(monkeypatch):
    state = init_state(
        run_id="partition_context_empty",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )
    monkeypatch.delenv("NIDS_DATASET_PATH", raising=False)

    prompt_text = build_prompt(state, ["feature_summary"])

    assert prompt_text.count("PARTITION_CONTEXT:\n") == 1
    assert _extract_section(prompt_text, "PARTITION_CONTEXT") == ""
    assert prompt_text.index("CONTEXT:\n") < prompt_text.index(
        "PARTITION_CONTEXT:\n")
    assert prompt_text.index(
        "PARTITION_CONTEXT:\n") < prompt_text.index("OVERVIEW:\n")


def test_prompt_includes_decision_criteria():
    state = init_state(
        run_id="reasoning_rules",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert "DECISION_CRITERIA:\n" in prompt_text
    assert "Reason over artefact families, not isolated features or one-off pairs." in prompt_text
    assert "Do not re-confirm a fact in KNOWN_FACTS when the next action probes the same mechanism." in prompt_text
    assert "Do not repeat failed actions with the same input." in prompt_text
    assert "Prefer new information over confirming an already established pattern." in prompt_text
    assert "In the first 1-2 steps, prefer one high-information global falsifier (`duplication_analysis` or `cardinality_analysis`) before stacking local relation checks, unless strong evidence already bounds the global story." in prompt_text
    assert "After one or two strong confirmations in the same family, treat that family as provisionally established." in prompt_text
    assert "Do not treat ADDITIONAL_CANDIDATES as a checklist or ranked queue." in prompt_text
    assert prompt_text.index("OBJECTIVE:\n") < prompt_text.index(
        "DECISION_CRITERIA:\n"
    )
    assert prompt_text.index("DECISION_CRITERIA:\n") < prompt_text.index(
        "STRATEGY:\n"
    )


def test_prompt_prioritizes_parse_safe_output_rules():
    state = init_state(
        run_id="parse_safe_output",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert "TOP PRIORITY: produce one valid 3-line block even if reasoning must be shorter." in prompt_text
    assert "Never repeat THOUGHT. Never omit ACTION. Never omit ACTION_INPUT." in prompt_text
    assert "ACTION_INPUT must stay on one line." in prompt_text
    assert "FINAL CHECK BEFORE OUTPUT: exactly 3 non-empty lines, exact prefixes once each, valid one-line JSON." in prompt_text
    assert prompt_text.index(
        "STRICT_OUTPUT_RULES:\n") < prompt_text.index("OBJECTIVE:\n")


def test_prompt_prioritizes_non_obvious_and_shared_pattern_rules():
    state = init_state(
        run_id="non_obvious_focus",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert "Treat similar features with the same signal as one pattern rather than separate tasks." in prompt_text
    assert "Stop exploring a pattern once the mechanism is understood unless the next step adds a different mechanism, stronger evidence, or resolves a contradiction." in prompt_text
    assert "Do not rotate across sibling or near-duplicate features when they express the same pattern." in prompt_text
    assert "Keep same-mechanism bursts short. After two consecutive actions in the same mechanism, prefer an orthogonal mechanism unless resolving a contradiction or recovering from a failed step." in prompt_text
    assert "If a blocked action occurs, ban that exact target and avoid nearby variants from the same family on the next step." in prompt_text
    assert "Start broad, test a global falsifier early, then narrow only after the broad story is bounded." in prompt_text
    assert "If dependency is already supported, prefer duplication, cardinality, or distribution before another nearby relation." in prompt_text
    assert "Treat already visible signals in the current context as background, not as primary targets for repeated analysis." in prompt_text
    assert "If a signal family appears across multiple features, treat it as shared structure and move on unless the next step adds different information or tests a different mechanism." in prompt_text
    assert "`duplication_analysis` is dataset-level only." in prompt_text
    assert "For `feature_relation`, ACTION_INPUT.feature_name may be one valid feature or one exact pair written as `feature_a|feature_b`." in prompt_text
    assert "Use CURRENT_PROGRESS, ACTIVE_PATTERNS, and STEP_SUMMARY to detect repetition and saturation." in prompt_text
    assert "Avoid repeating actions already visible in STEP_SUMMARY unless the next step changes mechanism or resolves a contradiction." in prompt_text
    assert "If CURRENT_PROGRESS marks a mechanism as explored multiple times, switch signal type." in prompt_text
    assert "Prefer changing mechanism over refining the same local pattern." in prompt_text
    assert "Do not probe multiple features from the same underlying structure." in prompt_text
    assert prompt_text.index("STRATEGY:\n") < prompt_text.index(
        "CONTEXT:\n"
    )


def test_prompt_renders_progress_sections_in_order_with_compact_memory():
    state = init_state(
        run_id="progress_sections",
        objective="test",
        max_steps=4,
        available_features=["f_dist", "f_dist_2",
                            "f_card", "f_rel_a", "f_rel_b"],
    )
    add_evidence(
        state,
        "f_dist",
        EvidenceBlock(
            feature="f_dist",
            signals=["high_skew"],
            metrics={"dominant_ratio": 0.42},
            support={"total_samples": 20},
            provenance={"tool": "distribution_analysis", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_dist_2",
        EvidenceBlock(
            feature="f_dist_2",
            signals=["high_skew"],
            metrics={"dominant_ratio": 0.33},
            support={"total_samples": 20},
            provenance={"tool": "distribution_analysis", "step": 2},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_rel_a|f_rel_b",
        EvidenceBlock(
            feature="f_rel_a|f_rel_b",
            signals=["high_redundancy"],
            metrics={"correlation": 0.999},
            support={"total_samples": 20},
            provenance={"tool": "feature_relation", "step": 3},
            status="active",
        ),
    )
    state.history.extend(
        [
            {
                "step_id": 1,
                "action": "distribution_analysis",
                "action_input": {"feature_name": "f_dist"},
                "observation": {
                    "ok": True,
                    "tool": "distribution_analysis",
                    "feature_name": "f_dist",
                    "value": 0.42,
                    "error_code": None,
                },
                "execution_status": "OK",
            },
            {
                "step_id": 2,
                "action": "distribution_analysis",
                "action_input": {"feature_name": "f_dist_2"},
                "observation": {
                    "ok": True,
                    "tool": "distribution_analysis",
                    "feature_name": "f_dist_2",
                    "value": 0.33,
                    "error_code": None,
                },
                "execution_status": "OK",
            },
            {
                "step_id": 3,
                "action": "feature_relation",
                "action_input": {"feature_name": "f_rel_a|f_rel_b"},
                "observation": {
                    "ok": True,
                    "tool": "feature_relation",
                    "feature_name": "f_rel_a|f_rel_b",
                    "value": 0.999,
                    "error_code": None,
                },
                "execution_status": "OK",
            },
            {
                "step_id": 4,
                "action": "duplication_analysis",
                "action_input": {"feature_name": "__dataset__"},
                "observation": {
                    "ok": False,
                    "tool": "duplication_analysis",
                    "feature_name": "__dataset__",
                    "value": None,
                    "error_code": "REPEATED_FEATURE_BLOCKED",
                },
                "execution_status": "REPEATED_FEATURE_BLOCKED",
            },
        ]
    )

    prompt_text = build_prompt(
        state,
        ["distribution_analysis", "cardinality_analysis",
            "feature_relation", "duplication_analysis"],
    )

    assert prompt_text.index(
        "CURRENT_PROGRESS:\n") < prompt_text.index("STEP_SUMMARY:\n")
    assert prompt_text.index("STEP_SUMMARY:\n") < prompt_text.index(
        "ADDITIONAL_CANDIDATES:\n")
    assert "ACTIVE_PATTERNS:\n" in prompt_text

    current_progress = _extract_section(prompt_text, "CURRENT_PROGRESS")
    step_summary = _extract_section(prompt_text, "STEP_SUMMARY")

    assert "- dependency: established" in current_progress
    assert "- distribution: explored multiple times (low additional value)" in current_progress
    assert "- cardinality: not explored" in current_progress
    assert "- duplication: already observed (unlikely to add new information)" in current_progress
    assert "- distribution: f_dist -> high skew (non-uniform)" in step_summary
    assert "- distribution: f_dist_2 -> high skew (non-uniform)" in step_summary
    assert "- relation: f_rel_a|f_rel_b -> strong correlation (~1.0)" in step_summary
    assert "- duplication: dataset -> repeated target (already observed)" in step_summary


def test_step_summary_lines_follow_fixed_compact_format():
    state = init_state(
        run_id="step_summary_format",
        objective="test",
        max_steps=3,
        available_features=["f1", "f2"],
    )
    add_evidence(
        state,
        "f1|f2",
        EvidenceBlock(
            feature="f1|f2",
            signals=["high_redundancy"],
            metrics={"correlation": 0.999},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    state.history.extend(
        [
            {
                "step_id": 1,
                "action": "feature_relation",
                "action_input": {"feature_name": "f1|f2"},
                "observation": {
                    "ok": True,
                    "tool": "feature_relation",
                    "feature_name": "f1|f2",
                    "value": 0.999,
                    "error_code": None,
                },
                "execution_status": "OK",
            },
            {
                "step_id": 2,
                "action": "duplication_analysis",
                "action_input": {"feature_name": "__dataset__"},
                "observation": {
                    "ok": False,
                    "tool": "duplication_analysis",
                    "feature_name": "__dataset__",
                    "value": None,
                    "error_code": "REPEATED_FEATURE_BLOCKED",
                },
                "execution_status": "REPEATED_FEATURE_BLOCKED",
            },
        ]
    )

    prompt_text = build_prompt(
        state, ["feature_relation", "duplication_analysis"])
    step_summary = _extract_section(prompt_text, "STEP_SUMMARY")
    step_lines = [line for line in step_summary.splitlines()
                  if line.startswith("-")]

    assert step_lines
    assert all(re.match(r"^- [a-z]+: .+ -> .+ \(.+\)$", line)
               for line in step_lines)


def test_active_patterns_is_omitted_without_repeated_support():
    state = init_state(
        run_id="active_patterns_omit",
        objective="test",
        max_steps=2,
        available_features=["f1", "f2"],
    )
    add_evidence(
        state,
        "f1|f2",
        EvidenceBlock(
            feature="f1|f2",
            signals=["high_redundancy"],
            metrics={"correlation": 0.99},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    state.history.append(
        {
            "step_id": 1,
            "action": "feature_relation",
            "action_input": {"feature_name": "f1|f2"},
            "observation": {
                "ok": True,
                "tool": "feature_relation",
                "feature_name": "f1|f2",
                "value": 0.99,
                "error_code": None,
            },
            "execution_status": "OK",
        }
    )

    prompt_text = build_prompt(state, ["feature_relation"])

    assert "ACTIVE_PATTERNS:\n" not in prompt_text


def test_additional_candidates_are_mechanism_diverse_and_dedupe_neighborhoods():
    summaries = {
        "f_low": {"unique_values": 2, "cardinality_ratio": 0.01, "skewness": 0.1, "redundancy": []},
        "Fwd Header Length": {"unique_values": 20, "cardinality_ratio": 0.4, "skewness": 4.8, "redundancy": []},
        "Fwd Header Length.1": {"unique_values": 20, "cardinality_ratio": 0.4, "skewness": 4.8, "redundancy": []},
        "f_rel_a": {
            "unique_values": 30,
            "cardinality_ratio": 0.4,
            "skewness": 0.2,
            "redundancy": [{"feature": "f_rel_b", "correlation": 0.99}],
        },
        "f_rel_b": {
            "unique_values": 30,
            "cardinality_ratio": 0.4,
            "skewness": 0.2,
            "redundancy": [{"feature": "f_rel_a", "correlation": 0.99}],
        },
    }
    state = init_state(
        run_id="candidate_diversity",
        objective="test",
        max_steps=1,
        available_features=list(summaries),
        metadata={"compact_feature_index": summaries},
    )

    prompt_text = build_prompt(
        state,
        ["distribution_analysis", "cardinality_analysis",
            "feature_relation", "duplication_analysis"],
    )
    candidate_lines = [
        line
        for line in _extract_section(prompt_text, "ADDITIONAL_CANDIDATES").splitlines()
        if line.startswith("-")
    ]

    assert 3 <= len(candidate_lines) <= 4
    assert any("dataset-level duplication" in line for line in candidate_lines)
    assert any(
        "Inspect low-cardinality behavior" in line for line in candidate_lines)
    assert any("Check distribution anomaly" in line for line in candidate_lines)
    assert any("Test dependency between" in line for line in candidate_lines)
    assert not (
        any("Fwd Header Length" in line for line in candidate_lines)
        and any("Fwd Header Length.1" in line for line in candidate_lines)
    )


def test_pattern_coverage_marks_saturated_families_and_biases_candidates():
    summaries = {
        "f_red1": {
            "unique_values": 12,
            "cardinality_ratio": 0.2,
            "skewness": 0.2,
            "redundancy": [{"feature": "f_red2", "correlation": 0.98}],
        },
        "f_red2": {
            "unique_values": 12,
            "cardinality_ratio": 0.2,
            "skewness": 0.3,
            "redundancy": [{"feature": "f_red1", "correlation": 0.98}],
        },
        "f_low1": {
            "unique_values": 2,
            "cardinality_ratio": 0.01,
            "skewness": 0.1,
            "redundancy": [],
        },
        "f_skew1": {
            "unique_values": 20,
            "cardinality_ratio": 0.4,
            "skewness": 5.2,
            "redundancy": [],
        },
    }
    state = init_state(
        run_id="pattern_coverage",
        objective="test",
        max_steps=1,
        available_features=list(summaries),
        metadata={"compact_feature_index": summaries},
    )
    add_evidence(
        state,
        "f_rel_a|f_rel_b",
        EvidenceBlock(
            feature="f_rel_a|f_rel_b",
            signals=["high_redundancy"],
            metrics={"correlation": 0.99},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "__dataset__",
        EvidenceBlock(
            feature="__dataset__",
            signals=["high_duplication"],
            metrics={"duplicate_ratio": 0.2},
            support={"total_samples": 10},
            provenance={"tool": "duplication_analysis", "step": 2},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_low_seen",
        EvidenceBlock(
            feature="f_low_seen",
            signals=["low_diversity"],
            metrics={"unique_values": 1},
            support={"total_samples": 10},
            provenance={"tool": "feature_summary", "step": 3},
            status="active",
        ),
    )

    prompt_text = build_prompt(
        state, ["feature_summary", "feature_relation", "duplication_analysis"])
    pattern_coverage = _extract_section(prompt_text, "PATTERN_COVERAGE")
    candidate_lines = [
        line
        for line in _extract_section(prompt_text, "ADDITIONAL_CANDIDATES").splitlines()
        if line.startswith("-")
    ]

    assert "- constant / low variance: weak (1 feature)" in pattern_coverage
    assert "- redundancy / dependency: established (2 features)" in pattern_coverage
    assert "- distribution skew / collapse: none" in pattern_coverage
    assert "f_skew1" in candidate_lines[0]
    assert any("f_red" in line for line in candidate_lines)


def test_prompt_is_single_purpose_and_removes_summary_generation_guidance():
    state = init_state(
        run_id="single_purpose_prompt",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert (
        "Decide only the next action. Do NOT generate summaries, reports, or multiple feature analyses."
        in prompt_text
    )
    assert "FEATURE_SUMMARIES" not in prompt_text
    assert "Keep each feature block compact" not in prompt_text
    assert "The overview should read as a working hypothesis" not in prompt_text
    assert "THOUGHT FORMAT GUIDANCE" not in prompt_text
    assert "Example:" not in prompt_text
    assert "Output one block only. No extra text, no repeated block, and no additional JSON object." in prompt_text


def test_recent_history_renders_action_input_as_json():
    state = init_state(
        run_id="history_json",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )
    state.history.append(
        {
            "step_id": 1,
            "thought": "Hypothesis: f1 may be low-cardinality. | Scope: f1 | Next action: Run `feature_summary` on `f1`.",
            "action": "feature_summary",
            "action_input": {"feature_name": "f1"},
            "observation": {
                "ok": True,
                "tool": "feature_summary",
                "feature_name": "f1",
                "value": 1,
                "error_code": None,
            },
            "execution_status": "OK",
        }
    )

    prompt_text = build_prompt(state, ["feature_summary"])
    recent_history = _extract_section(prompt_text, "RECENT_HISTORY")

    assert '- Last success: feature_summary {"feature_name": "f1"}' in recent_history
    assert "THOUGHT:" not in recent_history
    assert "Hypothesis:" not in recent_history
    assert "Last failure:" not in recent_history


def test_recent_history_preserves_last_failure_and_error_code():
    state = init_state(
        run_id="history_failure",
        objective="test",
        max_steps=3,
        available_features=["f1", "f2"],
    )
    state.history.extend(
        [
            {
                "step_id": 1,
                "action": "feature_summary",
                "action_input": {"feature_name": "f1"},
                "observation": {
                    "ok": True,
                    "tool": "feature_summary",
                    "feature_name": "f1",
                    "value": 1,
                    "error_code": None,
                },
                "execution_status": "OK",
            },
            {
                "step_id": 2,
                "action": "feature_relation",
                "action_input": {"feature_name": "f1|f2"},
                "observation": {
                    "ok": False,
                    "tool": "feature_relation",
                    "feature_name": "f1|f2",
                    "error_code": "BLOCKED",
                },
                "execution_status": "BLOCKED",
            },
        ]
    )

    prompt_text = build_prompt(state, ["feature_summary", "feature_relation"])
    recent_history = _extract_section(prompt_text, "RECENT_HISTORY")

    assert '- Last success: feature_summary {"feature_name": "f1"}' in recent_history
    assert '- Last failure: feature_relation {"feature_name": "f1|f2"} -> error_code=BLOCKED' in recent_history


def test_is_reconfirming_known_fact_blocks_value_distribution_for_known_constant():
    facts = extract_overview_facts(
        {
            "f_constant": {
                "unique_values": 1,
                "cardinality_ratio": 0.01,
                "skewness": 0.0,
                "redundancy": [],
            }
        }
    )

    assert is_reconfirming_known_fact("feature_summary", "f_constant", facts)
    assert is_reconfirming_known_fact(
        "cardinality_analysis", "f_constant", facts)


def test_is_reconfirming_known_fact_blocks_distribution_analysis_for_low_entropy():
    facts = extract_overview_facts(
        {
            "f_entropy": {
                "signals": ["low_entropy"],
                "unique_values": 5,
                "cardinality_ratio": 0.05,
                "skewness": 0.0,
                "redundancy": [],
            }
        }
    )

    assert is_reconfirming_known_fact(
        "distribution_analysis", "f_entropy", facts)


def test_is_reconfirming_known_fact_blocks_distribution_analysis_for_high_skew_signal():
    facts = extract_overview_facts(
        {
            "f_skew": {
                "signals": ["high_skew"],
                "unique_values": 25,
                "cardinality_ratio": 0.4,
                "skewness": 4.8,
                "redundancy": [],
            }
        }
    )

    assert is_reconfirming_known_fact(
        "distribution_analysis", "f_skew", facts)


def test_feature_relation_remains_allowed_for_known_constant():
    facts = extract_overview_facts(
        {
            "f_constant": {
                "unique_values": 1,
                "cardinality_ratio": 0.01,
                "skewness": 0.0,
                "redundancy": [],
            }
        }
    )

    assert not is_reconfirming_known_fact(
        "feature_relation", "f_constant", facts)


def test_redundancy_hint_does_not_block_relational_extension():
    summaries = {
        "f_red": {
            "unique_values": 12,
            "cardinality_ratio": 0.2,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_other", "correlation": 0.99}],
        }
    }
    facts = extract_overview_facts(summaries)
    filtered = filter_candidates_by_reconfirmation(
        [{"feature_name": "f_red", "signals": ["redundant_with=f_other@0.99"]}],
        "redundancy",
        facts,
    )

    assert [candidate["feature_name"] for candidate in filtered] == ["f_red"]


def test_mechanism_budget_penalty_applies_after_repeated_value_distribution_steps():
    state = init_state(
        run_id="mechanism_budget",
        objective="test",
        max_steps=4,
        available_features=["f1"],
    )
    state.history.extend(
        [
            {
                "step_id": 1,
                "action": "cardinality_analysis",
                "execution_status": "OK",
            },
            {
                "step_id": 2,
                "action": "distribution_analysis",
                "execution_status": "OK",
            },
            {
                "step_id": 3,
                "action": "feature_summary",
                "execution_status": "OK",
            },
        ]
    )

    counts = _get_mechanism_usage_counts(state)

    assert counts["value_distribution"] == 3
    assert _get_mechanism_penalty({"value_distribution"}, counts) > 0
    assert _get_mechanism_penalty({"dependency"}, counts) == 0


def test_recent_mechanism_cooldown_activates_after_streak_and_strong_dependency_evidence():
    state = init_state(
        run_id="recent_cooldown",
        objective="test",
        max_steps=4,
        available_features=["f1", "f2", "f3"],
    )
    state.history.extend(
        [
            {
                "step_id": 1,
                "action": "feature_relation",
                "execution_status": "OK",
            },
            {
                "step_id": 2,
                "action": "feature_relation",
                "execution_status": "OK",
            },
        ]
    )
    add_evidence(
        state,
        "f1|f2",
        EvidenceBlock(
            feature="f1|f2",
            signals=["high_redundancy"],
            metrics={"correlation": 1.0},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f2|f3",
        EvidenceBlock(
            feature="f2|f3",
            signals=["high_redundancy"],
            metrics={"correlation": 0.98},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 2},
            status="active",
        ),
    )

    mechanism, streak = _get_recent_mechanism_streak(state)
    cooldown = _get_recent_mechanism_cooldown(state)

    assert mechanism == "dependency"
    assert streak == 2
    assert cooldown["active"] is True
    assert _get_recent_mechanism_penalty(
        {"dependency"}, cooldown, state, "f1") > 0
    assert _get_recent_mechanism_penalty(
        {"value_distribution"}, cooldown, state, "f1") == 0


def test_saturated_redundancy_component_is_softly_downranked_but_not_removed():
    summaries = {
        "f_comp_a": {
            "unique_values": 12,
            "cardinality_ratio": 0.2,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_comp_b", "correlation": 0.98},
                {"feature": "f_comp_c", "correlation": 0.97},
            ],
        },
        "f_comp_b": {
            "unique_values": 12,
            "cardinality_ratio": 0.22,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_comp_a", "correlation": 0.98},
                {"feature": "f_comp_c", "correlation": 0.96},
            ],
        },
        "f_comp_c": {
            "unique_values": 12,
            "cardinality_ratio": 0.24,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_comp_a", "correlation": 0.97},
                {"feature": "f_comp_b", "correlation": 0.96},
            ],
        },
        "f_other_a": {
            "unique_values": 14,
            "cardinality_ratio": 0.25,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_other_b", "correlation": 0.96}],
        },
        "f_other_b": {
            "unique_values": 14,
            "cardinality_ratio": 0.26,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_other_a", "correlation": 0.96}],
        },
    }
    state = init_state(
        run_id="component_penalty",
        objective="test",
        max_steps=3,
        available_features=list(summaries),
        metadata={"compact_feature_index": summaries},
    )
    add_evidence(
        state,
        "f_comp_a|f_comp_b",
        EvidenceBlock(
            feature="f_comp_a|f_comp_b",
            signals=["high_redundancy"],
            metrics={"correlation": 0.98},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_comp_b|f_comp_c",
        EvidenceBlock(
            feature="f_comp_b|f_comp_c",
            signals=["high_redundancy"],
            metrics={"correlation": 0.96},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 2},
            status="active",
        ),
    )

    prompt_text = build_prompt(
        state,
        ["feature_summary", "distribution_analysis", "feature_relation"],
        candidate_criteria="redundancy",
    )
    candidate_lines = [
        line
        for line in _extract_section(prompt_text, "ADDITIONAL_CANDIDATES").splitlines()
        if line.startswith("-")
    ]

    assert len(candidate_lines) <= 4
    assert any("Test dependency between" in line for line in candidate_lines)
    assert any("f_other_" in line for line in candidate_lines)


def test_prompt_renders_next_step_guardrails_and_resets_previous_hypothesis():
    summaries = {
        "f_dep_a": {
            "unique_values": 10,
            "cardinality_ratio": 0.2,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_dep_b", "correlation": 0.99}],
        },
        "f_dep_b": {
            "unique_values": 10,
            "cardinality_ratio": 0.2,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_dep_a", "correlation": 0.99},
                {"feature": "f_dep_c", "correlation": 0.97},
            ],
        },
        "f_dep_c": {
            "unique_values": 10,
            "cardinality_ratio": 0.22,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_dep_b", "correlation": 0.97}],
        },
        "f_skew": {
            "unique_values": 20,
            "cardinality_ratio": 0.3,
            "skewness": 6.0,
            "redundancy": [],
        },
    }
    state = init_state(
        run_id="guardrails_prompt",
        objective="test",
        max_steps=4,
        available_features=list(summaries),
        metadata={
            "compact_feature_index": summaries,
            "last_hypothesis": "Dependency cluster still looks promising.",
            "hypothesis_revision_count": 3,
        },
    )
    state.history.extend(
        [
            {"step_id": 1, "action": "feature_relation", "execution_status": "OK"},
            {"step_id": 2, "action": "feature_relation", "execution_status": "OK"},
        ]
    )
    add_evidence(
        state,
        "f_dep_a|f_dep_b",
        EvidenceBlock(
            feature="f_dep_a|f_dep_b",
            signals=["high_redundancy"],
            metrics={"correlation": 0.99},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_dep_b|f_dep_c",
        EvidenceBlock(
            feature="f_dep_b|f_dep_c",
            signals=["high_redundancy"],
            metrics={"correlation": 0.97},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 2},
            status="active",
        ),
    )

    prompt_text = build_prompt(
        state,
        ["feature_relation", "distribution_analysis", "cardinality_analysis"],
        candidate_criteria="redundancy",
    )
    guardrails = _extract_section(prompt_text, "NEXT_STEP_GUARDRAILS")
    previous = _extract_section(prompt_text, "PREVIOUS_HYPOTHESIS")

    assert "- recent_focus=dependency" in guardrails
    assert "- recent_streak=2" in guardrails
    assert "switch mechanism unless contradiction or stronger unresolved evidence exists" in guardrails
    assert "Current dependency line of inquiry already has local support" in previous
    assert "Seek orthogonal evidence next" in previous


def test_recent_cooldown_keeps_cross_mechanism_candidates_visible():
    summaries = {
        "f_dep_a": {
            "unique_values": 10,
            "cardinality_ratio": 0.2,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_dep_b", "correlation": 0.99}],
        },
        "f_dep_b": {
            "unique_values": 10,
            "cardinality_ratio": 0.22,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_dep_a", "correlation": 0.99},
                {"feature": "f_dep_c", "correlation": 0.97},
            ],
        },
        "f_dep_c": {
            "unique_values": 10,
            "cardinality_ratio": 0.24,
            "skewness": 0.1,
            "redundancy": [{"feature": "f_dep_b", "correlation": 0.97}],
        },
        "f_skew": {
            "unique_values": 20,
            "cardinality_ratio": 0.4,
            "skewness": 5.4,
            "redundancy": [],
        },
    }
    state = init_state(
        run_id="recent_cooldown_candidates",
        objective="test",
        max_steps=4,
        available_features=list(summaries),
        metadata={"compact_feature_index": summaries},
    )
    state.history.extend(
        [
            {"step_id": 1, "action": "feature_relation", "execution_status": "OK"},
            {"step_id": 2, "action": "feature_relation", "execution_status": "OK"},
        ]
    )
    add_evidence(
        state,
        "f_dep_a|f_dep_b",
        EvidenceBlock(
            feature="f_dep_a|f_dep_b",
            signals=["high_redundancy"],
            metrics={"correlation": 0.99},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_dep_b|f_dep_c",
        EvidenceBlock(
            feature="f_dep_b|f_dep_c",
            signals=["high_redundancy"],
            metrics={"correlation": 0.97},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 2},
            status="active",
        ),
    )

    prompt_text = build_prompt(
        state,
        ["feature_relation", "distribution_analysis", "cardinality_analysis"],
        candidate_criteria="redundancy",
    )
    candidate_lines = [
        line
        for line in _extract_section(prompt_text, "ADDITIONAL_CANDIDATES").splitlines()
        if line.startswith("-")
    ]

    assert "f_skew" in candidate_lines[0]
    assert any("f_dep_" in line for line in candidate_lines)


def test_stronger_dependency_candidate_overrides_component_penalty():
    summaries = {
        "f_comp_a": {
            "unique_values": 10,
            "cardinality_ratio": 0.2,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_comp_b", "correlation": 0.96},
                {"feature": "f_comp_c", "correlation": 0.97},
            ],
        },
        "f_comp_b": {
            "unique_values": 10,
            "cardinality_ratio": 0.22,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_comp_a", "correlation": 0.96},
                {"feature": "f_comp_c", "correlation": 1.0},
            ],
        },
        "f_comp_c": {
            "unique_values": 10,
            "cardinality_ratio": 0.24,
            "skewness": 0.1,
            "redundancy": [
                {"feature": "f_comp_a", "correlation": 0.97},
                {"feature": "f_comp_b", "correlation": 1.0},
            ],
        },
    }
    state = init_state(
        run_id="component_override",
        objective="test",
        max_steps=3,
        available_features=list(summaries),
        metadata={"compact_feature_index": summaries},
    )
    add_evidence(
        state,
        "f_comp_a|f_comp_b",
        EvidenceBlock(
            feature="f_comp_a|f_comp_b",
            signals=["high_redundancy"],
            metrics={"correlation": 0.96},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 1},
            status="active",
        ),
    )
    add_evidence(
        state,
        "f_comp_a|f_comp_c",
        EvidenceBlock(
            feature="f_comp_a|f_comp_c",
            signals=["high_redundancy"],
            metrics={"correlation": 0.97},
            support={"total_samples": 10},
            provenance={"tool": "feature_relation", "step": 2},
            status="active",
        ),
    )

    component_by_feature = _build_redundancy_components(summaries)
    component_stats = _get_component_exploration(state, component_by_feature)

    assert _get_candidate_component_penalty(
        "f_comp_b",
        summaries["f_comp_b"],
        "redundancy",
        state,
        component_by_feature,
        component_stats,
    ) == 0


def test_known_facts_render_and_filter_same_mechanism_candidates():
    summaries = {
        "f_constant": {
            "unique_values": 1,
            "cardinality_ratio": 0.01,
            "skewness": 0.0,
            "redundancy": [],
        },
        "f_entropy": {
            "signals": ["low_entropy"],
            "unique_values": 5,
            "cardinality_ratio": 0.05,
            "skewness": 0.1,
            "redundancy": [],
        },
        "f_other": {
            "unique_values": 2,
            "cardinality_ratio": 0.02,
            "skewness": 0.2,
            "redundancy": [],
        },
    }
    state = init_state(
        run_id="known_facts_prompt",
        objective="test",
        max_steps=1,
        available_features=list(summaries),
        metadata={"compact_feature_index": summaries},
    )

    prompt_text = build_prompt(
        state,
        ["feature_summary", "cardinality_analysis",
            "distribution_analysis", "feature_relation"],
        candidate_criteria="low cardinality",
    )
    known_facts_section = _extract_section(prompt_text, "KNOWN_FACTS")
    candidates_section = _extract_section(prompt_text, "ADDITIONAL_CANDIDATES")

    assert "constant / near-constant behavior" in known_facts_section
    assert "dominant-value / low-entropy behavior" in known_facts_section
    assert "f_constant" in known_facts_section
    assert "f_entropy" in known_facts_section
    assert "feature_relation" not in known_facts_section
    assert "f_constant" not in candidates_section
    assert "f_other" in candidates_section


def test_available_features_are_gated_after_evidence_exists():
    state = init_state(
        run_id="available_features_gate",
        objective="test",
        max_steps=2,
        available_features=["f_focus", "f_aux", "f_other", "f_extra"],
    )
    add_evidence(
        state,
        "f_focus",
        EvidenceBlock(
            feature="f_focus",
            signals=["low_cardinality"],
            metrics={"cardinality_ratio": 0.02},
            support={"total_samples": 10},
            provenance={"tool": "cardinality_analysis", "step": 1},
            status="active",
        ),
    )

    prompt_text = build_prompt(state, ["cardinality_analysis"])
    available_section = _extract_section(prompt_text, "AVAILABLE_FEATURES")

    assert "4 total features." in available_section
    assert "Context examples:" in available_section
    assert "f_focus" in available_section
    assert "f_focus, f_aux, f_other, f_extra" not in available_section


def test_known_facts_block_is_present_in_prompt_section_order():
    state = init_state(
        run_id="known_facts_order",
        objective="test",
        max_steps=1,
        available_features=["f1"],
        metadata={
            "compact_feature_index": {
                "f1": {
                    "unique_values": 1,
                    "cardinality_ratio": 0.01,
                    "skewness": 0.0,
                    "redundancy": [],
                }
            }
        },
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert "KNOWN_FACTS:\n" in prompt_text
    assert prompt_text.index(
        "OVERVIEW:\n") < prompt_text.index("KNOWN_FACTS:\n")
    assert prompt_text.index(
        "KNOWN_FACTS:\n") < prompt_text.index("AVAILABLE_TOOLS:\n")
