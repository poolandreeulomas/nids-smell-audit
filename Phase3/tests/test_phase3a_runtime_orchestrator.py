from copy import deepcopy
from pathlib import Path

import phase3_runtime.orchestrator as orchestrator
import phase3_runtime.round_executor as round_executor
from investigation_analysis.contracts import build_hypothesis, build_hypothesis_set
from semantic_extraction.contracts import (
    build_feature_scope,
    build_locality_descriptor,
    build_region,
    build_semantic_substrate,
)
from state.store import init_canonical_batch_state


def _build_semantic_substrate(batch_id: str) -> dict[str, object]:
    return build_semantic_substrate(
        substrate_id="runtime-substrate-001",
        batch_id=batch_id,
        compressed_regions=[
            build_region(
                region_id="runtime-region-1",
                region_kind="dependency_region",
                status="broad_unvalidated",
                summary="src_bytes and dst_bytes remain tightly coupled in the batch slice.",
                feature_scope=build_feature_scope(
                    features=["src_bytes", "dst_bytes"],
                    feature_groups=["flow_size"],
                    locality=build_locality_descriptor(
                        scope_type="partition_global",
                        scope_value=batch_id,
                        localized=False,
                        notes=["Global dependency signal."],
                    ),
                ),
                evidence_refs=["runtime-region-e1"],
            )
        ],
        preserved_weak_signals=[],
        contradictions=[],
        unresolved_tensions=[],
    )


def _build_hypothesis_set(batch_id: str, analysis_id: str, summary: str) -> dict[str, object]:
    return build_hypothesis_set(
        analysis_id=analysis_id,
        batch_id=batch_id,
        hypotheses=[
            build_hypothesis(
                hypothesis_id="hyp-1",
                summary=summary,
                evidence_refs=["runtime-region-e1"],
                open_questions=[
                    "Need to verify whether the dependency stays local."],
            )
        ],
    )


def _build_multi_hypothesis_set(batch_id: str, analysis_id: str) -> dict[str, object]:
    return build_hypothesis_set(
        analysis_id=analysis_id,
        batch_id=batch_id,
        hypotheses=[
            build_hypothesis(
                hypothesis_id="hyp-1",
                summary="Broad dependency framing remains active.",
                evidence_refs=["runtime-region-e1"],
                open_questions=[
                    "Need a bounded relation check for the first framing."],
            ),
            build_hypothesis(
                hypothesis_id="hyp-2",
                summary="A narrower shortcut-like framing remains plausible.",
                evidence_refs=["runtime-region-e1"],
                open_questions=[
                    "Need a bounded shortcut check for the second framing."],
            ),
        ],
    )


