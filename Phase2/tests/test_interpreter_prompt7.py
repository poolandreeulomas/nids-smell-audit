from analysis import interpreter


def test_interpreter_instruments_prompt7_fields():
    run = {
        "history": [
            {"action": "feature_summary", "action_input": {
                "feature_name": "f1"}, "execution_status": "OK"},
            {"action": "distribution_analysis", "action_input": {
                "feature_name": "f2"}, "execution_status": "OK"},
            {"action": "feature_summary", "action_input": {"feature_name": "f1"},
                "execution_status": "TOOL_ERROR", "observation": {"error_code": "E1"}},
        ],
        "analyzed_features": {
            "f1": {"correlation": 0.4, "wasserstein": 0.2, "tools_used": ["feature_summary"]},
            "f2": {"correlation": 0.1, "wasserstein": 0.05, "tools_used": ["distribution_analysis"]},
        },
        "promising_features": ["f1", "f2"],
        "contradiction_memory": [{"feature": "f1", "evidence_refs": [0], "reason": "conflict"}],
        "metadata": {"hypothesis_history": [{"step": 0, "hypothesis": "f1 is a shortcut"}]},
    }

    insights = interpreter.extract_run_insights(run)
    assert "events" in insights
    assert insights["counterevidence"]["seen"] == 1
    assert insights["counterevidence"]["acted"] == 1
    assert insights["overview_usage"] == 0
    assert insights["feature_accesses"] == ["f1", "f2", "f1"]
    assert insights["evidence_signals"] > 0
    assert insights["tool_calls"] == 3
