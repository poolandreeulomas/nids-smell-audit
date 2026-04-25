from interface.cli import NidsAgentCli, RunContext


def test_build_feature_reviews_scores_english_levels():
    cli = object.__new__(NidsAgentCli)
    run_context = RunContext(
        artifact_paths={"run_log_path": "run.json",
                        "metrics_log_path": "run_metrics.json"},
        run_payload={"history": [],
                     "contradiction_memory": [], "metadata": {}},
        metrics={},
        insights={
            "feature_evidence": {
                "Flow Duration": {
                    "signals": ["high_class_separation"],
                    "metrics": {"js_divergence": 0.81},
                    "support": {},
                    "status": "active",
                    "tools_used": ["distribution_analysis"],
                    "anchor_count": 1,
                }
            },
            "errors": [],
        },
    )

    reviews = cli._build_feature_reviews(run_context)

    assert reviews[0]["level"] == "medium"
    assert reviews[0]["score"] == 2
