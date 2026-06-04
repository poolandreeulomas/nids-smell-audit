import json
from pathlib import Path

from aggregation.contracts import build_aggregation_handoff
from critic.runner import run_critic
from critic.runtime_artifacts import load_critic_bundle
from investigation_analysis.contracts import build_hypothesis, build_hypothesis_set
from semantic_extraction.contracts import (
    build_feature_scope,
    build_locality_descriptor,
    build_region,
    build_semantic_substrate,
)
from state.store import init_canonical_batch_state
from state_manager.runner import run_state_manager


def _build_round_component_bundles() -> dict[str, object]:
    return {
        "hypothesis_ranking": {
            "component_run": {
                "component": "hypothesis_ranking",
                "batch_id": "batch-001",
                "round_id": "round-001",
                "status": "ok",
                "validation_ok": True,
            },
            "artifact_paths": {
                "candidate_hypotheses_path": "hypothesis_ranking/candidate_hypotheses.json",
                "ranking_state_snapshot_path": "hypothesis_ranking/ranking_state_snapshot.json",
                "parsed_output_path": "hypothesis_ranking/parsed_output.json",
                "selection_index_path": "hypothesis_ranking/selection_index.json",
                "validation_report_path": "hypothesis_ranking/validation_report.json",
                "runtime_metrics_path": "hypothesis_ranking/runtime_metrics.json",
            },
            "candidate_hypotheses": {
                "candidate_hypotheses": [
                    {
                        "hypothesis_id": "hyp-1",
                        "evidence_refs": ["region-e1"],
                    }
                ]
            },
            "parsed_output": {
                "selected_hypotheses": [
                    {
                        "hypothesis_id": "hyp-1",
                        "evidence_refs": ["region-e1"],
                    }
                ]
            },
            "selection_index": {"selected_count": 1},
            "runtime_metrics": {"candidate_count": 1, "selected_count": 1},
        },
        "planner": {
            "component_run": {
                "component": "planner",
                "batch_id": "batch-001",
                "round_id": "round-001",
                "status": "ok",
                "validation_ok": True,
            },
            "artifact_paths": {
                "ranking_decision_min_path": "planner/ranking_decision_min.json",
                "selected_hypothesis_context_path": "planner/selected_hypothesis_context.json",
                "planner_round_context_path": "planner/planner_round_context.json",
                "parsed_output_path": "planner/parsed_output.json",
                "strategy_index_path": "planner/strategy_index.json",
                "validation_report_path": "planner/validation_report.json",
                "runtime_metrics_path": "planner/runtime_metrics.json",
            },
            "selected_hypothesis_context": {
                "selected_hypotheses": [
                    {
                        "hypothesis_id": "hyp-1",
                        "evidence_refs": ["region-e1"],
                    }
                ]
            },
            "parsed_output": {
                "planner_strategies": [
                    {
                        "strategy_id": "planner-strategy-1",
                        "hypothesis_id": "hyp-1",
                        "evidence_refs": ["region-e1"],
                    }
                ]
            },
            "strategy_index": {"strategy_count": 1},
            "runtime_metrics": {
                "selected_count": 1,
                "strategy_count": 1,
                "tool_capability_ref_count": 2,
            },
        },
        "router": {
            "component_run": {
                "component": "router",
                "batch_id": "batch-001",
                "round_id": "round-001",
                "hypothesis_id": "hyp-1",
                "planner_strategy_id": "planner-strategy-1",
                "status": "ok",
                "validation_ok": True,
            },
            "artifact_paths": {
                "planner_strategy_path": "router/planner_strategy.json",
                "router_context_min_path": "router/router_context_min.json",
                "parsed_output_path": "router/parsed_output.json",
                "task_bundle_index_path": "router/task_bundle_index.json",
                "validation_report_path": "router/validation_report.json",
                "runtime_metrics_path": "router/runtime_metrics.json",
            },
            "planner_strategy": {
                "strategy_id": "planner-strategy-1",
                "hypothesis_id": "hyp-1",
                "evidence_refs": ["region-e1"],
            },
            "parsed_output": {
                "worker_tasks": [
                    {
                        "task_id": "task-hyp-1-1",
                        "hypothesis_id": "hyp-1",
                        "local_context_refs": ["ctx-ref-1"],
                    }
                ]
            },
            "task_bundle_index": {"task_count": 1},
            "runtime_metrics": {"task_count": 1},
        },
        "worker": [
            {
                "component_run": {
                    "component": "worker",
                    "batch_id": "batch-001",
                    "round_id": "round-001",
                    "hypothesis_id": "hyp-1",
                    "task_id": "task-hyp-1-1",
                    "status": "ok",
                    "validation_ok": True,
                    "result_committed": True,
                },
                "artifact_paths": {
                    "worker_task_path": "worker/worker_task.json",
                    "worker_runtime_refs_path": "worker/worker_runtime_refs.json",
                    "worker_result_path": "worker/worker_result.json",
                    "worker_output_path": "worker/worker_output.json",
                    "operational_trace_path": "worker/operational_trace.json",
                    "validation_report_path": "worker/validation_report.json",
                    "runtime_metrics_path": "worker/runtime_metrics.json",
                },
                "worker_task": {
                    "task_id": "task-hyp-1-1",
                    "hypothesis_id": "hyp-1",
                    "local_context_refs": ["ctx-ref-1"],
                },
                "worker_result": {
                    "task_id": "task-hyp-1-1",
                    "hypothesis_id": "hyp-1",
                    "evidence_refs": ["task-hyp-1-1_step_01"],
                },
                "worker_output": {
                    "batch_id": "batch-001",
                    "round_id": "round-001",
                    "worker_result": {
                        "task_id": "task-hyp-1-1",
                    },
                },
                "operational_trace": {
                    "action_sequence": [
                        {
                            "call_id": "task-hyp-1-1_step_01",
                            "context_ref": "ctx-ref-1",
                        }
                    ]
                },
                "runtime_metrics": {
                    "tool_event_count": 1,
                    "failure_event_count": 0,
                    "termination_cause": "model_finish",
                },
            }
        ],
        "aggregation": {
            "component_run": {
                "component": "aggregation",
                "batch_id": "batch-001",
                "round_id": "round-001",
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
                "handoff_committed": True,
            },
            "artifact_paths": {
                "worker_result_set_path": "aggregation/worker_result_set.json",
                "normalized_inputs_path": "aggregation/normalized_inputs.json",
                "aggregation_handoff_path": "aggregation/aggregation_handoff.json",
                "overlap_diagnostics_path": "aggregation/overlap_diagnostics.json",
                "validation_report_path": "aggregation/validation_report.json",
                "runtime_metrics_path": "aggregation/runtime_metrics.json",
            },
            "worker_result_set": {
                "worker_results": [
                    {
                        "task_id": "task-hyp-1-1",
                        "evidence_refs": ["task-hyp-1-1_step_01"],
                    }
                ]
            },
            "overlap_diagnostics": [],
            "aggregation_handoff": _build_aggregation_handoff(),
        },
    }


