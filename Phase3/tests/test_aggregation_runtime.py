import json
from pathlib import Path

import pandas as pd

from aggregation.input_resolver import load_worker_result_set
from aggregation.runner import run_aggregation
from aggregation.runtime_artifacts import load_aggregation_bundle
from worker.runner import run_worker


def _write_dataset(tmp_path: Path) -> Path:
    dataset_path = tmp_path / "aggregation_fixture.csv"
    pd.DataFrame(
        {
            "src_bytes": [10, 12, 100, 105],
            "dst_bytes": [11, 13, 101, 106],
            "dst_port": [80, 80, 443, 443],
            "Label": ["BENIGN", "BENIGN", "ATTACK", "ATTACK"],
        }
    ).to_csv(dataset_path, index=False)
    return dataset_path


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
        "budget_rules": {"max_steps": 4, "max_retries": 1},
    }


def _build_worker_task(
    *,
    task_id: str,
    task_scope: str,
    allowed_actions: list[str],
    local_context_refs: list[str],
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "hypothesis_id": "hyp-1",
        "task_scope": task_scope,
        "allowed_actions": allowed_actions,
        "local_context_refs": local_context_refs,
        "stop_conditions": [
            "Stop when one local strengthening or weakening signal changes the comparison.",
            "Stop when the worker budget is exhausted.",
        ],
    }


def _run_saved_worker_bundle(
    tmp_path: Path,
    *,
    task_id: str,
    action: dict[str, object],
    findings: list[str],
    contradictions: list[str],
    limitations: list[str],
) -> dict[str, object]:
    dataset_path = _write_dataset(tmp_path)
    responses = iter(
        [
            json.dumps({"decision": "action", "action": action}),
            json.dumps(
                {
                    "decision": "finish",
                    "worker_result": {
                        "task_id": task_id,
                        "hypothesis_id": "hyp-1",
                        "status": "completed",
                        "findings": findings,
                        "evidence_refs": [f"{task_id}_step_01"],
                        "contradictions": contradictions,
                        "limitations": limitations,
                    },
                }
            ),
        ]
    )
    return run_worker(
        _build_worker_task(
            task_id=task_id,
            task_scope="Probe one bounded local signal for the aggregation fixture.",
            allowed_actions=[str(action.get("action_class"))],
            local_context_refs=[str(action.get("context_ref"))],
        ),
        _build_worker_runtime_refs(dataset_path),
        batch_id="batch-001",
        round_id="round-001",
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "worker_runs"),
    )


def test_load_worker_result_set_resolves_complete_saved_bundle(tmp_path: Path):
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-1",
        action={
            "action_class": "relation_verification",
            "context_ref": "e1",
            "feature_name": "src_bytes",
            "related_feature_name": "dst_bytes",
        },
        findings=["The broad dependency pair remained strong in the local slice."],
        contradictions=[
            "The broad dependency signal still conflicts with the narrower local port signal."],
        limitations=[],
    )
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-2",
        action={
            "action_class": "shortcut_verification",
            "context_ref": "e3",
            "feature_name": "dst_port",
        },
        findings=["The localized port shortcut stayed narrow and incomplete."],
        contradictions=[],
        limitations=[
            "The local port evidence remains too narrow to resolve the wider mechanism."],
    )

    resolved = load_worker_result_set(
        batch_id="batch-001",
        round_id="round-001",
        hypothesis_id="hyp-1",
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        log_dir=tmp_path / "worker_runs",
    )

    assert resolved["worker_result_set"]["hypothesis_id"] == "hyp-1"
    assert len(resolved["worker_result_set"]["worker_results"]) == 2
    assert resolved["normalized_inputs"]["missing_task_ids"] == []
    assert len(resolved["selected_run_dirs"]) == 2


