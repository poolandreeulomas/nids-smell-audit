from interface.terminal_ui import (
    render_feature_analysis,
    render_multi_run_summary,
    render_reasoning_trace,
    render_run_review,
)


def test_render_reasoning_trace_is_human_readable():
    history = [
        {
            "step_id": 1,
            "thought": "Hypothesis: Flow Duration may be a shortcut.",
            "action": "distribution_analysis",
            "action_input": {"feature_name": "Flow Duration"},
            "observation": {
                "ok": True,
                "value": 0.81,
                "evidence": {
                    "signals": ["high_class_separation"],
                    "metrics": {"js_divergence": 0.81},
                },
            },
        }
    ]

    rendered = render_reasoning_trace(history, path_label="Trace")

    assert "STEP 01" in rendered
    assert "Hypothesis" in rendered
    assert "Action" in rendered
    assert "Observation" in rendered
    assert "distribution_analysis" in rendered
    assert "js_divergence=0.810" in rendered


def test_render_run_review_and_feature_analysis_show_risk_cards():
    items = [
        {
            "name": "Flow Duration",
            "level": "high",
            "where": "Flow Duration",
            "why": "The feature separates classes unusually well and may behave like a shortcut.",
            "context": "tools=distribution_analysis; signals=high_class_separation",
        }
    ]

    review = render_run_review(
        title="Run Review",
        run_name="run_1.json",
        intro_line="Run completed.",
        problems=items,
        llm_overview=[
            "The run used two tools and converged on one suspicious feature."],
    )
    feature_analysis = render_feature_analysis(items, path_label="Features")

    assert "Detected Issues" in review
    assert "LLM Overview" in review
    assert "Risk" in review
    assert "Feature Analysis" in feature_analysis
    assert "Context" in feature_analysis


def test_render_multi_run_summary_uses_existing_ui_structure():
    rendered = render_multi_run_summary(
        title="Multi-Run Summary",
        intro_line="Executed 3 runs.",
        metrics=[("runs", "3"), ("avg_steps", "4.3")],
        tool_usage=["- feature_summary: 6 call(s) | 3/3 run(s)"],
        feature_summary=["- unique features explored: 8"],
        consistency=["- average overlap between runs: 0.41"],
    )

    assert "Metrics" in rendered
    assert "Tool Usage" in rendered
    assert "Feature Exploration" in rendered
    assert "Consistency" in rendered
