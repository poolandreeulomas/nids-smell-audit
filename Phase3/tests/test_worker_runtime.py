import json
from pathlib import Path

import pandas as pd

from worker.runner import run_worker
from worker.runtime_artifacts import load_worker_bundle


def _write_dataset(tmp_path: Path) -> Path:
    dataset_path = tmp_path / "worker_fixture.csv"
    pd.DataFrame(
        {
            "src_bytes": [10, 12, 100, 105],
            "dst_bytes": [11, 13, 101, 106],
            "dst_port": [80, 80, 443, 443],
            "Label": ["BENIGN", "BENIGN", "ATTACK", "ATTACK"],
        }
    ).to_csv(dataset_path, index=False)
    return dataset_path


def _build_worker_task() -> dict[str, object]:
    return {
        "task_id": "task-hyp-1-1",
        "hypothesis_id": "hyp-1",
        "task_scope": "Probe whether the broad dependency signal remains stronger than the narrow local port signal.",
        "allowed_actions": ["relation_verification", "shortcut_verification"],
        "local_context_refs": ["e1", "e3"],
        "stop_conditions": [
            "Stop when one local strengthening or weakening signal changes the comparison.",
            "Stop when the worker budget is exhausted.",
        ],
    }


def _build_worker_runtime_refs(dataset_path: Path) -> dict[str, object]:
    return {
        "tool_handles": {},
        "dataset_handles": {
            "dataset_path": str(dataset_path),
            "semantic_substrate": {
                "compressed_regions": [
                    {
                        "region_id": "region-1",
                        "summary": "Broad dependency structure links src_bytes and dst_bytes.",
                        "feature_scope": {
                            "features": ["src_bytes", "dst_bytes"],
                            "feature_groups": ["flow_size"],
                            "locality": {
                                "scope_type": "partition_global",
                                "scope_value": "batch-001",
                                "localized": False,
                                "notes": ["Broad dependency evidence."],
                            },
                        },
                        "evidence_refs": ["e1"],
                    }
                ],
                "preserved_weak_signals": [
                    {
                        "weak_signal_id": "weak-1",
                        "descriptor": "Localized dst_port separability remains narrow.",
                        "feature_scope": {
                            "features": ["dst_port"],
                            "feature_groups": ["port_behavior"],
                            "locality": {
                                "scope_type": "feature_group",
                                "scope_value": "port_behavior",
                                "localized": True,
                                "notes": ["Narrow local port signal."],
                            },
                        },
                        "evidence_refs": ["e3"],
                    }
                ],
                "contradictions": [],
                "unresolved_tensions": [],
            },
        },
        "budget_rules": {
            "max_steps": 4,
            "max_retries": 1,
        },
    }


def _continue_response(reasoning: str) -> str:
    return json.dumps(
        {
            "decision": "continue",
            "reasoning": reasoning,
        }
    )


def _action_response(reasoning: str, action: dict[str, object]) -> str:
    return json.dumps(
        {
            "decision": "action",
            "reasoning": reasoning,
            "actions": [action],
        }
    )


def _finish_response(
    *,
    evidence_refs: list[str],
    status: str = "completed",
    findings: list[str] | None = None,
    limitations: list[str] | None = None,
    contradictions: list[str] | None = None,
    reasoning: str = "The final worker status follows from the local evidence progression.",
) -> str:
    return json.dumps(
        {
            "decision": "finish",
            "reasoning": reasoning,
            "worker_result": {
                "task_id": "task-hyp-1-1",
                "hypothesis_id": "hyp-1",
                "status": status,
                "findings": findings or ["The broad dependency pair remained strong in the local slice."],
                "evidence_refs": evidence_refs,
                "contradictions": contradictions or [],
                "limitations": limitations or [],
            },
        }
    )


