import os

from prompts.builder import (
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

    prompt_initial = build_prompt(state, ["feature_summary"])
    candidates_initial = _extract_section(
        prompt_initial, "ADDITIONAL_CANDIDATES")
    candidate_lines_initial = [
        line for line in candidates_initial.splitlines() if line.startswith("-")]

    assert any("cardinality_ratio=" in line for line in candidate_lines_initial)
    assert any("skewness=" in line for line in candidate_lines_initial)
    assert any("redundant_with=" in line for line in candidate_lines_initial)
    assert len(candidate_lines_initial) <= 10

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

    prompt_after = build_prompt(state, ["feature_summary"])
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
    assert prompt_text.index("GLOBAL_RULES:\n") < prompt_text.index(
        "PARTITION_CONTEXT:\n")
    assert prompt_text.index(
        "PARTITION_CONTEXT:\n") < prompt_text.index("OVERVIEW:\n")
    assert prompt_text.index("OVERVIEW:\n") < prompt_text.index(
        "INSTRUCTIONS (concise):\n")


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
    assert prompt_text.index(
        "PARTITION_CONTEXT:\n") < prompt_text.index("OVERVIEW:\n")


def test_prompt_includes_reasoning_rules():
    state = init_state(
        run_id="reasoning_rules",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert "REASONING_RULES:\n" in prompt_text
    assert "Do not re-confirm a fact in KNOWN_FACTS when the next action probes the same mechanism." in prompt_text
    assert "Do not repeat failed actions." in prompt_text
    assert "Seek new information." in prompt_text
    assert prompt_text.index("GLOBAL_RULES:\n") < prompt_text.index(
        "REASONING_RULES:\n"
    )
    assert prompt_text.index("REASONING_RULES:\n") < prompt_text.index(
        "PARTITION_CONTEXT:\n"
    )


def test_prompt_prioritizes_non_obvious_and_shared_pattern_rules():
    state = init_state(
        run_id="non_obvious_focus",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert "Treat already visible signals in the current context as background, not primary targets for repeated analysis." in prompt_text
    assert "Prefer investigating patterns that are not immediately apparent from the current context." in prompt_text
    assert "If a signal family appears across multiple features, treat it as a shared pattern and move on unless the next step adds a different type of information or tests a different mechanism." in prompt_text
    assert "`duplication_analysis` is dataset-level only." in prompt_text
    assert "For `feature_relation`, `ACTION_INPUT.feature_name` may be one valid feature or one exact pair written as `feature_a|feature_b`." in prompt_text
    assert prompt_text.index("DECISION_POLICY:\n") < prompt_text.index(
        "STRICT_OUTPUT_RULES:\n"
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
    assert candidate_lines[0].startswith("- f_skew1:")
    assert any("f_red1" in line for line in candidate_lines)


def test_prompt_is_single_purpose_and_removes_summary_generation_guidance():
    state = init_state(
        run_id="single_purpose_prompt",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )

    prompt_text = build_prompt(state, ["feature_summary"])

    assert (
        "Your task is ONLY to decide the next action. Do NOT generate summaries, reports, or multiple feature analyses."
        in prompt_text
    )
    assert "FEATURE_SUMMARIES" not in prompt_text
    assert "Keep each feature block compact" not in prompt_text
    assert "The overview should read as a working hypothesis" not in prompt_text
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

    assert 'ACTION_INPUT: {"feature_name": "f1"}' in recent_history
    assert "ACTION_INPUT: {'feature_name': 'f1'}" not in recent_history


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

    assert "- f_constant: constant from overview (mechanism=value_distribution)" in known_facts_section
    assert "- f_entropy: low_entropy from overview (mechanism=value_distribution)" in known_facts_section
    assert "feature_relation" not in known_facts_section
    assert "f_constant" not in candidates_section
    assert "f_other" in candidates_section


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
