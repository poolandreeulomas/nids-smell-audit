import json

from judge.judge_runner import merge_jif_payloads, run_judge


def test_merge_jif_payloads_sums_existing_aggregate_fields_only():
    left = {
        "header": {"schema_version": "jif.v2", "run_count": 1, "source_run_ids": ["r1"], "source_artifacts": ["j1.json"]},
        "cohort_context": {
            "objective_frequency": {"audit": 1},
            "dataset_frequency": {"a.csv": 1},
            "model_name_frequency": {"m1": 1},
            "model_version_frequency": {"unknown": 1},
            "max_steps_frequency": {"10": 1},
            "tool_set": ["feature_summary"],
        },
        "aggregate": {
            "run_count": 1,
            "total_steps": 3,
            "tool_frequency": {"feature_summary": 2},
            "step_type_frequency": {"exploration": 2},
            "redundant_step_frequency": {"false": 3},
            "signal_frequency": {"low_variance": 1},
        },
        "run_cards": [{"run_id": "r1"}],
    }
    right = {
        "header": {"schema_version": "jif.v2", "run_count": 2, "source_run_ids": ["r2", "r3"], "source_artifacts": ["j2.json", "j3.json"]},
        "cohort_context": {
            "objective_frequency": {"audit": 2},
            "dataset_frequency": {"a.csv": 1, "b.csv": 1},
            "model_name_frequency": {"m1": 2},
            "model_version_frequency": {"unknown": 2},
            "max_steps_frequency": {"10": 2},
            "tool_set": ["distribution_analysis"],
        },
        "aggregate": {
            "run_count": 2,
            "total_steps": 7,
            "tool_frequency": {"distribution_analysis": 4},
            "step_type_frequency": {"confirmation": 3},
            "redundant_step_frequency": {"false": 6, "true": 1},
            "signal_frequency": {"dominant_value": 2},
        },
        "run_cards": [{"run_id": "r2"}, {"run_id": "r3"}],
    }

    merged = merge_jif_payloads([left, right])

    assert merged["aggregate"]["run_count"] == 3
    assert merged["aggregate"]["total_steps"] == 10
    assert merged["aggregate"]["tool_frequency"] == {
        "distribution_analysis": 4,
        "feature_summary": 2,
    }
    assert len(merged["run_cards"]) == 3


def test_run_judge_saves_structured_and_text_artifacts(tmp_path):
    payload = {
        "header": {"schema_version": "jif.v2", "run_count": 1, "source_run_ids": ["r1"], "source_artifacts": ["r1.json"], "export_scope": {"selection_mode": "explicit_paths", "selection_value": 1}},
        "cohort_context": {
            "objective_frequency": {"audit": 1},
            "dataset_frequency": {"a.csv": 1},
            "model_name_frequency": {"m1": 1},
            "model_version_frequency": {"unknown": 1},
            "max_steps_frequency": {"10": 1},
            "tool_set": ["feature_summary"],
        },
        "aggregate": {
            "run_count": 1,
            "total_steps": 2,
            "tool_frequency": {"feature_summary": 1},
            "step_type_frequency": {"exploration": 1, "confirmation": 1},
            "redundant_step_frequency": {"false": 2},
            "signal_frequency": {"low_variance": 1},
        },
        "run_cards": [
            {
                "run_id": "r1",
                "artifact_name": "r1.json",
                "objective": "audit",
                "dataset": {"path_basename": "a.csv", "path_hash": "h1"},
                "model": {"name": "m1", "version": "unknown"},
                "limits": {"max_steps": 10},
                "run_counts": {"total_steps": 2, "error_steps": 0, "contradiction_count": 0, "target_card_count": 1},
                "tool_frequency": {"feature_summary": 1},
                "step_type_frequency": {"exploration": 1, "confirmation": 1},
                "signal_frequency": {"low_variance": 1},
                "step_trace": [],
                "feature_cards": [],
                "contradictions": [],
                "errors": [],
            }
        ],
    }
    llm_response = json.dumps(
        {
            "behavior_summary": "The run shows a short exploration-confirmation sequence with no recorded redundancy.",
            "key_patterns": [
                {
                    "statement": "The run includes both exploration and confirmation steps.",
                    "evidence": ["aggregate.step_type_frequency", "run_cards.step_trace"],
                    "confidence": "high",
                }
            ],
            "weaknesses": [],
            "strengths": [
                {
                    "statement": "The run avoids redundant steps.",
                    "evidence": ["aggregate.redundant_step_frequency"],
                    "confidence": "medium",
                }
            ],
            "recommendations": [],
        }
    )

    result = run_judge(
        payload,
        model_name="gpt-4.1",
        mode="single_run",
        llm_callable=lambda prompt_text: llm_response,
        output_dir=tmp_path,
        prefix="judge_unit",
    )

    assert result["mode"] == "single_run"
    assert result["report"]["strengths"][0]["evidence"] == [
        "aggregate.redundant_step_frequency"]
    assert len(list(tmp_path.glob("judge_unit_*.json"))) == 1
    assert len(list(tmp_path.glob("judge_unit_*.txt"))) == 1
