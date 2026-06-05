import json
from pathlib import Path

from aggregation.contracts import build_aggregation_handoff
from final_batch_auditor.runner import run_final_batch_auditor
from final_batch_auditor.runtime_artifacts import load_final_batch_auditor_bundle
from investigation_analysis.contracts import build_hypothesis, build_hypothesis_set
from semantic_extraction.contracts import (
    build_feature_scope,
    build_locality_descriptor,
    build_region,
    build_semantic_substrate,
)
from state.store import init_canonical_batch_state
from state_manager.runner import run_state_manager


BATCH_ID = "final-audit-batch-001"
HYPOTHESIS_ID = "hyp-final-1"


def _build_initial_state() -> dict[str, object]:
    semantic_substrate = build_semantic_substrate(
        substrate_id="final-substrate-001",
        batch_id=BATCH_ID,
        compressed_regions=[
            build_region(
                region_id="final-region-1",
                region_kind="dependency_region",
                status="broad_unvalidated",
                summary="src_bytes and dst_bytes remain tightly coupled in the batch slice.",
                feature_scope=build_feature_scope(
                    features=["src_bytes", "dst_bytes"],
                    feature_groups=["flow_size"],
                    locality=build_locality_descriptor(
                        scope_type="partition_global",
                        scope_value=BATCH_ID,
                        localized=False,
                        notes=["Global dependency signal."],
                    ),
                ),
                evidence_refs=["final-region-e1"],
            )
        ],
        preserved_weak_signals=[],
        contradictions=[],
        unresolved_tensions=[],
    )
    hypothesis_set = build_hypothesis_set(
        analysis_id="final-analysis-001",
        batch_id=BATCH_ID,
        hypotheses=[
            build_hypothesis(
                hypothesis_id=HYPOTHESIS_ID,
                summary="The dependency may indicate a shortcut-compatible dependency framing.",
                evidence_refs=["final-region-e1"],
                open_questions=[
                    "Need to verify whether the dependency stays local."],
            )
        ],
    )
    return init_canonical_batch_state(
        batch_id=BATCH_ID,
        structural_substrate=semantic_substrate,
        hypothesis_set=hypothesis_set,
    ).to_dict()


def _build_handoff(
    *,
    round_id: str,
    evidence_ref: str,
    finding: str,
    contradiction: str,
    open_gap: str,
    update_focus: str,
) -> dict[str, object]:
    return build_aggregation_handoff(
        batch_id=BATCH_ID,
        round_id=round_id,
        hypothesis_id=HYPOTHESIS_ID,
        merged_findings=[finding],
        evidence_refs=[evidence_ref],
        preserved_contradictions=[contradiction],
        open_gaps=[open_gap],
        update_focus=update_focus,
    )


def _run_state_manager_round(
    *,
    tmp_path: Path,
    prior_state: dict[str, object],
    handoff: dict[str, object],
    summary: str,
    status: str,
    evidence_refs: list[str],
    preserved_contradictions: list[str],
    open_gaps: list[str],
    merged_findings: list[str],
    update_focus: str,
    log_dir_name: str,
) -> dict[str, object]:
    responses = iter(
        [
            json.dumps(
                {
                    "state_delta_record": {
                        "batch_id": BATCH_ID,
                        "round_id": handoff["round_id"],
                        "hypothesis_id": HYPOTHESIS_ID,
                        "summary": summary,
                        "status": status,
                        "evidence_refs": evidence_refs,
                        "preserved_contradictions": preserved_contradictions,
                        "open_gaps": open_gaps,
                        "merged_findings": merged_findings,
                        "update_focus": update_focus,
                        "applied_updates": [
                            {
                                "field": "summary",
                                "reason": "Committed evidence updated the final interpretive framing.",
                            }
                        ],
                    }
                }
            )
        ]
    )

    return run_state_manager(
        prior_state,
        handoff,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / log_dir_name),
    )


