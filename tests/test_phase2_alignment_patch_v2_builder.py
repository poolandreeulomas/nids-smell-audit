import os

from prompts.builder import build_prompt
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