def test_run_phase3a_batch_refreshes_analysis_after_round_one_and_keeps_round_start_state_frozen(
    tmp_path,
    monkeypatch,
):
    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text(
        "Label,src_bytes,dst_bytes\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "runtime-batch-001"

    analysis_calls: list[dict[str, object]] = []
    ranking_calls: list[dict[str, object]] = []
    planner_order: list[str] = []
    state_manager_prior_versions: list[int] = []
    final_auditor_calls: list[dict[str, object]] = []
    critic_calls: list[str] = []

    semantic_substrate = _build_semantic_substrate(batch_id)
    initial_hypothesis_set = _build_hypothesis_set(
        batch_id,
        analysis_id="analysis-initial-001",
        summary="Initial dependency framing remains broad and unresolved.",
    )
    refreshed_hypothesis_set = _build_hypothesis_set(
        batch_id,
        analysis_id="analysis-refresh-002",
        summary="Refreshed dependency framing incorporates the committed round-one state.",
    )

    def fake_build_initial_semantic_inputs(dataset_path_arg, runtime_batch_id):
        assert Path(dataset_path_arg) == dataset_path
        assert runtime_batch_id == batch_id
        return {
            "overview_summary_min": {"batch_id": runtime_batch_id},
            "partition_context": {"partition_semantics": ["synthetic"]},
        }

    def fake_build_initial_analysis_context(dataset_path_arg):
        assert Path(dataset_path_arg) == dataset_path
        return {
            "partition_context_ref": {
                "semantics": ["synthetic"],
                "expected_properties": ["deterministic"],
                "epistemic_warnings": ["bounded"],
                "investigation_guidance": ["stay local"],
            },
            "artifact_framing_refs": [
                {
                    "framing_id": "synthetic-framing",
                    "label": "synthetic framing",
                    "description": "Synthetic runtime framing for orchestration tests.",
                }
            ],
        }

    def fake_run_semantic_extraction(overview_summary_min, partition_context, **kwargs):
        return {
            "component_run": {
                "component": "semantic_extraction",
                "batch_id": batch_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": semantic_substrate,
            "artifact_paths": {
                "component_run_path": str(tmp_path / "semantic_extraction" / "component_run.json"),
            },
        }

    def fake_run_investigation_analysis(semantic_substrate_input, analysis_context_min, analysis_iteration_context_min=None, **kwargs):
        analysis_calls.append(
            {
                "analysis_iteration_context_min": dict(analysis_iteration_context_min or {}),
                "analysis_context_min": dict(analysis_context_min or {}),
            }
        )
        hypothesis_set = initial_hypothesis_set if len(
            analysis_calls) == 1 else refreshed_hypothesis_set
        return {
            "component_run": {
                "component": "investigation_analysis",
                "batch_id": batch_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": hypothesis_set,
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"investigation_analysis_{len(analysis_calls)}" / "component_run.json"),
            },
        }

    def fake_run_hypothesis_ranking(investigation_hypothesis_set, ranking_state_min, **kwargs):
        ranking_calls.append(deepcopy(ranking_state_min))
        round_id = str(ranking_state_min.get("round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "hypothesis_ranking",
                "batch_id": batch_id,
                "round_id": round_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "selected_hypothesis_ids": ["hyp-1"],
                "deferred_hypothesis_ids": [],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"ranking_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_planner(ranking_decision_min, selected_hypothesis_context, planner_round_context, **kwargs):
        round_id = str(planner_round_context.get(
            "round_id") or "unknown_round")
        planner_order.append(f"planner:{round_id}")
        return {
            "component_run": {
                "component": "planner",
                "batch_id": batch_id,
                "round_id": round_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "planner_strategies": [
                    {
                        "strategy_id": f"strategy-{round_id}",
                        "hypothesis_id": "hyp-1",
                        "strategic_objective": "Bound one local dependency check.",
                        "key_checks": ["local dependency check"],
                        "success_criteria": ["one bounded local check"],
                        "router_constraints": ["stay local"],
                        "tool_capability_refs": ["feature_summary"],
                    }
                ],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"planner_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_router(planner_strategy, router_context_min, **kwargs):
        round_id = str(kwargs.get("round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "router",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "planner_strategy_id": str(planner_strategy.get("strategy_id") or "strategy"),
                "worker_tasks": [
                    {
                        "task_id": f"task-{round_id}",
                        "hypothesis_id": "hyp-1",
                        "task_scope": "feature",
                        "allowed_actions": ["structural_summary"],
                        "local_context_refs": ["runtime-region-e1"],
                        "stop_conditions": ["one check"],
                    }
                ],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"router_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_worker(worker_task, worker_runtime_refs, **kwargs):
        round_id = str(kwargs.get("round_id") or "unknown_round")
        task_id = str(worker_task.get("task_id") or "task")
        return {
            "component_run": {
                "component": "worker",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
                "result_committed": True,
            },
            "worker_result": {
                "task_id": task_id,
                "hypothesis_id": "hyp-1",
                "status": "completed",
                "findings": [f"finding-{round_id}"],
                "evidence_refs": [f"worker-evidence-{round_id}"],
                "contradictions": [],
                "limitations": [],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"worker_{round_id}_{task_id}" / "component_run.json"),
            },
        }

    def fake_run_aggregation(worker_result_set, expected_task_ids=None, source_run_dirs=None, **kwargs):
        round_id = str(worker_result_set.get("round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "aggregation",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
                "handoff_committed": True,
            },
            "aggregation_handoff": {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "merged_findings": [f"merged-{round_id}"],
                "evidence_refs": [f"worker-evidence-{round_id}"],
                "preserved_contradictions": [],
                "open_gaps": [f"gap-{round_id}"],
                "update_focus": f"focus-{round_id}",
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"aggregation_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_state_manager(canonical_batch_state, aggregation_handoff, expected_prior_state_version=None, **kwargs):
        round_id = str(aggregation_handoff.get("round_id") or "unknown_round")
        planner_order.append(f"state_manager:{round_id}")
        state_manager_prior_versions.append(
            int(expected_prior_state_version or 0))
        updated_batch_state = deepcopy(canonical_batch_state)
        updated_batch_state["state_version"] = int(
            updated_batch_state.get("state_version") or 0) + 1
        hypothesis = dict(updated_batch_state["interpretive_hypotheses"][0])
        hypothesis["summary"] = f"updated-summary-{round_id}"
        hypothesis["status"] = "active"
        hypothesis["evidence_refs"] = [
            "runtime-region-e1", f"worker-evidence-{round_id}"]
        hypothesis["open_gaps"] = [f"gap-{round_id}"]
        hypothesis["merged_findings"] = [f"merged-{round_id}"]
        hypothesis["last_updated_round"] = round_id
        hypothesis["revision_count"] = int(
            hypothesis.get("revision_count") or 0) + 1
        updated_batch_state["interpretive_hypotheses"][0] = hypothesis
        updated_batch_state.setdefault("revision_log", []).append(
            {
                "revision_type": "state_update",
                "state_version": updated_batch_state["state_version"],
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "applied_updates": [{"field": "summary"}],
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        )
        return {
            "component_run": {
                "component": "state_manager",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
                "state_committed": True,
                "new_state_version": updated_batch_state["state_version"],
            },
            "updated_batch_state": updated_batch_state,
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"state_manager_{round_id}" / "component_run.json"),
                "updated_batch_state_path": str(tmp_path / f"state_manager_{round_id}" / "updated_batch_state.json"),
            },
        }

    def fake_run_critic(*args, **kwargs):
        critic_calls.append("called")
        return {
            "component_run": {
                "component": "critic",
                "validation_ok": True,
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / "critic" / "component_run.json"),
            },
        }

    def fake_run_final_batch_auditor(state_manager_bundle, **kwargs):
        final_auditor_calls.append(
            {
                "is_final_batch": bool(kwargs.get("is_final_batch")),
                "state_manager_bundle": dict(state_manager_bundle),
                "batch_component_bundles": dict(kwargs.get("batch_component_bundles") or {}),
            }
        )
        return {
            "component_run": {
                "component": "final_batch_auditor",
                "batch_id": batch_id,
                "status": "ok",
                "validation_ok": True,
                "report_committed": True,
            },
            "debugging_audit_report": {
                "batch_id": batch_id,
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / "final_batch_auditor" / "component_run.json"),
            },
        }

    monkeypatch.setattr(orchestrator, "build_initial_semantic_inputs",
                        fake_build_initial_semantic_inputs)
    monkeypatch.setattr(orchestrator, "build_initial_analysis_context",
                        fake_build_initial_analysis_context)
    monkeypatch.setattr(orchestrator, "run_semantic_extraction",
                        fake_run_semantic_extraction)
    monkeypatch.setattr(
        orchestrator, "run_investigation_analysis", fake_run_investigation_analysis)
    monkeypatch.setattr(orchestrator, "run_final_batch_auditor",
                        fake_run_final_batch_auditor)
    monkeypatch.setattr(
        round_executor, "run_investigation_analysis", fake_run_investigation_analysis)
    monkeypatch.setattr(
        round_executor, "run_hypothesis_ranking", fake_run_hypothesis_ranking)
    monkeypatch.setattr(round_executor, "run_planner", fake_run_planner)
    monkeypatch.setattr(round_executor, "run_router", fake_run_router)
    monkeypatch.setattr(round_executor, "run_worker", fake_run_worker)
    monkeypatch.setattr(round_executor, "run_aggregation",
                        fake_run_aggregation)
    monkeypatch.setattr(round_executor, "run_state_manager",
                        fake_run_state_manager)
    monkeypatch.setattr(round_executor, "run_critic", fake_run_critic)

    bundle = orchestrator.run_phase3a_batch(
        dataset_path,
        batch_id=batch_id,
        model_name="gpt-4.1-mini",
        max_rounds=2,
        enable_critic=False,
        log_dir=tmp_path / "runtime_logs",
    )

    assert bundle["component_run"]["status"] == "completed"
    assert bundle["runtime_metrics"]["analysis_refresh_count"] == 1
    assert bundle["batch_ledger"].round_manifests[0].analysis_mode == "initial"
    assert bundle["batch_ledger"].round_manifests[1].analysis_mode == "refresh"
    assert analysis_calls[0]["analysis_iteration_context_min"] == {}
    assert analysis_calls[1]["analysis_iteration_context_min"]["current_state_ref"]["state_id"] == "runtime-batch-001:v2"
    assert any(
        "updated-summary-round-001" in note
        for note in analysis_calls[1]["analysis_iteration_context_min"]["current_state_ref"]["state_notes"]
    )
    assert any(
        "round_start_state_version=1" == constraint
        for constraint in ranking_calls[0]["round_constraints"]
    )
    assert any(
        "round_start_state_version=2" == constraint
        for constraint in ranking_calls[1]["round_constraints"]
    )
    assert planner_order.index(
        "planner:round-001") < planner_order.index("state_manager:round-001")
    assert planner_order.index(
        "planner:round-002") < planner_order.index("state_manager:round-002")
    assert state_manager_prior_versions == [1, 2]
    assert critic_calls == []
    assert final_auditor_calls[0]["is_final_batch"] is True
    assert len(
        final_auditor_calls[0]["batch_component_bundles"]["state_manager"]) == 2
    assert Path(bundle["artifact_paths"]["batch_ledger_path"]).exists()
    assert Path(bundle["artifact_paths"]["initial_state_path"]).exists()


def test_run_phase3a_batch_propagates_critic_guidance_to_next_round_contexts(
    tmp_path,
    monkeypatch,
):
    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text(
        "Label,src_bytes,dst_bytes\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "runtime-batch-guidance-001"

    analysis_calls: list[dict[str, object]] = []
    ranking_calls: list[dict[str, object]] = []
    planner_calls: list[dict[str, object]] = []
    critic_calls: list[dict[str, object]] = []

    semantic_substrate = _build_semantic_substrate(batch_id)
    initial_hypothesis_set = _build_hypothesis_set(
        batch_id,
        analysis_id="analysis-initial-guidance-001",
        summary="Initial dependency framing remains broad and unresolved.",
    )

    def fake_build_initial_semantic_inputs(dataset_path_arg, runtime_batch_id):
        return {
            "overview_summary_min": {"batch_id": runtime_batch_id},
            "partition_context": {"partition_semantics": ["synthetic"]},
        }

    def fake_build_initial_analysis_context(dataset_path_arg):
        return {
            "partition_context_ref": {
                "semantics": ["synthetic"],
                "expected_properties": ["deterministic"],
                "epistemic_warnings": ["bounded"],
                "investigation_guidance": ["stay local"],
            },
            "artifact_framing_refs": [
                {
                    "framing_id": "synthetic-framing",
                    "label": "synthetic framing",
                    "description": "Synthetic runtime framing for orchestration tests.",
                }
            ],
        }

    def fake_run_semantic_extraction(overview_summary_min, partition_context, **kwargs):
        return {
            "component_run": {
                "component": "semantic_extraction",
                "batch_id": batch_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": semantic_substrate,
            "artifact_paths": {
                "component_run_path": str(tmp_path / "semantic_extraction" / "component_run.json"),
            },
        }

    def fake_run_investigation_analysis(semantic_substrate_input, analysis_context_min, analysis_iteration_context_min=None, **kwargs):
        analysis_calls.append(
            {
                "analysis_iteration_context_min": dict(analysis_iteration_context_min or {}),
            }
        )
        return {
            "component_run": {
                "component": "investigation_analysis",
                "batch_id": batch_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": initial_hypothesis_set,
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"investigation_analysis_{len(analysis_calls)}" / "component_run.json"),
            },
        }

    def fake_run_hypothesis_ranking(investigation_hypothesis_set, ranking_state_min, **kwargs):
        ranking_calls.append(deepcopy(ranking_state_min))
        round_id = str(ranking_state_min.get("round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "hypothesis_ranking",
                "batch_id": batch_id,
                "round_id": round_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "selected_hypothesis_ids": ["hyp-1"],
                "deferred_hypothesis_ids": [],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"ranking_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_planner(ranking_decision_min, selected_hypothesis_context, planner_round_context, **kwargs):
        planner_calls.append(deepcopy(planner_round_context))
        round_id = str(planner_round_context.get(
            "round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "planner",
                "batch_id": batch_id,
                "round_id": round_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "planner_strategies": [
                    {
                        "strategy_id": f"strategy-{round_id}",
                        "hypothesis_id": "hyp-1",
                        "strategic_objective": "Bound one local dependency check.",
                        "key_checks": ["local dependency check"],
                        "success_criteria": ["one bounded local check"],
                        "router_constraints": ["stay local"],
                        "tool_capability_refs": ["feature_summary"],
                    }
                ],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"planner_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_router(planner_strategy, router_context_min, **kwargs):
        round_id = str(kwargs.get("round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "router",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "planner_strategy_id": str(planner_strategy.get("strategy_id") or "strategy"),
                "worker_tasks": [
                    {
                        "task_id": f"task-{round_id}",
                        "hypothesis_id": "hyp-1",
                        "task_scope": "feature",
                        "allowed_actions": ["structural_summary"],
                        "local_context_refs": ["runtime-region-e1"],
                        "stop_conditions": ["one check"],
                    }
                ],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"router_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_worker(worker_task, worker_runtime_refs, **kwargs):
        round_id = str(kwargs.get("round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "worker",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
                "result_committed": True,
            },
            "worker_result": {
                "hypothesis_id": "hyp-1",
                "evidence_refs": ["runtime-region-e1"],
                "merged_findings": ["finding"],
                "preserved_contradictions": [],
                "open_gaps": [],
                "update_focus": "stay local",
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"worker_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_aggregation(worker_result_set, **kwargs):
        round_id = str(kwargs.get("round_id") or "unknown_round")
        return {
            "component_run": {
                "component": "aggregation",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
                "handoff_committed": True,
            },
            "aggregation_handoff": {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "merged_findings": ["finding"],
                "evidence_refs": ["runtime-region-e1"],
                "preserved_contradictions": [],
                "open_gaps": [],
                "update_focus": "stay local",
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"aggregation_{round_id}" / "component_run.json"),
            },
        }

    def fake_run_state_manager(canonical_batch_state, aggregation_handoff, **kwargs):
        round_id = str(aggregation_handoff.get("round_id") or "unknown_round")
        updated_batch_state = dict(canonical_batch_state)
        updated_batch_state["state_version"] = int(
            updated_batch_state.get("state_version") or 0) + 1
        return {
            "component_run": {
                "component": "state_manager",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": "hyp-1",
                "status": "ok",
                "validation_ok": True,
                "state_committed": True,
                "new_state_version": updated_batch_state["state_version"],
            },
            "updated_batch_state": updated_batch_state,
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"state_manager_{round_id}" / "component_run.json"),
                "updated_batch_state_path": str(tmp_path / f"state_manager_{round_id}" / "updated_batch_state.json"),
            },
        }

    def fake_run_critic(*args, **kwargs):
        critic_calls.append(dict(kwargs))
        return {
            "component_run": {
                "component": "critic",
                "validation_ok": True,
                "observation_count": 3,
                "observations_committed": True,
            },
            "critic_observations_payload": {
                "batch_id": batch_id,
                "round_id": kwargs.get("round_id", "round-001"),
                "critic_observations": [
                    {
                        "observation_id": "obs-ranking",
                        "observation_type": "productive_active_line",
                        "target_module": "hypothesis_ranking",
                        "priority": "high",
                        "hypothesis_ids": ["hyp-1"],
                        "rationale": "Ranking should keep the productive line in play.",
                        "guidance": "Keep allocating attention to the productive line.",
                        "prompt_snippet": "Keep allocating attention to the productive line.",
                    },
                    {
                        "observation_id": "obs-planner",
                        "observation_type": "productive_active_line",
                        "target_module": "planner",
                        "priority": "high",
                        "hypothesis_ids": ["hyp-1"],
                        "rationale": "Planner should preserve the productive line.",
                        "guidance": "Preserve the productive line in the next investigation strategy.",
                        "prompt_snippet": "Preserve the productive line in the next investigation strategy.",
                    },
                    {
                        "observation_id": "obs-analysis",
                        "observation_type": "productive_active_line",
                        "target_module": "investigation_analysis",
                        "priority": "high",
                        "hypothesis_ids": ["hyp-1"],
                        "rationale": "Analysis should keep the active line visible.",
                        "guidance": "Keep the active line visible in the next interpretation pass.",
                        "prompt_snippet": "Keep the active line visible in the next interpretation pass.",
                    },
                ],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / "critic" / "component_run.json"),
            },
        }

    def fake_run_final_batch_auditor(state_manager_bundle, **kwargs):
        return {
            "component_run": {
                "component": "final_batch_auditor",
                "batch_id": batch_id,
                "status": "ok",
                "validation_ok": True,
                "report_committed": True,
            },
            "debugging_audit_report": {
                "batch_id": batch_id,
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / "final_batch_auditor" / "component_run.json"),
            },
        }

    monkeypatch.setattr(orchestrator, "build_initial_semantic_inputs",
                        fake_build_initial_semantic_inputs)
    monkeypatch.setattr(orchestrator, "build_initial_analysis_context",
                        fake_build_initial_analysis_context)
    monkeypatch.setattr(orchestrator, "run_semantic_extraction",
                        fake_run_semantic_extraction)
    monkeypatch.setattr(
        orchestrator, "run_investigation_analysis", fake_run_investigation_analysis)
    monkeypatch.setattr(orchestrator, "run_final_batch_auditor",
                        fake_run_final_batch_auditor)
    monkeypatch.setattr(
        round_executor, "run_investigation_analysis", fake_run_investigation_analysis)
    monkeypatch.setattr(
        round_executor, "run_hypothesis_ranking", fake_run_hypothesis_ranking)
    monkeypatch.setattr(round_executor, "run_planner", fake_run_planner)
    monkeypatch.setattr(round_executor, "run_router", fake_run_router)
    monkeypatch.setattr(round_executor, "run_worker", fake_run_worker)
    monkeypatch.setattr(round_executor, "run_aggregation",
                        fake_run_aggregation)
    monkeypatch.setattr(round_executor, "run_state_manager",
                        fake_run_state_manager)
    monkeypatch.setattr(round_executor, "run_critic", fake_run_critic)
    monkeypatch.setattr(round_executor, "build_critic_guidance_context", lambda previous_round_manifest: {
        "source_round_id": "round-001",
        "source_critic_run_path": str(tmp_path / "critic" / "component_run.json"),
        "observations": [
            {
                "observation_id": "obs-ranking",
                "observation_type": "productive_active_line",
                "target_module": "hypothesis_ranking",
                "priority": "high",
                "hypothesis_ids": ["hyp-1"],
                "guidance": "Keep allocating attention to the productive line.",
                "prompt_snippet": "Keep allocating attention to the productive line.",
            },
            {
                "observation_id": "obs-planner",
                "observation_type": "productive_active_line",
                "target_module": "planner",
                "priority": "high",
                "hypothesis_ids": ["hyp-1"],
                "guidance": "Preserve the productive line in the next investigation strategy.",
                "prompt_snippet": "Preserve the productive line in the next investigation strategy.",
            },
            {
                "observation_id": "obs-analysis",
                "observation_type": "productive_active_line",
                "target_module": "investigation_analysis",
                "priority": "high",
                "hypothesis_ids": ["hyp-1"],
                "guidance": "Keep the active line visible in the next interpretation pass.",
                "prompt_snippet": "Keep the active line visible in the next interpretation pass.",
            },
        ],
        "per_module": {
            "hypothesis_ranking": {
                "target_module": "hypothesis_ranking",
                "source_round_id": "round-001",
                "source_critic_run_path": str(tmp_path / "critic" / "component_run.json"),
                "observations": [
                    {
                        "observation_id": "obs-ranking",
                        "observation_type": "productive_active_line",
                        "target_module": "hypothesis_ranking",
                        "priority": "high",
                        "hypothesis_ids": ["hyp-1"],
                        "guidance": "Keep allocating attention to the productive line.",
                        "prompt_snippet": "Keep allocating attention to the productive line.",
                    }
                ],
                "prompt_snippets": ["Keep allocating attention to the productive line."],
            },
            "planner": {
                "target_module": "planner",
                "source_round_id": "round-001",
                "source_critic_run_path": str(tmp_path / "critic" / "component_run.json"),
                "observations": [
                    {
                        "observation_id": "obs-planner",
                        "observation_type": "productive_active_line",
                        "target_module": "planner",
                        "priority": "high",
                        "hypothesis_ids": ["hyp-1"],
                        "guidance": "Preserve the productive line in the next investigation strategy.",
                        "prompt_snippet": "Preserve the productive line in the next investigation strategy.",
                    }
                ],
                "prompt_snippets": ["Preserve the productive line in the next investigation strategy."],
            },
            "investigation_analysis": {
                "target_module": "investigation_analysis",
                "source_round_id": "round-001",
                "source_critic_run_path": str(tmp_path / "critic" / "component_run.json"),
                "observations": [
                    {
                        "observation_id": "obs-analysis",
                        "observation_type": "productive_active_line",
                        "target_module": "investigation_analysis",
                        "priority": "high",
                        "hypothesis_ids": ["hyp-1"],
                        "guidance": "Keep the active line visible in the next interpretation pass.",
                        "prompt_snippet": "Keep the active line visible in the next interpretation pass.",
                    }
                ],
                "prompt_snippets": ["Keep the active line visible in the next interpretation pass."],
            },
        },
    })

    bundle = orchestrator.run_phase3a_batch(
        dataset_path,
        batch_id=batch_id,
        model_name="gpt-4.1-mini",
        max_rounds=2,
        enable_critic=True,
        log_dir=tmp_path / "runtime_logs",
    )

    assert bundle["component_run"]["status"] == "completed"
    assert critic_calls
    assert analysis_calls[1]["analysis_iteration_context_min"]["critic_guidance"][
        0] == "Keep the active line visible in the next interpretation pass."
    assert ranking_calls[1]["critic_guidance"][0] == "Keep allocating attention to the productive line."
    assert planner_calls[1]["critic_guidance"][0] == "Preserve the productive line in the next investigation strategy."


def test_execute_round_waits_for_all_hypothesis_aggregations_before_state_updates(
    tmp_path,
    monkeypatch,
):
    dataset_path = tmp_path / "partition.csv"
    dataset_path.write_text(
        "Label,src_bytes,dst_bytes\n0,1,2\n1,3,4\n", encoding="utf-8")
    batch_id = "runtime-batch-002"
    round_id = "round-001"
    event_log: list[str] = []

    semantic_substrate = _build_semantic_substrate(batch_id)
    hypothesis_set = _build_multi_hypothesis_set(
        batch_id, analysis_id="analysis-initial-002")
    canonical_batch_state = init_canonical_batch_state(
        batch_id=batch_id,
        structural_substrate=semantic_substrate,
        hypothesis_set=hypothesis_set,
    ).to_dict()

    def fake_run_hypothesis_ranking(investigation_hypothesis_set, ranking_state_min, **kwargs):
        return {
            "component_run": {
                "component": "hypothesis_ranking",
                "batch_id": batch_id,
                "round_id": round_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "selected_hypothesis_ids": ["hyp-1", "hyp-2"],
                "deferred_hypothesis_ids": [],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / "ranking" / "component_run.json"),
            },
        }

    def fake_run_planner(ranking_decision_min, selected_hypothesis_context, planner_round_context, **kwargs):
        return {
            "component_run": {
                "component": "planner",
                "batch_id": batch_id,
                "round_id": round_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "planner_strategies": [
                    {
                        "strategy_id": "strategy-hyp-1",
                        "hypothesis_id": "hyp-1",
                        "strategic_objective": "Bound one local dependency check.",
                        "key_checks": ["local dependency check"],
                        "success_criteria": ["one bounded local check"],
                        "router_constraints": ["stay local"],
                        "tool_capability_refs": ["feature_relation"],
                    },
                    {
                        "strategy_id": "strategy-hyp-2",
                        "hypothesis_id": "hyp-2",
                        "strategic_objective": "Bound one local shortcut check.",
                        "key_checks": ["local shortcut check"],
                        "success_criteria": ["one bounded local check"],
                        "router_constraints": ["stay local"],
                        "tool_capability_refs": ["shortcut_analysis"],
                    },
                ],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / "planner" / "component_run.json"),
            },
        }

    def fake_run_router(planner_strategy, router_context_min, **kwargs):
        hypothesis_id = str(planner_strategy.get(
            "hypothesis_id") or "unknown_hypothesis")
        event_log.append(f"router:{hypothesis_id}")
        return {
            "component_run": {
                "component": "router",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "status": "ok",
                "validation_ok": True,
            },
            "parsed_output": {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "planner_strategy_id": str(planner_strategy.get("strategy_id") or "strategy"),
                "worker_tasks": [
                    {
                        "task_id": f"task-{hypothesis_id}",
                        "hypothesis_id": hypothesis_id,
                        "task_scope": f"bounded scope for {hypothesis_id}",
                        "allowed_actions": ["shortcut_verification"],
                        "local_context_refs": ["runtime-region-e1"],
                        "stop_conditions": ["one bounded local check"],
                    }
                ],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"router_{hypothesis_id}" / "component_run.json"),
            },
        }

    def fake_run_worker(worker_task, worker_runtime_refs, **kwargs):
        hypothesis_id = str(worker_task.get(
            "hypothesis_id") or "unknown_hypothesis")
        event_log.append(f"worker:{hypothesis_id}")
        return {
            "component_run": {
                "component": "worker",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "status": "ok",
                "validation_ok": True,
                "result_committed": True,
            },
            "worker_result": {
                "task_id": str(worker_task.get("task_id") or "unknown_task"),
                "hypothesis_id": hypothesis_id,
                "status": "completed",
                "findings": [f"finding-{hypothesis_id}"],
                "evidence_refs": [f"evidence-{hypothesis_id}"],
                "contradictions": [],
                "limitations": [],
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"worker_{hypothesis_id}" / "component_run.json"),
            },
        }

    def fake_run_aggregation(worker_result_set, expected_task_ids=None, source_run_dirs=None, **kwargs):
        hypothesis_id = str(worker_result_set.get(
            "hypothesis_id") or "unknown_hypothesis")
        event_log.append(f"aggregation:{hypothesis_id}")
        return {
            "component_run": {
                "component": "aggregation",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "status": "ok",
                "validation_ok": True,
                "handoff_committed": True,
            },
            "aggregation_handoff": {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "merged_findings": [f"merged-{hypothesis_id}"],
                "evidence_refs": [f"evidence-{hypothesis_id}"],
                "preserved_contradictions": [],
                "open_gaps": [f"gap-{hypothesis_id}"],
                "update_focus": f"focus-{hypothesis_id}",
            },
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"aggregation_{hypothesis_id}" / "component_run.json"),
            },
        }

    def fake_run_state_manager(canonical_batch_state_arg, aggregation_handoff, expected_prior_state_version=None, **kwargs):
        hypothesis_id = str(aggregation_handoff.get(
            "hypothesis_id") or "unknown_hypothesis")
        event_log.append(f"state_manager:{hypothesis_id}")
        updated_batch_state = deepcopy(canonical_batch_state_arg)
        updated_batch_state["state_version"] = int(
            updated_batch_state.get("state_version") or 0) + 1
        return {
            "component_run": {
                "component": "state_manager",
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "status": "ok",
                "validation_ok": True,
                "state_committed": True,
                "new_state_version": updated_batch_state["state_version"],
            },
            "updated_batch_state": updated_batch_state,
            "artifact_paths": {
                "component_run_path": str(tmp_path / f"state_manager_{hypothesis_id}" / "component_run.json"),
                "updated_batch_state_path": str(tmp_path / f"state_manager_{hypothesis_id}" / "updated_batch_state.json"),
            },
        }

    monkeypatch.setattr(
        round_executor, "run_hypothesis_ranking", fake_run_hypothesis_ranking)
    monkeypatch.setattr(round_executor, "run_planner", fake_run_planner)
    monkeypatch.setattr(round_executor, "run_router", fake_run_router)
    monkeypatch.setattr(round_executor, "run_worker", fake_run_worker)
    monkeypatch.setattr(round_executor, "run_aggregation",
                        fake_run_aggregation)
    monkeypatch.setattr(round_executor, "run_state_manager",
                        fake_run_state_manager)

    round_result = round_executor.execute_round(
        batch_id=batch_id,
        round_id=round_id,
        round_index=1,
        dataset_path=dataset_path,
        semantic_bundle={"parsed_output": semantic_substrate},
        initial_hypothesis_bundle={"parsed_output": hypothesis_set},
        analysis_context_min={},
        canonical_batch_state=canonical_batch_state,
        model_name="gpt-4.1-mini",
        temperature=0.0,
        enable_critic=False,
        analysis_mode="initial",
    )

    aggregation_indices = [index for index, value in enumerate(
        event_log) if value.startswith("aggregation:")]
    state_manager_indices = [index for index, value in enumerate(
        event_log) if value.startswith("state_manager:")]

    assert round_result["round_manifest"].status == "completed"
    assert len(round_result["aggregation_bundles"]) == 2
    assert len(round_result["state_manager_bundles"]) == 2
    assert aggregation_indices
    assert state_manager_indices
    assert max(aggregation_indices) < min(state_manager_indices)
    assert round_result["global_aggregation_summary"]["selected_hypothesis_ids"] == [
        "hyp-1", "hyp-2"]
    assert [record["hypothesis_id"] for record in round_result["global_aggregation_summary"]
            ["source_hypothesis_records"]] == ["hyp-1", "hyp-2"]
    assert round_result["global_aggregation_summary"]["component_run"]["component"] == "inter_hypothesis_aggregation"
    assert round_result["global_aggregation_summary"]["component_run"]["validation_ok"] is True
    assert round_result["global_aggregation_summary"]["validation_report"]["ok"] is True
