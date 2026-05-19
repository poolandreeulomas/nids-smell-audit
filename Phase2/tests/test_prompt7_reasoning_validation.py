from analysis import interpreter, scoring


def composite_reasoning_score(rc: dict) -> float:
    # rc is the reasoning_components dict from scoring.score_run
    hr = rc.get("hypothesis_revision", {}).get(
        "beneficial_revision_ratio", 0.0)
    ce = rc.get("counterevidence_usage", {}).get("acted_ratio", 0.0)
    od = rc.get("overview_dependence", {}).get("overview_dependence", 0.0)
    ent = rc.get("exploration_diversity", {}).get("shannon_entropy", 0.0)
    eff = rc.get("evidence_efficiency", {}).get("evidence_efficiency", 0.0)

    # normalize entropy (assume max ~3.0 for small sets) and efficiency into [0,1]
    ent_n = min(ent / 3.0, 1.0)
    eff_n = min(eff * 10.0, 1.0)

    # higher is better for hr, ce, ent_n, eff_n; lower is better for od
    return hr + ce + (1.0 - od) + ent_n + eff_n


def test_reasoning_quality_distinguishes_good_and_bad():
    # Good run: multiple beneficial hypothesis revisions, reacts to counterevidence,
    # broad exploration and good evidence per call.
    good = {
        "history": [
            {"action": "feature_summary", "action_input": {
                "feature_name": "f1"}, "execution_status": "OK"},
            {"action": "distribution_analysis", "action_input": {
                "feature_name": "f2"}, "execution_status": "OK"},
        ],
        "analyzed_features": {
            "f1": {"correlation": 0.4, "wasserstein": 0.3, "tools_used": ["a", "b"]},
            "f2": {"correlation": 0.25, "wasserstein": 0.15, "tools_used": ["b"]},
        },
        "promising_features": ["f1"],
        "metadata": {"hypothesis_history": [{"step": 0, "hypothesis": "f1 shortcut"}, {"step": 1, "hypothesis": "f2 suspicious"}]},
        "contradiction_memory": [{"feature": "f2", "evidence_refs": [0], "reason": "counter"}],
        "overview_usage": 0,
    }

    # Bad run: no revisions, ignores counterevidence, narrow exploration, weak evidence
    bad = {
        "history": [
            {"action": "feature_summary", "action_input": {
                "feature_name": "f1"}, "execution_status": "OK"},
        ],
        "analyzed_features": {
            "f1": {"correlation": 0.02, "wasserstein": 0.01, "tools_used": ["a"]},
        },
        "promising_features": [],
        "metadata": {"hypothesis_history": [{"step": 0, "hypothesis": "f1 shortcut"}]},
        "contradiction_memory": [],
        "overview_usage": 2,
    }

    ins_good = interpreter.extract_run_insights(good)
    ins_bad = interpreter.extract_run_insights(bad)

    sc_good = scoring.score_run(ins_good)
    sc_bad = scoring.score_run(ins_bad)

    rc_good = sc_good.get("reasoning_components", {})
    rc_bad = sc_bad.get("reasoning_components", {})

    comp_good = composite_reasoning_score(rc_good)
    comp_bad = composite_reasoning_score(rc_bad)

    assert comp_good > comp_bad, f"Expected good ({comp_good}) > bad ({comp_bad})"
