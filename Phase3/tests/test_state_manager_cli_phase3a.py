import json
from pathlib import Path
from types import SimpleNamespace

from aggregation.contracts import build_aggregation_handoff
from interface.cli import NidsAgentCli, StateManagerRunContext
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
                open_questions=["Need to verify whether the dependency stays local."],
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
        preserved_contradiction_ids=["contr_0"],
        contradiction_lookup={
            "contr_0": "Current local evidence still conflicts with the broader dependency framing.",
        },
        open_gaps=["Need one more counter-check before closing the framing."],
        update_focus="Carry forward the dependency framing without collapsing the remaining contradiction.",
    )


def _build_saved_state_manager_bundle(tmp_path: Path) -> dict[str, object]:
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
        log_dir=str(tmp_path / "state_manager"),
    )


def test_phase3a_components_menu_routes_state_manager():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "8"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "state_manager"
    assert "State Manager  <available>" in cli._last_rendered


def test_load_state_manager_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = _build_saved_state_manager_bundle(tmp_path)

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_state_manager_run_context(Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, StateManagerRunContext)
    assert loaded.component_run["round_id"] == "round-001"
    assert loaded.component_run["prompt_version"] == "phase3a.state_manager.prompt.v1"
    assert loaded.state_update_result["new_state_version"] == 2
    assert loaded.updated_batch_state["batch_id"] == "batch-001"


def test_resolve_state_manager_prior_state_prompts_for_source_choice():
    cli = object.__new__(NidsAgentCli)
    cli._last_state_manager_run = SimpleNamespace(
        component_run={"batch_id": "batch-001"},
        updated_batch_state={"batch_id": "batch-001", "state_version": 3},
        artifact_paths={
            "component_run_path": "logs/state_manager_runs/state_manager_run_003/component_run.json"
        },
    )
    cli._get_latest_matching_state_manager_run_context = lambda batch_id: SimpleNamespace(
        component_run={"batch_id": batch_id},
        updated_batch_state={"batch_id": batch_id, "state_version": 2},
        artifact_paths={
            "component_run_path": "logs/state_manager_runs/state_manager_run_002/component_run.json"
        },
    )
    cli._get_latest_matching_investigation_analysis_run_context = lambda batch_id: None
    cli._clear_screen = lambda: None
    cli._show_error = lambda message: setattr(cli, "_last_error", message)
    cli._show_info = lambda message: setattr(cli, "_last_info", message)
    cli._read_menu_choice = lambda valid_choices: "2"

    prior_state, prior_state_source = cli._resolve_state_manager_prior_state(
        SimpleNamespace(
            component_run={"batch_id": "batch-001"},
            aggregation_handoff={"batch_id": "batch-001"},
        )
    )

    assert prior_state is not None
    assert prior_state_source is not None
    assert prior_state["state_version"] == 2
    assert prior_state_source["origin"] == "saved_state_manager_run"


def test_render_state_manager_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = StateManagerRunContext(
        artifact_paths={
            "component_run_path": "state_manager_run_001/component_run.json",
            "prior_state_path": "state_manager_run_001/prior_state.json",
            "updated_batch_state_path": "state_manager_run_001/updated_batch_state.json",
            "validation_report_path": "state_manager_run_001/validation_report.json",
            "runtime_metrics_path": "state_manager_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "round_id": "round-001",
            "hypothesis_id": "hyp-1",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
            "state_committed": True,
            "previous_state_version": 1,
            "new_state_version": 2,
        },
        prior_state={"state_version": 1},
        aggregation_handoff={"hypothesis_id": "hyp-1"},
        state_manager_context={},
        prompt_text="prompt",
        raw_response_text="response",
        state_delta_record={},
        updated_batch_state={"state_version": 2},
        state_update_result={"new_state_version": 2},
        validation_report={},
        runtime_metrics={"duration_ms": 10.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_state_manager_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "hyp-1" in cli._last_rendered
    assert "prior_state.json" in cli._last_rendered
    assert "updated_batch_state.json" in cli._last_rendered