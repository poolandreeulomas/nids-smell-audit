import json
from pathlib import Path

from interface.cli import InvestigationAnalysisRunContext, NidsAgentCli
from investigation_analysis.input_builder import build_analysis_context_min
from investigation_analysis.runner import run_investigation_analysis


def _build_semantic_substrate() -> dict[str, object]:
    return {
        "substrate_id": "substrate-batch-001",
        "batch_id": "batch-001",
        "compressed_regions": [
            {
                "region_id": "region-1",
                "region_kind": "dependency_region",
                "status": "active",
                "summary": "Broad dependency structure links src_bytes and dst_bytes at partition scope.",
                "structural_descriptors": ["paired variation"],
                "feature_scope": {
                    "features": ["src_bytes", "dst_bytes"],
                    "feature_groups": ["flow_size"],
                    "locality": {
                        "scope_type": "partition_global",
                        "scope_value": "batch-001",
                        "localized": False,
                        "notes": ["Observed across the batch."],
                    },
                },
                "evidence_refs": ["e1", "e2"],
                "supporting_patterns": ["paired movement"],
                "contextual_modifiers": ["Regularity remains descriptive only."],
                "uncertainty_notes": ["Scope remains broad."],
                "contradiction_refs": ["contradiction-1"],
                "tension_refs": ["tension-1"],
            }
        ],
        "preserved_weak_signals": [
            {
                "weak_signal_id": "weak-1",
                "descriptor": "Localized dst_port separability appears in a narrow slice.",
                "feature_scope": {
                    "features": ["dst_port"],
                    "locality": {
                        "scope_type": "feature_group",
                        "scope_value": "port_behavior",
                        "localized": True,
                        "notes": ["Confined to a local slice."],
                    },
                },
                "evidence_refs": ["e3"],
                "preservation_reason": "Localized structure may matter later.",
                "contextual_modifiers": ["Single-feature separation remains weak evidence."],
                "uncertainty_notes": ["Scope beyond the slice is unresolved."],
            }
        ],
        "contradictions": [
            {
                "contradiction_id": "contradiction-1",
                "contradiction_kind": "representation_duplication_vs_scope_unclear",
                "description": "Duplicate-sensitive evidence coexists with localized separability whose broader scope is unclear.",
                "feature_scope": {
                    "features": ["dst_port"],
                    "locality": {
                        "scope_type": "representation_cluster",
                        "scope_value": "dst_port_cluster",
                        "localized": True,
                        "notes": ["Representation-sensitive evidence remains local."],
                    },
                },
                "supporting_evidence_refs": ["e4"],
                "conflicting_evidence_refs": ["e3"],
                "context_notes": ["Scope uncertainty remains explicit."],
                "downstream_relevance": "Preserve the contradiction for later comparison.",
            }
        ],
        "unresolved_tensions": [
            {
                "tension_id": "tension-1",
                "description": "The broad dependency region and the localized port signal may overlap without resolving to the same structural handle.",
                "related_region_ids": ["region-1"],
                "evidence_refs": ["e1", "e3"],
                "context_notes": ["Local structure should remain explicit."],
                "reason_unresolved": "Current evidence does not determine whether the local signal belongs inside the broad dependency region.",
            }
        ],
    }


def _build_partition_context() -> dict[str, object]:
    return {
        "partition_semantics": ["This partition shows repeated destination activity with mixed locality."],
        "expected_structural_properties": ["Broad dependency structure can coexist with local regularities."],
        "epistemic_warnings": ["Single-feature separation should remain weak evidence unless broader structure agrees."],
        "investigation_guidance": ["Preserve overlapping framings and unresolved local-vs-global scope questions."],
    }


def _build_artifact_framing_refs() -> list[dict[str, object]]:
    return [
        {
            "framing_id": "framing-1",
            "label": "dependency-backed regularity",
            "description": "Broad paired movement may reflect a stable structural regularity.",
        },
        {
            "framing_id": "framing-2",
            "label": "localized representation-sensitive handle",
            "description": "A narrow separability signal may coexist with the broad region without collapsing into it.",
        },
    ]


def _build_valid_response_payload() -> dict[str, object]:
    return {
        "analysis_id": "analysis-batch-001",
        "batch_id": "batch-001",
        "hypotheses": [
            {
                "hypothesis_id": "hyp-1",
                "summary": "The broad dependency region may reflect a batch-wide regularity that coexists with a narrower port-sensitive interpretation.",
                "evidence_refs": ["e1", "e2", "e3"],
                "open_questions": [
                    "Does the localized dst_port signal remain when the dependency-linked flow-size structure is controlled?"
                ],
            },
            {
                "hypothesis_id": "hyp-2",
                "summary": "The dst_port signal may remain a distinct representation-sensitive framing whose scope is still narrower than the broad dependency region.",
                "evidence_refs": ["e3", "e4"],
                "open_questions": [
                    "Would nearby representation-sensitive slices preserve this local signal or dissolve it?"
                ],
            },
        ],
    }


def test_phase3a_components_menu_routes_investigation_analysis():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "2"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "investigation_analysis"
    assert "Investigation Analysis  <available>" in cli._last_rendered


def test_load_investigation_analysis_run_context_reads_saved_bundle(tmp_path: Path):
    analysis_context = build_analysis_context_min(
        _build_partition_context(),
        _build_artifact_framing_refs(),
    )
    bundle = run_investigation_analysis(
        _build_semantic_substrate(),
        analysis_context,
        llm_callable=lambda prompt_text: json.dumps(_build_valid_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_investigation_analysis_run_context(
        Path(bundle["artifact_paths"]["component_run_path"]).parent
    )

    assert isinstance(loaded, InvestigationAnalysisRunContext)
    assert loaded.component_run["batch_id"] == "batch-001"
    assert loaded.parsed_output["analysis_id"] == "analysis-batch-001"
    assert loaded.hypothesis_index["hypothesis_count"] == 2


def test_render_investigation_analysis_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = InvestigationAnalysisRunContext(
        artifact_paths={
            "component_run_path": "investigation_analysis_run_001/component_run.json",
            "semantic_substrate_path": "investigation_analysis_run_001/semantic_substrate.json",
            "parsed_output_path": "investigation_analysis_run_001/parsed_output.json",
            "validation_report_path": "investigation_analysis_run_001/validation_report.json",
            "runtime_metrics_path": "investigation_analysis_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "batch-001",
            "source_substrate_id": "substrate-batch-001",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
        },
        semantic_substrate_input={},
        analysis_context_min={},
        analysis_iteration_context_min={},
        projected_substrate={},
        projected_analysis_context={},
        projected_iteration_context={},
        prompt_text="prompt",
        raw_response_text="response",
        parsed_output={"hypotheses": [{"hypothesis_id": "hyp-1"}, {"hypothesis_id": "hyp-2"}]},
        hypothesis_index={"overlap_pairs": [{"left_hypothesis_id": "hyp-1", "right_hypothesis_id": "hyp-2"}]},
        validation_report={},
        runtime_metrics={"duration_ms": 15.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_investigation_analysis_run_review(run_context)

    assert "batch-001" in cli._last_rendered
    assert "substrate-batch-001" in cli._last_rendered
    assert "parsed_output.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered