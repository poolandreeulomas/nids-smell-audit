import json
from pathlib import Path

from aggregation.contracts import build_aggregation_handoff
from final_batch_auditor.runner import run_final_batch_auditor
from interface.cli import FinalBatchAuditorRunContext, NidsAgentCli
from investigation_analysis.contracts import build_hypothesis, build_hypothesis_set
from semantic_extraction.contracts import (
    build_feature_scope,
    build_locality_descriptor,
    build_region,
    build_semantic_substrate,
)
from state.store import init_canonical_batch_state
from state_manager.runner import run_state_manager


BATCH_ID = "final-audit-cli-batch-001"
HYPOTHESIS_ID = "hyp-final-cli-1"


def _build_initial_state() -> dict[str, object]:
    semantic_substrate = build_semantic_substrate(
        substrate_id="final-cli-substrate-001",
        batch_id=BATCH_ID,
        compressed_regions=[
            build_region(
                region_id="final-cli-region-1",
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
                evidence_refs=["final-cli-region-e1"],
            )
        ],
        preserved_weak_signals=[],
        contradictions=[],
        unresolved_tensions=[],
    )
    hypothesis_set = build_hypothesis_set(
        analysis_id="final-cli-analysis-001",
        batch_id=BATCH_ID,
        hypotheses=[
            build_hypothesis(
                hypothesis_id=HYPOTHESIS_ID,
                summary="The dependency may indicate a shortcut-compatible dependency framing.",
                evidence_refs=["final-cli-region-e1"],
                open_questions=["Need to verify whether the dependency stays local."],
            )
        ],
    )
    return init_canonical_batch_state(
        batch_id=BATCH_ID,
        structural_substrate=semantic_substrate,
        hypothesis_set=hypothesis_set,
    ).to_dict()


def _build_saved_final_batch_auditor_bundle(tmp_path: Path) -> dict[str, object]:
    state_manager_responses = iter(
        [
            json.dumps(
                {
                    "state_delta_record": {
                        "batch_id": BATCH_ID,
                        "round_id": "round-001",
                        "hypothesis_id": HYPOTHESIS_ID,
                        "summary": "The final CLI fixture keeps one contradiction visible in the committed final state.",
                        "status": "active",
                        "evidence_refs": ["final-cli-region-e1", "final-cli-task-step-01"],
                        "preserved_contradictions": [
                            "The local slice still conflicts with the broader dependency framing."
                        ],
                        "open_gaps": [
                            "Need to verify whether the dependency stays local.",
                            "One closure gap still remains in the final committed state."
                        ],
                        "merged_findings": [
                            "The dependency remained visible in the localized verification slice."
                        ],
                        "update_focus": "Finish with contradiction-preserving auditability rather than forced closure.",
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
    state_manager_bundle = run_state_manager(
        _build_initial_state(),
        build_aggregation_handoff(
            batch_id=BATCH_ID,
            round_id="round-001",
            hypothesis_id=HYPOTHESIS_ID,
            merged_findings=[
                "The dependency remained visible in the localized verification slice."
            ],
            evidence_refs=["final-cli-task-step-01"],
            preserved_contradictions=[
                "The local slice still conflicts with the broader dependency framing."
            ],
            open_gaps=["One closure gap still remains in the final committed state."],
            update_focus="Finish with contradiction-preserving auditability rather than forced closure.",
        ),
        llm_callable=lambda prompt_text: next(state_manager_responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "state_manager"),
    )

    final_audit_responses = iter(
        [
            json.dumps(
                {
                    "debugging_audit_report": {
                        "batch_id": BATCH_ID,
                        "trajectory_summary": "The completed batch stayed focused on one dependency framing while preserving one contradiction into the final committed state.",
                        "hypothesis_summary": "The main hypothesis remained active and locally supported, but the final state kept one unresolved contradiction and one open pressure visible.",
                        "surviving_contradictions": [
                            "The local slice still conflicts with the broader dependency framing."
                        ],
                        "open_pressures": [
                            "One closure gap still remains in the final committed state."
                        ],
                        "failure_summary": "The runtime remained traceable, but the final investigation breadth stayed narrow relative to the contradiction pressure.",
                        "traceability_refs": [
                            "final-cli-region-e1",
                            "final-cli-task-step-01",
                            str(state_manager_bundle["artifact_paths"]["updated_batch_state_path"]),
                        ],
                    }
                }
            )
        ]
    )
    return run_final_batch_auditor(
        state_manager_bundle,
        llm_callable=lambda prompt_text: next(final_audit_responses),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path / "final_batch_auditor"),
        is_final_batch=True,
        batch_component_bundles={"state_manager": [state_manager_bundle]},
    )


def test_phase3a_components_menu_routes_final_batch_auditor():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "10"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "final_batch_auditor"
    assert "Final Batch Auditor  <available>" in cli._last_rendered


def test_load_final_batch_auditor_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = _build_saved_final_batch_auditor_bundle(tmp_path)

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_final_batch_auditor_run_context(
        Path(bundle["artifact_paths"]["component_run_path"]).parent
    )

    assert isinstance(loaded, FinalBatchAuditorRunContext)
    assert loaded.component_run["batch_id"] == BATCH_ID
    assert loaded.component_run["prompt_version"] == "phase3a.final_batch_auditor.prompt.v1"
    assert loaded.debugging_audit_report["batch_id"] == BATCH_ID


def test_render_final_batch_auditor_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = FinalBatchAuditorRunContext(
        artifact_paths={
            "component_run_path": "final_batch_audit_run_001/component_run.json",
            "final_audit_input_path": "final_batch_audit_run_001/final_audit_input.json",
            "debugging_audit_report_path": "final_batch_audit_run_001/debugging_audit_report.json",
            "validation_report_path": "final_batch_audit_run_001/validation_report.json",
            "runtime_metrics_path": "final_batch_audit_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": BATCH_ID,
            "state_version": 3,
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
            "terminal_gate_status": "confirmed_terminal_batch",
            "audit_mode": "authoritative",
            "traceability_ref_count": 3,
        },
        final_audit_input={"batch_id": BATCH_ID},
        final_state_summary={"state_version": 3},
        round_history_summary=[],
        process_signal_summary={"round_count": 1},
        prompt_text="prompt",
        raw_response_text="response",
        debugging_audit_report={"batch_id": BATCH_ID},
        validation_report={},
        runtime_metrics={"duration_ms": 10.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_final_batch_auditor_run_review(run_context)

    assert BATCH_ID in cli._last_rendered
    assert "final_audit_input.json" in cli._last_rendered
    assert "debugging_audit_report.json" in cli._last_rendered