def _build_aggregation_bundle(
    *,
    round_id: str,
    evidence_ref: str,
    overlap_group_count: int,
) -> dict[str, object]:
    return {
        "component_run": {
            "component": "aggregation",
            "batch_id": BATCH_ID,
            "round_id": round_id,
            "hypothesis_id": HYPOTHESIS_ID,
            "status": "ok",
            "validation_ok": True,
            "handoff_committed": True,
        },
        "artifact_paths": {
            "worker_result_set_path": f"aggregation/{round_id}/worker_result_set.json",
            "normalized_inputs_path": f"aggregation/{round_id}/normalized_inputs.json",
            "aggregation_handoff_path": f"aggregation/{round_id}/aggregation_handoff.json",
            "overlap_diagnostics_path": f"aggregation/{round_id}/overlap_diagnostics.json",
            "validation_report_path": f"aggregation/{round_id}/validation_report.json",
            "runtime_metrics_path": f"aggregation/{round_id}/runtime_metrics.json",
        },
        "worker_result_set": {
            "worker_results": [
                {
                    "task_id": f"task-{round_id}-1",
                    "evidence_refs": [evidence_ref],
                }
            ]
        },
        "normalized_inputs": {},
        "overlap_diagnostics": [
            {
                "overlap_group_id": f"overlap-{round_id}-{index}",
                "shared_evidence_refs": [evidence_ref],
            }
            for index in range(overlap_group_count)
        ],
        "aggregation_handoff": _build_handoff(
            round_id=round_id,
            evidence_ref=evidence_ref,
            finding=f"Finding for {round_id} remained visible in the localized slice.",
            contradiction=f"Contradiction for {round_id} remains unresolved.",
            open_gap=f"Open gap for {round_id} remains unresolved.",
            update_focus=f"Keep {round_id} focused on contradiction-preserving closure checks.",
        ),
        "validation_report": {"ok": True},
        "runtime_metrics": {"overlap_group_count": overlap_group_count},
    }


def _build_critic_bundle(*, round_id: str, evidence_ref: str) -> dict[str, object]:
    return {
        "component_run": {
            "component": "critic",
            "batch_id": BATCH_ID,
            "round_id": round_id,
            "status": "ok",
            "validation_ok": True,
        },
        "artifact_paths": {
            "critic_observations_path": f"critic/{round_id}/critic_observations.json",
        },
        "critic_observations": {
            "batch_id": BATCH_ID,
            "round_id": round_id,
            "critic_observations": [
                {
                    "observation_id": "obs-final-001",
                    "observation_type": "productive_active_line",
                    "target_module": "planner",
                    "priority": "medium",
                    "hypothesis_ids": ["hyp-final-1"],
                    "rationale": "Planner narrowed too quickly onto one contradiction path.",
                    "guidance": "Keep contradiction pressure visible without broadening scope prematurely.",
                    "prompt_snippet": "Keep contradiction pressure visible without broadening scope prematurely.",
                }
            ],
        },
        "validation_report": {"ok": True},
        "runtime_metrics": {"observation_count": 1},
    }


