import json

from judge.judge_runner import (
    build_judge_prompt,
    merge_jif_payloads,
    run_judge,
    _resolve_partition_analysis_mode,
)


def _build_judge_payload(*dataset_basenames: str | None) -> dict[str, object]:
    run_cards = []
    dataset_frequency = {}

    for index, dataset_basename in enumerate(dataset_basenames, start=1):
        run_id = f"r{index}"
        artifact_name = f"{run_id}.json"
        dataset = {"path_hash": f"h{index}"}
        if dataset_basename is not None:
            dataset["path_basename"] = dataset_basename
            dataset_frequency[dataset_basename] = dataset_frequency.get(
                dataset_basename, 0
            ) + 1
        run_cards.append(
            {
                "run_id": run_id,
                "artifact_name": artifact_name,
                "objective": "audit",
                "dataset": dataset,
                "model": {"name": "m1", "version": "unknown"},
                "limits": {"max_steps": 10},
                "run_counts": {
                    "total_steps": 2,
                    "error_steps": 0,
                    "contradiction_count": 0,
                    "target_card_count": 1,
                },
                "tool_frequency": {"feature_summary": 1},
                "step_type_frequency": {"exploration": 1, "confirmation": 1},
                "signal_frequency": {"low_variance": 1},
                "step_trace": [],
                "feature_cards": [],
                "contradictions": [],
                "errors": [],
            }
        )

    return {
        "header": {
            "schema_version": "jif.v2",
            "run_count": len(run_cards),
            "source_run_ids": [card["run_id"] for card in run_cards],
            "source_artifacts": [card["artifact_name"] for card in run_cards],
            "export_scope": {"selection_mode": "explicit_paths", "selection_value": len(run_cards)},
        },
        "cohort_context": {
            "objective_frequency": {"audit": len(run_cards)},
            "dataset_frequency": dataset_frequency,
            "model_name_frequency": {"m1": len(run_cards)},
            "model_version_frequency": {"unknown": len(run_cards)},
            "max_steps_frequency": {"10": len(run_cards)},
            "tool_set": ["feature_summary"],
        },
        "aggregate": {
            "run_count": len(run_cards),
            "total_steps": len(run_cards) * 2,
            "tool_frequency": {"feature_summary": len(run_cards)},
            "step_type_frequency": {
                "exploration": len(run_cards),
                "confirmation": len(run_cards),
            },
            "redundant_step_frequency": {"false": len(run_cards) * 2},
            "signal_frequency": {"low_variance": len(run_cards)},
        },
        "run_cards": run_cards,
    }


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


def test_build_judge_prompt_injects_exactly_one_context_block():
    payload = _build_judge_payload(
        "Friday-WorkingHours-Afternoon-PortScan.csv")

    prompt = build_judge_prompt(payload, "single_run")

    assert prompt.count("=== CONTEXT: DATASET PHENOMENON ===") == 1
    assert prompt.count("=== CONTEXT: EXPECTED STRUCTURE ===") == 1
    assert prompt.count("=== CONTEXT: EVALUATION LENS ===") == 1
    assert "scanning behavior with high repetition" in prompt
    assert "repeated login attempts and structured repetition" not in prompt
    assert "Use the injected context only to interpret behavior" in prompt
    assert prompt.index("You are an evaluator of agent reasoning behavior.") < prompt.index(
        "=== CONTEXT: DATASET PHENOMENON ===")
    assert prompt.index(
        "=== CONTEXT: DATASET PHENOMENON ===") < prompt.index("JIF payload:")
    assert prompt.index("JIF payload:") < prompt.index("Output rules:")


def test_resolve_partition_analysis_mode_ignores_unknown_runs():
    payload = _build_judge_payload(
        "Wednesday-WorkingHours-DDos.csv",
        "mystery_partition.csv",
    )

    assert _resolve_partition_analysis_mode(payload) == "single_partition"


def test_resolve_partition_analysis_mode_detects_cross_partition_from_valid_runs_only():
    payload = _build_judge_payload(
        "Wednesday-WorkingHours-DDos.csv",
        "Friday-WorkingHours-Afternoon-PortScan.csv",
        "mystery_partition.csv",
    )

    assert _resolve_partition_analysis_mode(payload) == "cross_partition"


def test_build_judge_prompt_uses_single_partition_context_for_same_phenomenon_multi_run():
    payload = _build_judge_payload(
        "Wednesday-WorkingHours-DDos.csv",
        "Friday-WorkingHours-Afternoon-DDos.csv",
    )

    prompt = build_judge_prompt(payload, "multi_run")

    assert "=== CONTEXT: DATASET PHENOMENON ===" in prompt
    assert "=== CROSS-PARTITION ANALYSIS INSTRUCTIONS ===" not in prompt
    assert "saturation, spikes, and load" in prompt
    assert "Analysis mode:\nsingle_partition" in prompt


def test_build_judge_prompt_uses_cross_partition_block_without_context_sections():
    payload = _build_judge_payload(
        "Wednesday-WorkingHours-DDos.csv",
        "Friday-WorkingHours-Afternoon-PortScan.csv",
    )

    prompt = build_judge_prompt(payload, "multi_run")

    assert "=== CROSS-PARTITION ANALYSIS INSTRUCTIONS ===" in prompt
    assert "Anchor claims to specific runs in the JIF payload" in prompt
    assert "Final evidence references must still use only the allowed field-level references" in prompt
    assert "=== CONTEXT: DATASET PHENOMENON ===" not in prompt
    assert "=== CONTEXT: EXPECTED STRUCTURE ===" not in prompt
    assert "=== CONTEXT: EVALUATION LENS ===" not in prompt
    assert "Analysis mode:\ncross_partition" in prompt
    assert prompt.index("=== CROSS-PARTITION ANALYSIS INSTRUCTIONS ===") < prompt.index(
        "JIF payload:"
    )
    assert prompt.index("JIF payload:") < prompt.index("Output rules:")
