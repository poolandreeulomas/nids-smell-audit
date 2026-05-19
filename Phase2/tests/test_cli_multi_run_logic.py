from datetime import UTC, datetime

from interface import cli as cli_module
from interface.cli import NidsAgentCli, RunContext
from utils.run_logging import build_session_run_basename, get_next_run_index


def test_build_session_run_basename_has_visible_sequence():
    basename = build_session_run_basename(
        7,
        datetime(2026, 4, 30, tzinfo=UTC),
        partition_name="Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
        model_name="gpt-5.4-mini",
    )

    assert basename == "run_007_30-04_DS_5.4_mini"


def test_get_next_run_index_uses_highest_persisted_visible_sequence(tmp_path):
    (tmp_path / "run_001_30-04_DS_5.4.json").write_text("{}", encoding="utf-8")
    (tmp_path / "run_007_30-04_PS_5.4_mini.json").write_text("{}", encoding="utf-8")
    (tmp_path / "run_007_30-04_PS_5.4_mini_metrics.json").write_text("{}", encoding="utf-8")

    assert get_next_run_index(tmp_path) == 8


def test_build_multi_run_summary_payload_reuses_aggregated_results(monkeypatch):
    cli = object.__new__(NidsAgentCli)

    monkeypatch.setattr(
        cli_module,
        "evaluate_runs",
        lambda run_paths, latest: {
            "runs": [{"path": run_paths[1], "score": {"score": 88.0}}],
            "aggregate": {
                "run_metrics_summary": {
                    "steps": {"average": 4.5},
                    "features_attempted": {"average": 3.0},
                    "features_successful": {"average": 2.5},
                }
            },
        },
    )
    monkeypatch.setattr(
        cli_module,
        "compare_runs",
        lambda run_paths: {"average_overlap_score": 0.42},
    )

    run_contexts = [
        RunContext(
            artifact_paths={"run_log_path": "run_001.json",
                            "metrics_log_path": "run_001_metrics.json"},
            run_payload={
                "history": [
                    {"action": "feature_summary",
                        "action_input": {"feature_name": "f1"}},
                    {"action": "distribution_analysis",
                        "action_input": {"feature_name": "f2"}},
                ]
            },
            metrics={},
            insights={},
        ),
        RunContext(
            artifact_paths={"run_log_path": "run_002.json",
                            "metrics_log_path": "run_002_metrics.json"},
            run_payload={
                "history": [
                    {"action": "feature_summary",
                        "action_input": {"feature_name": "f1"}},
                    {"action": "feature_relation",
                        "action_input": {"feature_name": "f3"}},
                ]
            },
            metrics={},
            insights={},
        ),
    ]

    summary = cli._build_multi_run_summary_payload(run_contexts)

    assert ("runs", "2") in summary["metrics"]
    assert ("avg_steps", "4.5") in summary["metrics"]
    assert any(
        "feature_summary: 2 call(s) | 2/2 run(s)" in line for line in summary["tool_usage"])
    assert any(
        "unique features explored: 3" in line for line in summary["feature_summary"])
    assert any(
        "average overlap between runs: 0.42" in line for line in summary["consistency"])
