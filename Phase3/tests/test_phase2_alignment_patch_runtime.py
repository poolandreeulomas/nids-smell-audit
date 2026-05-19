from pathlib import Path

import pandas as pd
import pytest

from agent.loop import run_agent
from analysis.interpreter import extract_run_insights
from analysis.scoring import score_run
from data.dataset_config import get_default_dataset_config
from main import DEFAULT_OBJECTIVE
from prompts.builder import build_prompt
from src.feature_index import build_compact_feature_index
from state.store import init_state
from tools.registry import get_tool_registry


def test_runtime_populates_evidence_and_planning_state():
    dataset_config = get_default_dataset_config()
    dataset_frame = pd.DataFrame(
        {
            "f1": [1, 1, 2, 2, 2, 2],
            "f2": [10.0, 10.5, 50.0, 49.5, 51.0, 52.0],
            "Label": ["BENIGN", "BENIGN", "ATTACK", "ATTACK", "ATTACK", "ATTACK"],
        }
    )
    available_features = ["f1", "f2"]
    state = init_state(
        run_id="runtime_patch",
        objective=DEFAULT_OBJECTIVE,
        max_steps=2,
        available_features=available_features,
        metadata={
            "compact_feature_index": build_compact_feature_index(
                dataset_frame,
                label_col=dataset_config.label_column,
            )
        },
    )
    tool_names = list(get_tool_registry().keys())
    outputs = iter(
        [
            "THOUGHT: Hypothesis: f1 may be low-cardinality and suspicious. | Scope: f1 | Next action: Run cardinality_analysis on f1.\nACTION: cardinality_analysis\nACTION_INPUT: {\"feature_name\": \"f1\"}",
            "THOUGHT: Hypothesis: f2 now looks more suspicious than f1. | Scope: f2 | Next action: Run feature_summary on f2.\nACTION: feature_summary\nACTION_INPUT: {\"feature_name\": \"f2\"}",
        ]
    )

    def fake_llm(_prompt_text: str) -> str:
        return next(outputs)

    final_state = run_agent(
        state=state,
        llm_callable=fake_llm,
        dataset_path=Path("synthetic.csv"),
        dataset_config=dataset_config,
        tool_names=tool_names,
        model_name="test-model",
        temperature=0.0,
        seed=1,
        repo_path=Path(__file__).resolve().parents[1],
        dataset_frame=dataset_frame,
        valid_numeric_features=available_features,
        trace=False,
    )

    assert final_state.evidence_by_feature
    assert "f1" in final_state.evidence_by_feature
    assert "f2" in final_state.evidence_by_feature

    first_block = final_state.evidence_by_feature["f1"][0]
    assert first_block["signals"]
    assert first_block["metrics"]
    assert first_block["provenance"]["tool"] == "cardinality_analysis"
    assert first_block["status"] == "weakened"

    assert final_state.metadata["last_hypothesis"] == "f2 now looks more suspicious than f1."
    assert len(final_state.metadata["hypothesis_history"]) == 2
    assert final_state.contradiction_memory
    assert int(final_state.metadata["overview_usage"]) == 2

    prompt_text = build_prompt(final_state, tool_names)
    assert "signals=[" in prompt_text
    assert "metrics:" in prompt_text
    assert "tools_used=[" not in prompt_text

    insights = extract_run_insights(final_state.to_dict())
    assert "f1" in insights["feature_evidence"]
    assert insights["feature_evidence"]["f1"]["signals"]
    assert "cardinality_ratio" in insights["feature_evidence"]["f1"]["metrics"]

    scored = score_run(insights)
    assert scored["evidence"]["max_signal_tags"] >= 1
    assert scored["evidence"]["max_numeric_anchors"] >= 1


