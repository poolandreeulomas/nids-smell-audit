import json
from pathlib import Path

from aggregation.contracts import build_aggregation_handoff
from critic.runner import run_critic
from interface.cli import CriticRunContext, NidsAgentCli
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
            "The dependency signal remained visible in the targeted local slice."
        ],
        evidence_refs=["task-hyp-1-1_step_01"],
        preserved_contradictions=[
            "Current local evidence still conflicts with the broader dependency framing."
        ],
        open_gaps=["Need one more counter-check before closing the framing."],
        update_focus="Carry forward the dependency framing without collapsing the remaining contradiction.",
    )


def _build_saved_critic_bundle(tmp_path: Path) -> dict[str, object]:
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
    state_manager_bundle = run_state_manager(
        _build_initial_state(),
        _build_aggregation_handoff(),
        llm_callable=lambda prompt_text: next(state_manager_responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager"),
    )

    critic_responses = iter(
        [
            json.dumps(
                {
                    "batch_id": "batch-001",
                    "round_id": "round-001",
                    "critic_observations": [
                        {
                            "observation_id": "obs_001",
                            "observation_type": "productive_active_line",
                            "target_module": "planner",
                            "priority": "medium",
                            "hypothesis_ids": ["hyp-1"],
                            "rationale": "Aggregation is carrying contradiction pressure forward without narrowing the next check enough.",
                            "guidance": "Keep the next round focused on one explicit contradiction-closing check before widening scope again.",
                            "prompt_snippet": "Keep the next round focused on one explicit contradiction-closing check before widening scope again.",
                        }
                    ],
                }
            )
        ]
    )
    return run_critic(
        state_manager_bundle,
        llm_callable=lambda prompt_text: next(critic_responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "critic"),
    )


def test_phase3a_components_menu_routes_critic():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "9"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "critic"
    assert "Critic  <available>" in cli._last_rendered


def test_load_critic_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = _build_saved_critic_bundle(tmp_path)

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_critic_run_context(
        Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, CriticRunContext)
    assert loaded.component_run["round_id"] == "round-001"
    assert loaded.component_run["prompt_version"] == "phase3a.critic.prompt.v2"
    assert loaded.critic_observations_payload["batch_id"] == "batch-001"
    assert loaded.critic_observations_payload["critic_observations"][0]["target_module"] == "planner"


def test_render_critic_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = CriticRunContext(
        artifact_paths={
            "component_run_path": "critic_run_001/component_run.json",
            "critic_input_bundle_path": "critic_run_001/critic_input_bundle.json",
            "critic_observations_path": "critic_run_001/critic_observations.json",
            "validation_report_path": "critic_run_001/validation_report.json",
            "runtime_metrics_path": "critic_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "round_id": "round-001",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
            "final_round_gate_status": "allowed_non_final_round",
            "observation_count": 1,
            "observations_committed": True,
        },
        critic_input_min={"round_id": "round-001"},
        refined_state_summary={"hypothesis_id": "hyp-1"},
        module_behavior_summaries=[],
        process_signal_summary={"is_final_round": False},
        prompt_text="prompt",
        raw_response_text="response",
        critic_observations_payload={"critic_observations": []},
        validation_report={},
        runtime_metrics={"duration_ms": 10.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_critic_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "round-001" in cli._last_rendered
    assert "critic_input_bundle.json" in cli._last_rendered
    assert "critic_observations.json" in cli._last_rendered