def _build_semantic_substrate() -> dict[str, object]:
    return build_semantic_substrate(
        substrate_id="substrate-001",
        batch_id="batch-001",
        compressed_regions=[
            build_region(
                region_id="region-1",
                region_kind="dependency_region",
                status="broad_unvalidated",
                summary="src_bytes and dst_bytes move together in the global slice.",
                feature_scope=build_feature_scope(
                    features=["src_bytes", "dst_bytes"],
                    feature_groups=["flow_size"],
                    locality=build_locality_descriptor(
                        scope_type="partition_global",
                        scope_value="batch-001",
                        localized=False,
                        notes=["Global dependency signal."],
                    ),
                ),
                evidence_refs=["region-e1"],
            )
        ],
        preserved_weak_signals=[],
        contradictions=[],
        unresolved_tensions=[],
    )


def _build_hypothesis_set() -> dict[str, object]:
    return build_hypothesis_set(
        analysis_id="analysis-001",
        batch_id="batch-001",
        hypotheses=[
            build_hypothesis(
                hypothesis_id="hyp-1",
                summary="The dependency may reflect a shortcut-compatible framing.",
                evidence_refs=["region-e1"],
                open_questions=["Need to verify whether the dependency stays local."],
            )
        ],
    )


def _build_initial_state() -> dict[str, object]:
    return init_canonical_batch_state(
        batch_id="batch-001",
        structural_substrate=_build_semantic_substrate(),
        hypothesis_set=_build_hypothesis_set(),
    ).to_dict()


def _build_aggregation_handoff() -> dict[str, object]:
    return build_aggregation_handoff(
        batch_id="batch-001",
        round_id="round-001",
        hypothesis_id="hyp-1",
        merged_findings=[
            "The dependency signal remained visible in the targeted local slice."
        ],
        evidence_refs=["task-hyp-1-1_step_01"],
        preserved_contradictions=[
            "Current local evidence still conflicts with the broader dependency framing."
        ],
        open_gaps=["Need one more counter-check before closing the framing."],
        update_focus="Carry forward the dependency framing without collapsing the remaining contradiction.",
    )


def _build_state_manager_bundle(tmp_path: Path) -> dict[str, object]:
    responses = iter(
        [
            json.dumps(
                {
                    "state_delta_record": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "hypothesis_id": "hyp-1",
                        "summary": "The dependency framing remains active after local verification, but the contradiction is still unresolved.",
                        "status": "active",
                        "evidence_refs": ["region-e1", "task-hyp-1-1_step_01"],
                        "preserved_contradictions": [
                            "Current local evidence still conflicts with the broader dependency framing."
                        ],
                        "open_gaps": [
                            "Need to verify whether the dependency stays local.",
                            "Need one more counter-check before closing the framing.",
                        ],
                        "merged_findings": [
                            "The dependency signal remained visible in the targeted local slice."
                        ],
                        "update_focus": "Carry forward the dependency framing without collapsing the remaining contradiction.",
                        "applied_updates": [
                            {
                                "field": "summary",
                                "reason": "The aggregation handoff strengthened the current framing without resolving the contradiction."
                            }
                        ],
                    }
                }
            )
        ]
    )

    return run_state_manager(
        _build_initial_state(),
        _build_aggregation_handoff(),
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )


def test_run_critic_returns_valid_bundle_and_artifacts(tmp_path: Path):
    state_manager_bundle = _build_state_manager_bundle(tmp_path)
    round_component_bundles = _build_round_component_bundles()
    responses = iter(
        [
            json.dumps(
                {
                    "critic_feedback_payload": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "module_feedback": [
                            {
                                "module_name": "planner",
                                "observed_issue": "Planner is pushing one strategy forward without stating the narrowest closure check clearly enough.",
                                "evidence_refs": ["planner-strategy-1"],
                                "suggestion": "State one explicit closure check before expanding the next planner strategy set.",
                            }
                        ],
                    }
                }
            )
        ]
    )

    bundle = run_critic(
        state_manager_bundle,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "critic_runs"),
        round_component_bundles=round_component_bundles,
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["validation_ok"] is True
    assert bundle["component_run"]["module_feedback_count"] == 1
    assert bundle["validation_report"]["ok"] is True
    assert bundle["validation_report"]["final_round_gate"]["status"] == "allowed_non_final_round"
    assert {item["module_name"] for item in bundle["module_behavior_summaries"]} >= {
        "planner",
        "router",
        "worker",
        "aggregation",
        "state_manager",
    }
    assert any(
        item["module_name"] == "planner"
        for item in bundle["critic_input_min"]["module_artifact_refs"]
    )
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["critic_feedback_payload_path"]).exists()

    loaded = load_critic_bundle(Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["component_run"]["prompt_version"] == "phase3a.critic.prompt.v1"
    assert loaded["critic_feedback_payload"]["round_id"] == "round-001"


def test_run_critic_skips_final_round_before_calling_llm(tmp_path: Path):
    state_manager_bundle = _build_state_manager_bundle(tmp_path)
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return "{}"

    bundle = run_critic(
        state_manager_bundle,
        llm_callable=_unexpected_call,
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "critic_runs"),
        is_final_round=True,
    )

    assert bundle["component_run"]["status"] == "skipped"
    assert bundle["validation_report"]["ok"] is True
    assert bundle["validation_report"]["final_round_gate"]["status"] == "skipped_final_round"
    assert bundle["prompt_text"] == ""
    assert bundle["critic_feedback_payload"] == {}
    assert llm_called["value"] is False


def test_run_critic_flags_hard_directive_feedback_without_blocking(tmp_path: Path):
    state_manager_bundle = _build_state_manager_bundle(tmp_path)
    round_component_bundles = _build_round_component_bundles()
    responses = iter(
        [
            json.dumps(
                {
                    "critic_feedback_payload": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "module_feedback": [
                            {
                                "module_name": "planner",
                                "observed_issue": "The round is narrowing too quickly around the current framing.",
                                "evidence_refs": ["task-hyp-1-1_step_01"],
                                "suggestion": "Replan the next round and rerank the active hypotheses immediately.",
                            }
                        ],
                    }
                }
            )
        ]
    )

    bundle = run_critic(
        state_manager_bundle,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "critic_runs"),
        round_component_bundles=round_component_bundles,
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["feedback_committed"] is True
    assert bundle["validation_report"]["critic_feedback_validation"]["ok"] is True
    assert any(
        "Semantic language flag detected" in warning["message"]
        for warning in bundle["validation_report"]["critic_feedback_validation"]["warnings"]
    )
    assert any(
        hit["code"] in {"planning_directive", "execution_directive"}
        for hit in bundle["validation_report"]["critic_feedback_validation"]["forbidden_language_hits"]
    )


def test_run_critic_rejects_feedback_for_unobserved_module(tmp_path: Path):
    state_manager_bundle = _build_state_manager_bundle(tmp_path)
    responses = iter(
        [
            json.dumps(
                {
                    "critic_feedback_payload": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "module_feedback": [
                            {
                                "module_name": "planner",
                                "observed_issue": "Planner is not isolating the closure target sharply enough.",
                                "evidence_refs": ["task-hyp-1-1_step_01"],
                                "suggestion": "Keep the next planner step focused on one closure test.",
                            }
                        ],
                    }
                }
            )
        ]
    )

    bundle = run_critic(
        state_manager_bundle,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "critic_runs"),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["critic_feedback_validation"]["ok"] is False
    assert any(
        "observed modules" in error["message"]
        for error in bundle["validation_report"]["critic_feedback_validation"]["errors"]
    )