def test_overview_usage_does_not_increment_when_candidates_are_not_shown():
    dataset_config = get_default_dataset_config()
    dataset_frame = pd.DataFrame(
        {
            "f1": [1, 2, 3, 4],
            "Label": ["BENIGN", "BENIGN", "ATTACK", "ATTACK"],
        }
    )
    state = init_state(
        run_id="no_overview",
        objective=DEFAULT_OBJECTIVE,
        max_steps=1,
        available_features=["f1"],
    )
    tool_names = list(get_tool_registry().keys())

    def fake_llm(_prompt_text: str) -> str:
        return (
            "THOUGHT: Hypothesis: f1 may be low-cardinality and suspicious. | Scope: f1 | Next action: Run cardinality_analysis on f1.\n"
            "ACTION: cardinality_analysis\n"
            "ACTION_INPUT: {\"feature_name\": \"f1\"}"
        )

    final_state = run_agent(
        state=state,
        llm_callable=fake_llm,
        dataset_path=Path("synthetic.csv"),
        dataset_config=dataset_config,
        tool_names=tool_names,
        model_name="test-model",
        temperature=0.0,
        seed=1,
        repo_path=Path(__file__).resolve().parents[1],
        dataset_frame=dataset_frame,
        valid_numeric_features=["f1"],
        trace=False,
    )

    assert int(final_state.metadata.get("overview_usage", 0)) == 0


def test_runtime_trace_is_human_readable(capsys):
    dataset_config = get_default_dataset_config()
    dataset_frame = pd.DataFrame(
        {
            "f1": [1, 1, 2, 2],
            "Label": ["BENIGN", "BENIGN", "ATTACK", "ATTACK"],
        }
    )
    state = init_state(
        run_id="trace_human",
        objective=DEFAULT_OBJECTIVE,
        max_steps=1,
        available_features=["f1"],
        metadata={
            "compact_feature_index": build_compact_feature_index(
                dataset_frame,
                label_col=dataset_config.label_column,
            )
        },
    )
    tool_names = list(get_tool_registry().keys())

    def fake_llm(_prompt_text: str) -> str:
        return (
            "THOUGHT: Hypothesis: f1 may be low-cardinality and suspicious. | Scope: f1 | Next action: Run cardinality_analysis on f1.\n"
            "ACTION: cardinality_analysis\n"
            "ACTION_INPUT: {\"feature_name\": \"f1\"}"
        )

    run_agent(
        state=state,
        llm_callable=fake_llm,
        dataset_path=Path("synthetic.csv"),
        dataset_config=dataset_config,
        tool_names=tool_names,
        model_name="test-model",
        temperature=0.0,
        seed=1,
        repo_path=Path(__file__).resolve().parents[1],
        dataset_frame=dataset_frame,
        valid_numeric_features=["f1"],
        trace=True,
    )

    output = capsys.readouterr().out
    assert "STEP 01 | STATUS: OK" in output
    assert "HYPOTHESIS :" in output
    assert "ACTION     :" in output
    assert "OBSERVATION:" in output
    assert "THOUGHT:" not in output


@pytest.mark.parametrize(
    ("model_output", "expected_status"),
    [
        (
            "THOUGHT: Hypothesis: formatting drifted. | Scope: f1 | Next action: Repair JSON.\n"
            "ACTION: feature_summary\n"
            "ACTION_INPUT: {\"feature_name\": \"f1\"",
            "INVALID_JSON",
        ),
        (
            "THINK: Hypothesis: formatting drifted. | Scope: f1 | Next action: Repair output.\n"
            "ACTION: feature_summary\n"
            "ACTION_INPUT: {\"feature_name\": \"f1\"}",
            "PARSE_ERROR",
        ),
    ],
)
def test_high_end_models_stop_early_after_two_parse_failures(
    model_output: str, expected_status: str
):
    dataset_config = get_default_dataset_config()
    state = init_state(
        run_id=f"parse_guard_{expected_status.lower()}",
        objective=DEFAULT_OBJECTIVE,
        max_steps=5,
        available_features=["f1"],
    )
    tool_names = list(get_tool_registry().keys())

    final_state = run_agent(
        state=state,
        llm_callable=lambda _prompt_text: model_output,
        dataset_path=Path("synthetic.csv"),
        dataset_config=dataset_config,
        tool_names=tool_names,
        model_name="gpt-5.4",
        temperature=0.0,
        seed=1,
        repo_path=Path(__file__).resolve().parents[1],
        dataset_frame=None,
        valid_numeric_features=["f1"],
        trace=False,
    )

    assert final_state.current_step == 2
    assert final_state.metadata["status"] == "terminated_due_to_parse_errors"
    assert final_state.metadata["termination_log"] == (
        "Run stopped early due to parse errors (model: gpt-5.4)"
    )
    assert [step["execution_status"] for step in final_state.history] == [
        expected_status,
        expected_status,
    ]
    assert [error["error_code"] for error in final_state.errors] == [
        expected_status,
        expected_status,
        "RUN_TERMINATED",
    ]
