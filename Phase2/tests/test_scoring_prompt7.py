from analysis import scoring


def test_reasoning_components_and_baselines():
    insights_good = {
        "behavior": {"num_steps": 6},
        "patterns": {"confirmed_features": ["f1", "f2"]},
        "events": [
            {"type": "hypothesis", "action": "create", "beneficial": True},
            {"type": "hypothesis", "action": "update", "beneficial": True},
            {"type": "hypothesis", "action": "update", "beneficial": False},
        ],
        "counterevidence": {"seen": 2, "acted": 2},
        "overview_usage": 1,
        "feature_accesses": ["f1", "f2", "f1", "f3"],
        "evidence_signals": 3.5,
        "tool_calls": 4,
    }

    insights_bad = {
        "behavior": {"num_steps": 6},
        "patterns": {"confirmed_features": []},
        "events": [
            {"type": "hypothesis", "action": "create", "beneficial": False},
        ],
        "counterevidence": {"seen": 2, "acted": 0},
        "overview_usage": 4,
        "feature_accesses": ["f1", "f1", "f1"],
        "evidence_signals": 0.5,
        "tool_calls": 5,
    }

    res_good = scoring.score_run(insights_good)
    res_bad = scoring.score_run(insights_bad)

    # Ensure new reasoning components are present
    assert "reasoning_components" in res_good
    rc_good = res_good["reasoning_components"]
    rc_bad = res_bad["reasoning_components"]

    # Hypothesis revision measured
    assert rc_good["hypothesis_revision"]["total_revisions"] == 3.0
    assert rc_good["hypothesis_revision"]["beneficial_revisions"] == 2.0

    # Counterevidence usage shows acted ratio higher for good run
    assert rc_good["counterevidence_usage"]["acted_ratio"] > rc_bad["counterevidence_usage"]["acted_ratio"]

    # Exploration diversity: good run should have higher entropy
    assert rc_good["exploration_diversity"]["shannon_entropy"] > rc_bad["exploration_diversity"]["shannon_entropy"]

    # Evidence efficiency: good run should be higher
    assert rc_good["evidence_efficiency"]["evidence_efficiency"] > rc_bad["evidence_efficiency"]["evidence_efficiency"]

    # Baselines deterministic and seeded random
    b_det = scoring.baseline_deterministic(insights_good)
    b_rand_a = scoring.baseline_random(insights_good, seed=42, budget=4)
    b_rand_b = scoring.baseline_random(insights_good, seed=42, budget=4)
    assert b_det["baseline"] == "deterministic"
    assert b_rand_a == b_rand_b
