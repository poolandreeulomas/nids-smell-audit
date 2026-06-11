import json
from pathlib import Path

from aggregation.contracts import build_aggregation_handoff
from investigation_analysis.contracts import build_hypothesis, build_hypothesis_set
from semantic_extraction.contracts import (
    build_feature_scope,
    build_locality_descriptor,
    build_region,
    build_semantic_substrate,
)
from state.store import init_canonical_batch_state
from state_manager.runner import run_state_manager
from state_manager.runtime_artifacts import load_state_manager_bundle


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
                open_questions=[
                    "Need to verify whether the dependency stays local."],
            ),
            build_hypothesis(
                hypothesis_id="hyp-2",
                summary="The dependency may still hide a representation-sensitive effect.",
                evidence_refs=["region-e1"],
                open_questions=[
                    "Need to compare the signal across partitions."],
            ),
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
        preserved_contradiction_ids=["contr_0"],
        contradiction_lookup={
            "contr_0": "Current local evidence still conflicts with the broader dependency framing.",
        },
        open_gaps=["Need one more counter-check before closing the framing."],
        update_focus="Carry forward the dependency framing without collapsing the remaining contradiction.",
    )


def test_run_state_manager_returns_valid_bundle_and_artifacts(tmp_path: Path):
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
                            },
                            {
                                "field": "status",
                                "reason": "The hypothesis should remain active rather than unresolved after the new local evidence."
                            },
                        ],
                    }
                }
            )
        ]
    )

    bundle = run_state_manager(
        _build_initial_state(),
        _build_aggregation_handoff(),
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["state_committed"] is True
    assert bundle["validation_report"]["ok"] is True
    assert bundle["state_update_result"]["previous_state_version"] == 1
    assert bundle["state_update_result"]["new_state_version"] == 2
    assert bundle["updated_batch_state"]["state_version"] == 2
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["state_update_result_path"]).exists()
    assert bundle["component_run"]["request_id"].startswith("state_manager_")
    assert bundle["component_run"]["prompt_version"] == "phase3a.state_manager.prompt.v1"

    loaded = load_state_manager_bundle(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["state_update_result"]["new_state_version"] == 2
    assert loaded["updated_batch_state"]["batch_id"] == "batch-001"
    assert loaded["runtime_metrics"]["applied_update_count"] == 2
    assert loaded["validation_report"]["request_id"] == bundle["component_run"]["request_id"]


def test_run_state_manager_warns_on_long_update_focus_and_continues(tmp_path: Path):
    long_update_focus = (
        "Carry forward the dependency framing without collapsing the remaining contradiction. "
        "This guidance is intentionally a little longer than the preferred display target."
    )
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
                        "update_focus": long_update_focus,
                        "applied_updates": [
                            {
                                "field": "summary",
                                "reason": "The aggregation handoff strengthened the current framing without resolving the contradiction."
                            },
                            {
                                "field": "status",
                                "reason": "The hypothesis should remain active rather than unresolved after the new local evidence."
                            },
                        ],
                    }
                }
            )
        ]
    )

    handoff = _build_aggregation_handoff()
    handoff["update_focus"] = long_update_focus

    bundle = run_state_manager(
        _build_initial_state(),
        handoff,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["state_committed"] is True
    assert bundle["validation_report"]["ok"] is True
    assert bundle["validation_report"]["handoff_input_validation"]["ok"] is True
    assert bundle["validation_report"]["state_delta_validation"]["ok"] is True
    assert any(
        warning["field"] == "update_focus"
        for warning in bundle["validation_report"]["handoff_input_validation"]["warnings"]
    )
    assert any(
        warning["field"] == "update_focus"
        for warning in bundle["validation_report"]["state_delta_validation"]["warnings"]
    )


def test_run_state_manager_allows_explicit_resolution_of_continuity_lists(tmp_path: Path):
    responses = iter(
        [
            json.dumps(
                {
                    "state_delta_record": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "hypothesis_id": "hyp-1",
                        "summary": "The local verification narrowed the framing and resolved the prior contradiction, but one broader locality check remains open.",
                        "status": "active",
                        "evidence_refs": ["region-e1", "task-hyp-1-1_step_01"],
                        "preserved_contradictions": [],
                        "open_gaps": [
                            "Need to verify whether the dependency stays local."
                        ],
                        "merged_findings": [
                            "The local verification narrowed the framing to a localized effect."
                        ],
                        "update_focus": "Preserve the active framing while carrying forward only the remaining locality check.",
                        "applied_updates": [
                            {
                                "field": "preserved_contradictions",
                                "reason": "The new local evidence resolved the previously preserved contradiction."
                            },
                            {
                                "field": "open_gaps",
                                "reason": "One round-specific check is resolved, so only the broader locality gap remains."
                            },
                            {
                                "field": "merged_findings",
                                "reason": "The finding list should reflect the refined local interpretation after the update."
                            },
                        ],
                    }
                }
            )
        ]
    )

    bundle = run_state_manager(
        _build_initial_state(),
        _build_aggregation_handoff(),
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )

    updated_hypothesis = bundle["updated_batch_state"]["interpretive_hypotheses"][0]
    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["ok"] is True
    assert updated_hypothesis["preserved_contradictions"] == []
    assert updated_hypothesis["open_gaps"] == [
        "Need to verify whether the dependency stays local."
    ]
    assert updated_hypothesis["merged_findings"] == [
        "The local verification narrowed the framing to a localized effect."
    ]


def test_run_state_manager_rejects_invalid_handoff_before_calling_llm(tmp_path: Path):
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return "{}"

    handoff = _build_aggregation_handoff()
    handoff["batch_id"] = "batch-999"

    bundle = run_state_manager(
        _build_initial_state(),
        handoff,
        llm_callable=_unexpected_call,
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["handoff_input_validation"]["ok"] is False
    assert bundle["prompt_text"] == ""
    assert llm_called["value"] is False


def test_run_state_manager_fails_closed_on_invalid_state_delta(tmp_path: Path):
    responses = iter(
        [
            json.dumps(
                {
                    "state_delta_record": {
                        "batch_id": "batch-001",
                        "round_id": "round-001",
                        "hypothesis_id": "hyp-1",
                        "summary": "The dependency framing should move forward quickly.",
                        "status": "active",
                        "evidence_refs": ["invented-evidence-ref"],
                        "preserved_contradictions": [],
                        "open_gaps": [],
                        "merged_findings": [
                            "The dependency signal remained visible in the targeted local slice."
                        ],
                        "update_focus": "Carry forward the dependency framing quickly.",
                        "applied_updates": [
                            {
                                "field": "summary",
                                "reason": "The aggregation handoff points the hypothesis toward quick closure."
                            }
                        ],
                    }
                }
            )
        ]
    )

    bundle = run_state_manager(
        _build_initial_state(),
        _build_aggregation_handoff(),
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["component_run"]["state_committed"] is False
    assert bundle["updated_batch_state"] == {}
    assert bundle["state_update_result"] == {}
    assert bundle["validation_report"]["state_delta_validation"]["ok"] is False


def test_run_state_manager_rejects_mismatched_expected_prior_state_version(tmp_path: Path):
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return "{}"

    bundle = run_state_manager(
        _build_initial_state(),
        _build_aggregation_handoff(),
        llm_callable=_unexpected_call,
        expected_prior_state_version=2,
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["state_input_validation"]["ok"] is False
    assert bundle["prompt_text"] == ""
    assert llm_called["value"] is False
    assert any(
        error["field"] == "state_version"
        for error in bundle["validation_report"]["state_input_validation"]["errors"]
    )
