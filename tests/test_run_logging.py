from pathlib import Path

from state.store import append_history, init_state, merge_metadata
from utils.run_logging import build_debug_log_text, save_run_artifacts


def test_build_debug_log_text_includes_partition_prompt_response_and_tool_result():
    state = init_state(
        run_id="debug_log_case",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )
    merge_metadata(
        state,
        {
            "reproducibility": {
                "model_name": "gpt-5.4-mini",
                "dataset_snapshot": {"path": "Monday-WorkingHours.csv"},
            }
        },
    )
    append_history(
        state,
        {
            "step_id": 1,
            "execution_status": "OK",
            "action": "cardinality_analysis",
            "action_input": {"feature_name": "f1"},
            "prompt_snapshot": "OBJECTIVE:\nPROMPT BODY\n\nKNOWN_FACTS:\n- fact one\n\nADDITIONAL_CANDIDATES:\n- candidate one",
            "raw_model_output": "THOUGHT: ...\nACTION: cardinality_analysis\nACTION_INPUT: {\"feature_name\": \"f1\"}",
            "observation": {
                "ok": True,
                "tool": "cardinality_analysis",
                "feature_name": "f1",
                "value": 0.5,
                "error_code": None,
                "error_message": None,
                "meta": {"ignored": "value"},
            },
        },
    )

    text = build_debug_log_text(state)

    assert "Partition: Monday-WorkingHours.csv" in text
    assert "Model: gpt-5.4-mini" in text
    assert "## Step 1 | OK" in text
    assert "PROMPT BODY" in text
    assert "Prompt Sections: OBJECTIVE, KNOWN_FACTS, ADDITIONAL_CANDIDATES" in text
    assert "Section Lengths: OBJECTIVE=" in text
    assert "KNOWN_FACTS=" in text
    assert "ADDITIONAL_CANDIDATES=" in text
    assert "ACTION: cardinality_analysis" in text
    assert '"tool": "cardinality_analysis"' in text
    assert '"feature_name": "f1"' in text
    assert '"value": 0.5' in text
    assert "ignored" not in text


def test_save_run_artifacts_writes_debug_log(tmp_path: Path):
    state = init_state(
        run_id="debug_artifact_case",
        objective="test",
        max_steps=1,
        available_features=["f1"],
    )
    merge_metadata(
        state,
        {
            "reproducibility": {
                "model_name": "gpt-5.4-mini",
                "dataset_snapshot": {"path": "Monday-WorkingHours.csv"},
            }
        },
    )
    append_history(
        state,
        {
            "step_id": 1,
            "execution_status": "OK",
            "action": "feature_summary",
            "action_input": {"feature_name": "f1"},
            "prompt_snapshot": "OBJECTIVE:\nPROMPT BODY\n\nRECENT_HISTORY:\n- Last success: feature_summary {\"feature_name\": \"f1\"} -> value=1",
            "raw_model_output": "RAW RESPONSE",
            "observation": {
                "ok": True,
                "tool": "feature_summary",
                "feature_name": "f1",
                "value": 1,
                "error_code": None,
                "error_message": None,
            },
        },
    )

    artifact_paths = save_run_artifacts(
        state, metrics={"score": 1}, log_dir=tmp_path)

    debug_log_path = Path(artifact_paths["debug_log_path"])
    assert debug_log_path.exists()
    content = debug_log_path.read_text(encoding="utf-8")
    assert "Partition: Monday-WorkingHours.csv" in content
    assert "Prompt Sections:" in content
    assert "Section Lengths:" in content
    assert "Prompt:" in content
    assert "Model Response:" in content
    assert "Tool Result:" in content