def _build_multi_round_history(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    round_one_bundle = _run_state_manager_round(
        tmp_path=tmp_path,
        prior_state=_build_initial_state(),
        handoff=_build_handoff(
            round_id="round-001",
            evidence_ref="final-task-step-01",
            finding="The dependency remained visible in the first local verification slice.",
            contradiction="The first local slice still conflicts with the broader dependency framing.",
            open_gap="Need one counter-check after the first local verification.",
            update_focus="Carry the contradiction forward without collapsing the framing.",
        ),
        summary="The first round kept the dependency framing active while preserving a contradiction.",
        status="active",
        evidence_refs=["final-region-e1", "final-task-step-01"],
        preserved_contradictions=[
            "The first local slice still conflicts with the broader dependency framing."
        ],
        open_gaps=[
            "Need to verify whether the dependency stays local.",
            "Need one counter-check after the first local verification.",
        ],
        merged_findings=[
            "The dependency remained visible in the first local verification slice."],
        update_focus="Carry the contradiction forward without collapsing the framing.",
        log_dir_name="state_manager_round_001",
    )
    round_two_bundle = _run_state_manager_round(
        tmp_path=tmp_path,
        prior_state=dict(round_one_bundle["updated_batch_state"]),
        handoff=_build_handoff(
            round_id="round-002",
            evidence_ref="final-task-step-02",
            finding="The dependency remained visible in the second local verification slice.",
            contradiction="The final local slice still conflicts with the broader dependency framing.",
            open_gap="One closure gap still remains in the final state.",
            update_focus="Finish with contradiction-preserving auditability rather than forced closure.",
        ),
        summary="The second round strengthened local support while leaving one contradiction and one closure gap unresolved.",
        status="active",
        evidence_refs=["final-region-e1",
                       "final-task-step-01", "final-task-step-02"],
        preserved_contradictions=[
            "The first local slice still conflicts with the broader dependency framing.",
            "The final local slice still conflicts with the broader dependency framing."
        ],
        open_gaps=[
            "Need to verify whether the dependency stays local.",
            "Need one counter-check after the first local verification.",
            "One closure gap still remains in the final state.",
        ],
        merged_findings=[
            "The dependency remained visible in the first local verification slice.",
            "The dependency remained visible in the second local verification slice.",
        ],
        update_focus="Finish with contradiction-preserving auditability rather than forced closure.",
        log_dir_name="state_manager_round_002",
    )
    return round_one_bundle, round_two_bundle


def test_run_final_batch_auditor_returns_valid_bundle_and_artifacts(tmp_path: Path):
    round_one_bundle, round_two_bundle = _build_multi_round_history(tmp_path)
    batch_component_bundles = {
        "state_manager": [round_one_bundle, round_two_bundle],
        "aggregation": [
            _build_aggregation_bundle(
                round_id="round-001",
                evidence_ref="final-task-step-01",
                overlap_group_count=1,
            ),
            _build_aggregation_bundle(
                round_id="round-002",
                evidence_ref="final-task-step-02",
                overlap_group_count=2,
            ),
        ],
        "critic": [
            _build_critic_bundle(
                round_id="round-001",
                evidence_ref="final-task-step-01",
            )
        ],
    }
    responses = iter(
        [
            json.dumps(
                {
                    "debugging_audit_report": {
                        "batch_id": BATCH_ID,
                        "trajectory_summary": "Across two committed rounds, investigation pressure stayed concentrated on one dependency framing while preserving one contradiction and visible overlap pressure.",
                        "hypothesis_summary": "The main hypothesis remained active and gained local support, but the final state still preserved one contradiction and one closure gap instead of forcing deterministic resolution.",
                        "surviving_contradictions": [
                            "The final local slice still conflicts with the broader dependency framing."
                        ],
                        "open_pressures": [
                            "One closure gap still remains in the final state.",
                            "Overlap pressure remained visible in the second aggregation diagnostics."
                        ],
                        "failure_summary": "The architecture remained traceable, but breadth stayed narrow relative to the contradiction pressure that survived into the final state.",
                        "traceability_refs": [
                            "final-region-e1",
                            "final-task-step-02",
                            str(round_two_bundle["artifact_paths"]
                                ["updated_batch_state_path"]),
                        ],
                    }
                }
            )
        ]
    )

    bundle = run_final_batch_auditor(
        round_two_bundle,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "final_batch_auditor_runs"),
        is_final_batch=True,
        batch_component_bundles=batch_component_bundles,
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["validation_ok"] is True
    assert bundle["component_run"]["report_committed"] is True
    assert bundle["validation_report"]["ok"] is True
    assert bundle["validation_report"]["terminal_gate"]["status"] == "confirmed_terminal_batch"
    assert len(bundle["final_audit_input"]["round_artifact_refs"]) >= 6
    assert len(bundle["final_audit_input"]["hypothesis_history_refs"]) >= 2
    assert len(bundle["round_history_summary"]) == 2
    assert bundle["debugging_audit_report"]["batch_id"] == BATCH_ID
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]
                ["debugging_audit_report_path"]).exists()

    loaded = load_final_batch_auditor_bundle(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["debugging_audit_report"]["batch_id"] == BATCH_ID
    assert loaded["component_run"]["audit_mode"] == "authoritative"


def test_run_final_batch_auditor_rejects_non_terminal_batch_request(tmp_path: Path):
    _, round_two_bundle = _build_multi_round_history(tmp_path)

    bundle = run_final_batch_auditor(
        round_two_bundle,
        llm_callable=lambda prompt_text: "{}",
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "final_batch_auditor_runs"),
        is_final_batch=False,
        batch_component_bundles={"state_manager": [round_two_bundle]},
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["component_run"]["report_committed"] is False
    assert bundle["debugging_audit_report"] == {}
    assert bundle["validation_report"]["terminal_gate"]["status"] == "rejected_non_terminal_batch"


def test_run_final_batch_auditor_flags_future_facing_report_without_blocking(tmp_path: Path):
    round_one_bundle, round_two_bundle = _build_multi_round_history(tmp_path)
    responses = iter(
        [
            json.dumps(
                {
                    "debugging_audit_report": {
                        "batch_id": BATCH_ID,
                        "trajectory_summary": "Across the completed rounds, one contradiction remained visible.",
                        "hypothesis_summary": "The final hypothesis remained active with one unresolved contradiction.",
                        "surviving_contradictions": [
                            "The final local slice still conflicts with the broader dependency framing."
                        ],
                        "open_pressures": [
                            "One closure gap still remains in the final state."
                        ],
                        "failure_summary": "Next round should rerank the hypothesis and execute one more tool call.",
                        "traceability_refs": ["final-region-e1", "final-task-step-02"],
                    }
                }
            )
        ]
    )

    bundle = run_final_batch_auditor(
        round_two_bundle,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "final_batch_auditor_runs"),
        is_final_batch=True,
        batch_component_bundles={"state_manager": [
            round_one_bundle, round_two_bundle]},
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["debugging_audit_report_validation"]["ok"] is True
    assert any(
        "Semantic language flags detected" in warning["message"]
        for warning in bundle["validation_report"]["debugging_audit_report_validation"]["warnings"]
    )
    assert any(
        hit["code"] in {"future_round_guidance", "control_language"}
        for hit in bundle["validation_report"]["debugging_audit_report_validation"]["forbidden_language_hits"]
    )