def test_run_worker_returns_valid_bundle_and_artifacts(tmp_path: Path):
    dataset_path = _write_dataset(tmp_path)
    responses = iter(
        [
            _continue_response(
                "The first pass confirms the task is local and still underdetermined."),
            _continue_response(
                "The second pass narrows the most useful check to the broad size dependency pair."),
            _action_response(
                "A bounded local relation check is warranted before final synthesis.",
                {
                    "action_class": "relation_verification",
                    "context_ref": "e1",
                    "feature_name": "src_bytes",
                    "related_feature_name": "dst_bytes",
                },
            ),
            _finish_response(evidence_refs=["task-hyp-1-1_step_03"]),
        ]
    )

    bundle = run_worker(
        _build_worker_task(),
        _build_worker_runtime_refs(dataset_path),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker_runs"),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["ok"] is True
    assert bundle["worker_output"]["worker_result"]["status"] == "completed"
    assert len(bundle["tool_events"]) == 1
    assert "Stay inside one bounded local worker task" in bundle[
        "prompt_snapshots"][0]["prompt_text"]
    assert bundle["prompt_snapshots"][0]["step_mode"] == "reasoning_only"
    assert bundle["prompt_snapshots"][2]["step_mode"] == "action_window"
    assert bundle["prompt_snapshots"][3]["step_mode"] == "final_synthesis"
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["worker_result_path"]).exists()

    loaded = load_worker_bundle(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["worker_result"]["status"] == "completed"
    assert loaded["operational_trace"]["budget_consumption"]["termination_cause"] == "model_finish"
    assert loaded["tool_events"][0]["tool_name"] == "feature_relation"
    assert loaded["tool_events"][0]["tool_metrics"]["duration_ms"] >= 0.0


def test_run_worker_repairs_one_invalid_action_before_completion(tmp_path: Path):
    dataset_path = _write_dataset(tmp_path)
    responses = iter(
        [
            _continue_response(
                "The task remains unresolved after the first local pass."),
            _continue_response(
                "The second reasoning step identifies one promising local verification route."),
            _action_response(
                "This first proposed action is intentionally invalid to exercise repair.",
                {
                    "action_class": "distribution_verification",
                    "context_ref": "e1",
                    "feature_name": "src_bytes",
                },
            ),
            _action_response(
                "The repaired action stays within the allowed local scope.",
                {
                    "action_class": "relation_verification",
                    "context_ref": "e1",
                    "feature_name": "src_bytes",
                    "related_feature_name": "dst_bytes",
                },
            ),
            _finish_response(
                evidence_refs=["task-hyp-1-1_step_03"],
                status="partial",
                findings=[
                    "The dependency pair still produced local relation evidence after the first invalid step was corrected."
                ],
                limitations=[
                    "One invalid action needed repair before execution continued."],
            ),
        ]
    )

    bundle = run_worker(
        _build_worker_task(),
        _build_worker_runtime_refs(dataset_path),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker_runs"),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["worker_result"]["status"] == "partial"
    assert len(bundle["retry_events"]) == 1
    assert bundle["retry_events"][0]["retry_kind"] == "step_repair"
    assert len(bundle["tool_events"]) == 1


def test_run_worker_executes_non_relation_action_classes(tmp_path: Path):
    dataset_path = _write_dataset(tmp_path)
    responses = iter(
        [
            _continue_response(
                "The first local pass keeps the shortcut question active."),
            _continue_response(
                "The second local pass isolates one feature-level shortcut check."),
            _action_response(
                "A shortcut-oriented bounded action is appropriate before final synthesis.",
                {
                    "action_class": "shortcut_verification",
                    "context_ref": "e1",
                    "feature_name": "src_bytes",
                },
            ),
            _finish_response(
                evidence_refs=["task-hyp-1-1_step_03"],
                findings=[
                    "The local shortcut signal ran successfully for the selected feature."],
            ),
        ]
    )

    bundle = run_worker(
        _build_worker_task(),
        _build_worker_runtime_refs(dataset_path),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker_runs"),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert len(bundle["tool_events"]) == 1
    assert bundle["tool_events"][0]["tool_name"] == "shortcut_analysis"
    assert bundle["tool_events"][0]["execution_ok"] is True
    assert bundle["worker_result"]["status"] == "completed"


def test_run_worker_executes_multiple_actions_in_one_action_window(tmp_path: Path):
    dataset_path = _write_dataset(tmp_path)
    responses = iter(
        [
            _continue_response(
                "The first local pass highlights both a relation check and a shortcut check."),
            _continue_response(
                "The second local pass confirms both checks remain bounded and useful."),
            json.dumps(
                {
                    "decision": "action",
                    "reasoning": "Two bounded checks are justified in the same action window.",
                    "actions": [
                        {
                            "action_class": "relation_verification",
                            "context_ref": "e1",
                            "feature_name": "src_bytes",
                            "related_feature_name": "dst_bytes",
                        },
                        {
                            "action_class": "shortcut_verification",
                            "context_ref": "e1",
                            "feature_name": "src_bytes",
                        },
                    ],
                }
            ),
            _finish_response(
                evidence_refs=[
                    "task-hyp-1-1_step_03_call_01",
                    "task-hyp-1-1_step_03_call_02",
                ],
                findings=[
                    "The relation and shortcut checks both completed inside the same bounded action window."
                ],
            ),
        ]
    )

    bundle = run_worker(
        _build_worker_task(),
        _build_worker_runtime_refs(dataset_path),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker_runs"),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["ok"] is True
    assert len(bundle["tool_events"]) == 2
    assert bundle["tool_events"][0]["call_id"] == "task-hyp-1-1_step_03_call_01"
    assert bundle["tool_events"][1]["call_id"] == "task-hyp-1-1_step_03_call_02"


def test_run_worker_rejects_invalid_runtime_refs_before_calling_llm(tmp_path: Path):
    dataset_path = _write_dataset(tmp_path)
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return "{}"

    bundle = run_worker(
        _build_worker_task(),
        {
            "tool_handles": {},
            "dataset_handles": {
                "dataset_path": str(dataset_path),
                "semantic_substrate": {},
            },
            "budget_rules": {"max_steps": 4, "max_retries": 1},
        },
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=_unexpected_call,
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker_runs"),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["runtime_refs_validation"]["ok"] is False
    assert bundle["prompt_snapshots"] == []
    assert llm_called["value"] is False


def test_run_worker_does_not_commit_invalid_result_after_partial_execution(tmp_path: Path):
    dataset_path = _write_dataset(tmp_path)
    responses = iter(
        [
            _continue_response(
                "The first local reasoning step still needs a direct relation check."),
            _continue_response(
                "The second reasoning step confirms the relation check is the right bounded action."),
            _action_response(
                "A local relation check is required before attempting synthesis.",
                {
                    "action_class": "relation_verification",
                    "context_ref": "e1",
                    "feature_name": "src_bytes",
                    "related_feature_name": "dst_bytes",
                },
            ),
            _finish_response(
                evidence_refs=["invented-call-id"],
                findings=[
                    "Unsupported evidence was claimed after one valid action."],
            ),
            _finish_response(
                evidence_refs=["invented-call-id"],
                findings=[
                    "Unsupported evidence was claimed after one valid action."],
            ),
        ]
    )

    bundle = run_worker(
        _build_worker_task(),
        _build_worker_runtime_refs(dataset_path),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker_runs"),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["worker_result"] == {}
    assert bundle["worker_output"] == {}
    assert bundle["validation_report"]["worker_result_validation"]["ok"] is False
    assert bundle["tool_events"][0]["execution_ok"] is True
    assert bundle["operational_trace"]["budget_consumption"]["termination_cause"] == "invalid_result"
    assert bundle["operational_trace"]["budget_consumption"]["result_committed"] is False
