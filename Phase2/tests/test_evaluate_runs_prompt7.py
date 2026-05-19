import json
from pathlib import Path

from experiments.evaluate_runs import evaluate_runs


def write_run(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_evaluate_runs_includes_reasoning_and_baselines(tmp_path):
    good = {
        "run_id": "good",
        "history": [],
        "analyzed_features": {"f1": {"correlation": 0.4, "wasserstein": 0.3, "tools_used": ["a", "b"]}},
        "promising_features": ["f1"],
        "metadata": {"hypothesis_history": [{"step": 0, "hypothesis": "f1 is shortcut"}, {"step": 2, "hypothesis": "f2 now suspicious"}]},
        "contradiction_memory": [{"feature": "f1", "evidence_refs": [0], "reason": "conflict"}],
        "overview_usage": 1,
    }
    bad = {
        "run_id": "bad",
        "history": [],
        "analyzed_features": {"f1": {"correlation": 0.05, "wasserstein": 0.01, "tools_used": ["a"]}},
        "promising_features": [],
        "metadata": {"hypothesis_history": [{"step": 0, "hypothesis": "f1 is shortcut"}]},
        "contradiction_memory": [],
        "overview_usage": 3,
    }

    p1 = write_run(tmp_path, "run_good.json", good)
    p2 = write_run(tmp_path, "run_bad.json", bad)

    result = evaluate_runs([p1, p2], latest=2)
    agg = result.get("aggregate", {})
    assert "reasoning_components_summary" in agg
    rsum = agg["reasoning_components_summary"]
    assert "avg_shannon_entropy" in rsum
    # Baselines attached per run
    runs = result.get("runs", [])
    assert any(r.get("baselines") for r in runs)