def test_run_aggregation_returns_valid_bundle_and_artifacts(tmp_path: Path):
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-1",
        action={
            "action_class": "relation_verification",
            "context_ref": "e1",
            "feature_name": "src_bytes",
            "related_feature_name": "dst_bytes",
        },
        findings=["The broad dependency pair remained strong in the local slice."],
        contradictions=[
            "The broad dependency signal still conflicts with the narrower local port signal."],
        limitations=[],
    )
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-2",
        action={
            "action_class": "shortcut_verification",
            "context_ref": "e3",
            "feature_name": "dst_port",
        },
        findings=["The localized port shortcut stayed narrow and incomplete."],
        contradictions=[],
        limitations=[
            "The local port evidence remains too narrow to resolve the wider mechanism."],
    )
    resolved = load_worker_result_set(
        batch_id="batch-001",
        round_id="round-001",
        hypothesis_id="hyp-1",
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        log_dir=tmp_path / "worker_runs",
    )
    responses = iter(
        [
            json.dumps(
                {
                    "aggregation_handoff": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "hypothesis_id": "hyp-1",
                        "merged_findings": [
                            "The wider dependency signal remains stronger than the narrow port-local shortcut."
                        ],
                        "evidence_refs": ["task-hyp-1-1_step_01", "task-hyp-1-2_step_01"],
                        "preserved_contradiction_ids": ["contr_0"],
                        "open_gaps": [
                            "The local port evidence remains too narrow to resolve the wider mechanism."
                        ],
                        "update_focus": "Dependency strength versus localized port evidence.",
                    }
                }
            )
        ]
    )

    bundle = run_aggregation(
        resolved["worker_result_set"],
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "aggregation_runs"),
        source_run_dirs=resolved["selected_run_dirs"],
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["handoff_committed"] is True
    assert bundle["validation_report"]["ok"] is True
    assert bundle["aggregation_handoff"]["update_focus"] == "Dependency strength versus localized port evidence."
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["aggregation_handoff_path"]).exists()

    loaded = load_aggregation_bundle(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["aggregation_handoff"]["hypothesis_id"] == "hyp-1"
    assert loaded["runtime_metrics"]["worker_result_count"] == 2


def test_run_aggregation_accepts_update_focus_overflow_without_failing_round(tmp_path: Path):
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-1",
        action={
            "action_class": "relation_verification",
            "context_ref": "e1",
            "feature_name": "src_bytes",
            "related_feature_name": "dst_bytes",
        },
        findings=["The broad dependency pair remained strong in the local slice."],
        contradictions=[
            "The broad dependency signal still conflicts with the narrower local port signal."],
        limitations=[],
    )
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-2",
        action={
            "action_class": "shortcut_verification",
            "context_ref": "e3",
            "feature_name": "dst_port",
        },
        findings=["The localized port shortcut stayed narrow and incomplete."],
        contradictions=[],
        limitations=[
            "The local port evidence remains too narrow to resolve the wider mechanism."],
    )
    resolved = load_worker_result_set(
        batch_id="batch-001",
        round_id="round-001",
        hypothesis_id="hyp-1",
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        log_dir=tmp_path / "worker_runs",
    )
    responses = iter(
        [
            json.dumps(
                {
                    "aggregation_handoff": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "hypothesis_id": "hyp-1",
                        "merged_findings": [
                            "The wider dependency signal remains stronger than the narrow port-local shortcut."
                        ],
                        "evidence_refs": ["task-hyp-1-1_step_01", "task-hyp-1-2_step_01"],
                        "preserved_contradiction_ids": ["contr_0"],
                        "open_gaps": [
                            "The local port evidence remains too narrow to resolve the wider mechanism."
                        ],
                        "update_focus": (
                            "Dependency strength versus localized port evidence. "
                            "This sentence is intentionally extended so the aggregation handoff remains valid without any cosmetic truncation rule."
                        ),
                    }
                }
            )
        ]
    )

    bundle = run_aggregation(
        resolved["worker_result_set"],
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "aggregation_runs"),
        source_run_dirs=resolved["selected_run_dirs"],
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["handoff_committed"] is True
    assert bundle["validation_report"]["ok"] is True
    assert bundle["validation_report"]["aggregation_handoff_validation"]["ok"] is True
    assert any(
        warning["field"] == "update_focus"
        for warning in bundle["validation_report"]["aggregation_handoff_validation"]["warnings"]
    )
    assert bundle["validation_report"]["repair_attempts"] == []
    assert len(bundle["aggregation_handoff"]["update_focus"]) > 160

    loaded = load_aggregation_bundle(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["repair_attempts"] == []
    assert len(loaded["aggregation_handoff"]["update_focus"]) > 160


def test_run_aggregation_rejects_mixed_hypothesis_worker_results_before_calling_llm(tmp_path: Path):
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return "{}"

    bundle = run_aggregation(
        {
            "batch_id": "batch-001",
            "round_id": "round-001",
            "hypothesis_id": "hyp-1",
            "worker_results": [
                {
                    "task_id": "task-hyp-1-1",
                    "hypothesis_id": "hyp-2",
                    "status": "completed",
                    "findings": ["Mismatched worker result."],
                    "evidence_refs": ["task-hyp-1-1_step_01"],
                    "contradictions": [],
                    "limitations": [],
                }
            ],
        },
        expected_task_ids=["task-hyp-1-1"],
        llm_callable=_unexpected_call,
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "aggregation_runs"),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["worker_result_set_validation"]["ok"] is False
    assert bundle["prompt_text"] == ""
    assert llm_called["value"] is False


def test_run_aggregation_fails_closed_on_invalid_handoff(tmp_path: Path):
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-1",
        action={
            "action_class": "relation_verification",
            "context_ref": "e1",
            "feature_name": "src_bytes",
            "related_feature_name": "dst_bytes",
        },
        findings=["The broad dependency pair remained strong in the local slice."],
        contradictions=[
            "The broad dependency signal still conflicts with the narrower local port signal."],
        limitations=[],
    )
    _run_saved_worker_bundle(
        tmp_path,
        task_id="task-hyp-1-2",
        action={
            "action_class": "shortcut_verification",
            "context_ref": "e3",
            "feature_name": "dst_port",
        },
        findings=["The localized port shortcut stayed narrow and incomplete."],
        contradictions=[],
        limitations=[
            "The local port evidence remains too narrow to resolve the wider mechanism."],
    )
    resolved = load_worker_result_set(
        batch_id="batch-001",
        round_id="round-001",
        hypothesis_id="hyp-1",
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        log_dir=tmp_path / "worker_runs",
    )
    responses = iter(
        [
            json.dumps(
                {
                    "aggregation_handoff": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "hypothesis_id": "hyp-1",
                        "merged_findings": [
                            "The wider dependency signal remains stronger than the narrow port-local shortcut."
                        ],
                        "evidence_refs": ["invented-evidence-ref"],
                        "preserved_contradiction_ids": [],
                        "open_gaps": [],
                        "update_focus": "Dependency strength versus localized port evidence.",
                    }
                }
            )
        ]
    )

    bundle = run_aggregation(
        resolved["worker_result_set"],
        expected_task_ids=["task-hyp-1-1", "task-hyp-1-2"],
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "aggregation_runs"),
        source_run_dirs=resolved["selected_run_dirs"],
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["component_run"]["handoff_committed"] is False
    assert bundle["aggregation_handoff"] == {}
    assert bundle["validation_report"]["aggregation_handoff_validation"]["ok"] is False
    assert bundle["parsed_output"]["evidence_refs"] == [
        "invented-evidence-ref"]
