import json

from experiments.export_jif import export_jif, save_jif_artifact


def write_run(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def assert_no_forbidden_keys(value):
    forbidden = {
        "executive_summary",
        "verdict",
        "verdict_counts",
        "score",
        "trust",
        "insight",
        "insights",
        "pattern",
        "patterns",
        "summary",
        "unstable",
        "recurring",
        "judge_notes_seed",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            assert key not in forbidden
            assert_no_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_forbidden_keys(child)


def test_export_jif_builds_neutral_compact_payload(tmp_path):
    run = {
        "run_id": "run_a",
        "objective": "Audit dataset",
        "max_steps": 5,
        "history": [
            {
                "step_id": 1,
                "action": "feature_summary",
                "action_input": {"feature_name": "f1"},
                "execution_status": "OK",
                "observation": {
                    "feature_name": "f1",
                    "evidence": {
                        "feature": "f1",
                        "signals": ["low_variance"],
                        "metrics": {
                            "variance": {"BENIGN": 0.0, "ATTACK": 0.0},
                            "unique_values": {"BENIGN": 1, "ATTACK": 1},
                        },
                        "support": {"total_samples": 10, "per_class": {"BENIGN": 5, "ATTACK": 5}},
                        "status": "active",
                    },
                },
            },
            {
                "step_id": 2,
                "action": "distribution_analysis",
                "action_input": {"feature_name": "f1"},
                "execution_status": "OK",
                "observation": {
                    "feature_name": "f1",
                    "evidence": {
                        "feature": "f1",
                        "signals": ["dominant_value"],
                        "metrics": {
                            "entropy": {"BENIGN": 0.1, "ATTACK": 0.1},
                            "js_divergence": 0.2,
                        },
                        "support": {"total_samples": 10, "per_class": {"BENIGN": 5, "ATTACK": 5}},
                        "status": "active",
                    },
                },
            },
            {
                "step_id": 3,
                "action": "distribution_analysis",
                "action_input": {"feature_name": "f1"},
                "execution_status": "OK",
                "observation": {
                    "feature_name": "f1",
                    "evidence": {
                        "feature": "f1",
                        "signals": ["dominant_value"],
                        "metrics": {
                            "entropy": {"BENIGN": 0.1, "ATTACK": 0.1},
                            "js_divergence": 0.2,
                        },
                        "support": {"total_samples": 10, "per_class": {"BENIGN": 5, "ATTACK": 5}},
                        "status": "weakened",
                    },
                },
            },
        ],
        "evidence_by_feature": {
            "f1": [
                {
                    "feature": "f1",
                    "signals": ["low_variance"],
                    "metrics": {
                        "variance": {"BENIGN": 0.0, "ATTACK": 0.0},
                        "unique_values": {"BENIGN": 1, "ATTACK": 1},
                    },
                    "support": {"total_samples": 10, "per_class": {"BENIGN": 5, "ATTACK": 5}},
                    "provenance": {"tool": "feature_summary", "step": 1},
                    "status": "active",
                },
                {
                    "feature": "f1",
                    "signals": ["dominant_value"],
                    "metrics": {
                        "entropy": {"BENIGN": 0.1, "ATTACK": 0.1},
                        "js_divergence": 0.2,
                    },
                    "support": {"total_samples": 10, "per_class": {"BENIGN": 5, "ATTACK": 5}},
                    "provenance": {"tool": "distribution_analysis", "step": 2},
                    "status": "weakened",
                },
            ]
        },
        "contradiction_memory": [
            {
                "feature": "f1",
                "reason": "Hypothesis revised from 'f1 is constant' to 'f1 may still carry shape effects'.",
                "evidence_refs": [],
                "step": 3,
                "evidence_snapshot": {"feature": "f1", "status": "weakened", "metrics": {"js_divergence": 0.2}},
            }
        ],
        "errors": [],
        "metadata": {
            "reproducibility": {
                "dataset_path": "C:/tmp/dataset.csv",
                "dataset_hash": "hash123",
                "model_name": "model-x",
            }
        },
    }
    result = export_jif([write_run(tmp_path, "run_a.json", run)],
                        exported_at="2026-04-24T18:40:00+00:00")

    assert set(result["aggregate"]) == {
        "run_count",
        "total_steps",
        "tool_frequency",
        "step_type_frequency",
        "redundant_step_frequency",
        "signal_frequency",
    }
    assert_no_forbidden_keys(result)

    run_card = result["run_cards"][0]
    third_step = run_card["step_trace"][2]
    assert third_step["redundant_step"] is True
    assert third_step["information_gain"] == "low"
    assert third_step["novelty_sources"] == {
        "new_signals": 0, "new_metrics": 0}
    assert third_step["key_result_short"] == "dominant_value"
    assert third_step["metric_anchors"] == {
        "entropy": 0.1, "js_divergence": 0.2}

    feature_card = run_card["feature_cards"][0]
    assert feature_card["metric_anchors"] == {
        "entropy": 0.1,
        "js_divergence": 0.2,
        "unique_values": 1.0,
        "variance": 0.0,
    }
    assert feature_card["support_variants"] == [
        {"class_count": 2, "total_samples": 10}]
    assert run_card["contradictions"][0]["from_hypothesis"] == "f1 is constant"
    assert run_card["contradictions"][0]["to_hypothesis"] == "f1 may still carry shape effects"


def test_export_jif_relation_steps_are_canonicalized_and_redundancy_is_consistent(tmp_path):
    run = {
        "run_id": "run_pair",
        "objective": "Audit dataset",
        "max_steps": 3,
        "history": [
            {
                "step_id": 1,
                "action": "feature_relation",
                "action_input": {"feature_name": "f2"},
                "execution_status": "OK",
                "observation": {
                    "feature_name": "f2|f1",
                    "evidence": {
                        "feature": "f2|f1",
                        "signals": ["high_redundancy"],
                        "metrics": {"correlation": 1.0},
                        "status": "active",
                    },
                },
            },
            {
                "step_id": 2,
                "action": "feature_relation",
                "action_input": {"feature_name": "f1"},
                "execution_status": "OK",
                "observation": {
                    "feature_name": "f1|f2",
                    "evidence": {
                        "feature": "f1|f2",
                        "signals": ["high_redundancy"],
                        "metrics": {"correlation": 1.0},
                        "status": "active",
                    },
                },
            },
        ],
        "evidence_by_feature": {
            "f2|f1": [
                {
                    "feature": "f2|f1",
                    "signals": ["high_redundancy"],
                    "metrics": {"correlation": 1.0},
                    "support": {"total_samples": 10},
                    "provenance": {"tool": "feature_relation", "step": 1},
                    "status": "active",
                }
            ]
        },
    }
    result = export_jif([write_run(tmp_path, "run_pair.json", run)],
                        exported_at="2026-04-24T18:40:00+00:00")

    steps = result["run_cards"][0]["step_trace"]
    assert steps[0]["target_key"] == "f1|f2"
    assert steps[0]["step_type"] == "relation"
    assert steps[1]["target_key"] == "f1|f2"
    assert steps[1]["step_type"] == "relation"
    assert steps[1]["redundant_step"] is True
    assert steps[1]["information_gain"] == "low"


def test_export_jif_is_deterministic_with_fixed_timestamp(tmp_path):
    run = {
        "run_id": "run_det",
        "objective": "Audit dataset",
        "max_steps": 1,
        "history": [
            {
                "step_id": 1,
                "action": "cardinality_analysis",
                "action_input": {"feature_name": "f1"},
                "execution_status": "OK",
                "observation": {
                    "feature_name": "f1",
                    "evidence": {
                        "feature": "f1",
                        "signals": ["low_cardinality"],
                        "metrics": {"cardinality_ratio": 0.01},
                        "status": "active",
                    },
                },
            }
        ],
        "evidence_by_feature": {},
    }
    run_path = write_run(tmp_path, "run_det.json", run)

    first = export_jif([run_path], exported_at="2026-04-24T18:40:00+00:00")
    second = export_jif([run_path], exported_at="2026-04-24T18:40:00+00:00")

    assert first == second


def test_save_jif_artifact_writes_json(tmp_path):
    payload = {
        "header": {"schema_version": "jif.v2"},
        "cohort_context": {},
        "aggregate": {},
        "run_cards": [],
    }

    artifact_paths = save_jif_artifact(
        payload, output_dir=tmp_path, prefix="unit_jif")
    saved_path = tmp_path / next(iter(tmp_path.iterdir())).name

    assert saved_path.name.startswith("unit_jif_")
    assert json.loads(saved_path.read_text(encoding="utf-8")) == payload
    assert artifact_paths["jif_json_path"] == str(saved_path)
