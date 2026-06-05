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


def _build_initial_state() -> dict[str, object]:
    semantic_substrate = build_semantic_substrate(
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
    hypothesis_set = build_hypothesis_set(
        analysis_id="analysis-001",
        batch_id="batch-001",
        hypotheses=[
            build_hypothesis(
                hypothesis_id="hyp-1",
                summary="The dependency may reflect a shortcut-compatible framing.",
                evidence_refs=["region-e1"],
                open_questions=[
                    "Need to verify whether the dependency stays local."],
            )
        ],
    )
    return init_canonical_batch_state(
        batch_id="batch-001",
        structural_substrate=semantic_substrate,
        hypothesis_set=hypothesis_set,
    ).to_dict()


def _build_aggregation_handoff() -> dict[str, object]:
    return build_aggregation_handoff(
        batch_id="batch-001",
        round_id="round-001",
        hypothesis_id="hyp-1",
        merged_findings=[
            "The dependency signal remained visible in the targeted local slice."],
        evidence_refs=["task-hyp-1-1_step_01"],
        preserved_contradictions=[
            "Current local evidence still conflicts with the broader dependency framing."
        ],
        open_gaps=["Need one more counter-check before closing the framing."],
        update_focus="Carry forward the dependency framing without collapsing the remaining contradiction.",
    )


def _build_state_manager_bundle(tmp_path: Path) -> dict[str, object]:
    state_manager_responses = iter(
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
        llm_callable=lambda prompt_text: next(state_manager_responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager_runs"),
    )


def _run_critic(tmp_path: Path, response_payload: dict[str, object], *, is_final_round: bool = False) -> dict[str, object]:
    state_manager_bundle = _build_state_manager_bundle(tmp_path)
    responses = iter([json.dumps(response_payload)])
    return run_critic(
        state_manager_bundle,
        llm_callable=lambda prompt_text: next(responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "critic_runs"),
        round_component_bundles={"planner": {}, "hypothesis_ranking": {}},
        is_final_round=is_final_round,
    )


def test_run_critic_persists_observations_payload(tmp_path: Path):
    bundle = _run_critic(
        tmp_path,
        {
            "batch_id": "batch-001",
            "round_id": "round-001",
            "critic_observations": [
                {
                    "observation_id": "obs_001",
                    "observation_type": "productive_active_line",
                    "target_module": "planner",
                    "priority": "high",
                    "hypothesis_ids": ["hyp-1"],
                    "rationale": "The current line is still producing useful state change.",
                    "guidance": "Human-readable note for review.",
                    "prompt_snippet": "Consider continuing the productive line before widening scope.",
                }
            ],
        },
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["component_run"]["observation_count"] == 1
    assert bundle["component_run"]["observations_committed"] is True
    assert bundle["runtime_metrics"]["observation_count"] == 1
    assert bundle["runtime_metrics"]["observations_committed"] is True
    assert bundle["validation_report"]["critic_observations_validation"]["ok"] is True
    assert "SEMANTIC_LANDSCAPE:" in bundle["prompt_text"]
    assert "INVESTIGATION_HISTORY (PRIMARY):" in bundle["prompt_text"]
    assert Path(bundle["artifact_paths"]["critic_observations_path"]).exists()
    assert Path(bundle["artifact_paths"]["critic_observations_path"]).exists()

    loaded = load_critic_bundle(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["critic_observations"]["batch_id"] == "batch-001"
    assert loaded["critic_observations"]["critic_observations"][0]["target_module"] == "planner"
    assert loaded["critic_observations"]["critic_observations"][0]["observation_id"] == "obs_001"


def test_run_critic_skips_final_round_before_calling_llm(tmp_path: Path):
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return "{}"

    state_manager_bundle = _build_state_manager_bundle(tmp_path)
    bundle = run_critic(
        state_manager_bundle,
        llm_callable=_unexpected_call,
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "critic_runs"),
        is_final_round=True,
    )

    assert bundle["component_run"]["status"] == "skipped"
    assert bundle["component_run"]["observation_count"] == 0
    assert bundle["validation_report"]["ok"] is True
    assert bundle["validation_report"]["final_round_gate"]["status"] == "skipped_final_round"
    assert bundle["prompt_text"] == ""
    assert bundle["critic_observations_payload"] == {}
    assert llm_called["value"] is False


def test_run_critic_rejects_unknown_hypothesis_id(tmp_path: Path):
    bundle = _run_critic(
        tmp_path,
        {
            "batch_id": "batch-001",
            "round_id": "round-001",
            "critic_observations": [
                {
                    "observation_id": "obs_001",
                    "observation_type": "productive_active_line",
                    "target_module": "planner",
                    "priority": "high",
                    "hypothesis_ids": ["missing-hypothesis"],
                    "rationale": "The line still seems productive.",
                    "guidance": "Review the active line.",
                    "prompt_snippet": "Consider the active line again.",
                }
            ],
        },
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["critic_observations_validation"]["ok"] is False
    assert any(
        "Unknown hypothesis_id" in error["message"]
        for error in bundle["validation_report"]["critic_observations_validation"]["errors"]
    )


def test_run_critic_normalizes_legacy_payloads(tmp_path: Path):
    bundle = _run_critic(
        tmp_path,
        {
            "batch_id": "batch-001",
            "round_id": "round-001",
            "critic_observations": [
                {
                    "observation_id": "obs_legacy_001",
                    "observation_type": "productive_active_line",
                    "target_module": "planner",
                    "priority": "high",
                    "hypothesis_ids": ["hyp-1"],
                    "rationale": "Aggregation is carrying contradiction pressure forward without narrowing the next check enough.",
                    "guidance": "Keep the next round focused on one explicit contradiction-closing check before widening scope again.",
                    "prompt_snippet": "Keep the next round focused on one explicit contradiction-closing check before widening scope again.",
                }
            ],
        },
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["critic_observations_validation"]["ok"] is True
    assert bundle["critic_observations_payload"]["critic_observations"][0]["target_module"] == "planner"
    assert bundle["critic_observations_payload"]["critic_observations"][0]["prompt_snippet"].startswith(
        "Keep the next round")
