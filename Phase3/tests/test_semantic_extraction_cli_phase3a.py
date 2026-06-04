import json
from pathlib import Path

from interface.cli import NidsAgentCli, SemanticExtractionRunContext
from semantic_extraction.runner import run_semantic_extraction


def _build_overview_summary_min() -> dict[str, object]:
    return {
        "batch_id": "semantic_batch_001_portscan",
        "dataset_name": "Friday-WorkingHours-Afternoon-PortScan.csv",
        "evidence_records": [
            {
                "evidence_id": "e1",
                "source_type": "dependency_observation",
                "source_name": "feature_redundancy",
                "feature_names": ["src_bytes", "dst_bytes"],
                "metric_names": ["correlation"],
                "observation_text": "src_bytes and dst_bytes move together across the partition.",
            },
            {
                "evidence_id": "e2",
                "source_type": "cardinality_metric",
                "source_name": "feature_cardinality",
                "feature_names": ["dst_port"],
                "metric_names": ["unique_values", "cardinality_ratio"],
                "observation_text": "dst_port has low cardinality relative to the partition size.",
            },
        ],
        "feature_scope_refs": ["src_bytes", "dst_bytes", "dst_port"],
        "global_observation_refs": ["e1"],
    }


def _build_partition_context() -> dict[str, object]:
    return {
        "partition_semantics": ["This partition models scanning behavior with high repetition."],
        "expected_structural_properties": ["Highly regular scanning behavior may appear naturally."],
        "epistemic_warnings": ["Use context only to interpret behavior, not to validate it."],
        "investigation_guidance": ["Retain broad and local structure for downstream analysis."],
    }


def _build_valid_response_payload() -> dict[str, object]:
    return {
        "substrate_id": "substrate-semantic-batch-001",
        "batch_id": "semantic_batch_001_portscan",
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
                        "scope_value": "semantic_batch_001_portscan",
                        "localized": False,
                        "notes": ["Observed across the overview evidence."],
                    },
                },
                "evidence_refs": ["e1"],
                "supporting_patterns": ["paired movement"],
                "contextual_modifiers": ["Regularity is expected in this partition, so this region remains descriptive only."],
                "uncertainty_notes": ["The region is broad and not yet localized."],
                "contradiction_refs": [],
                "tension_refs": ["tension-1"],
            }
        ],
        "preserved_weak_signals": [
            {
                "weak_signal_id": "weak-1",
                "descriptor": "dst_port shows low-diversity structure that may remain locally relevant.",
                "feature_scope": {
                    "features": ["dst_port"],
                    "locality": {
                        "scope_type": "feature_group",
                        "scope_value": "port_behavior",
                        "localized": True,
                        "notes": ["Signal is narrow and should remain explicit."],
                    },
                },
                "evidence_refs": ["e2"],
                "preservation_reason": "Minority but coherent low-diversity structure may matter later.",
                "contextual_modifiers": ["Low-diversity structure is not treated as validation here."],
                "uncertainty_notes": ["The signal remains weaker than the broad dependency region."],
            }
        ],
        "contradictions": [],
        "unresolved_tensions": [
            {
                "tension_id": "tension-1",
                "description": "The broad dependency region and the low-diversity dst_port signal may overlap without sharing the same structural handle yet.",
                "related_region_ids": ["region-1"],
                "evidence_refs": ["e1", "e2"],
                "context_notes": ["Keep the local signal visible instead of folding it into the broad region."],
                "reason_unresolved": "Current overview evidence does not resolve whether the low-diversity signal belongs inside the broad dependency structure.",
            }
        ],
    }


def test_phase3a_components_menu_routes_semantic_extraction():
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "1"
    cli._quit = lambda: None

    route = cli._phase3a_components_menu()

    assert route == "semantic_extraction"
    assert "Semantic Extraction  <available>" in cli._last_rendered


def test_load_semantic_extraction_run_context_reads_saved_bundle(tmp_path: Path):
    bundle = run_semantic_extraction(
        _build_overview_summary_min(),
        _build_partition_context(),
        llm_callable=lambda prompt_text: json.dumps(_build_valid_response_payload()),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_semantic_extraction_run_context(Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, SemanticExtractionRunContext)
    assert loaded.component_run["batch_id"] == "semantic_batch_001_portscan"
    assert loaded.parsed_output["substrate_id"] == "substrate-semantic-batch-001"


def test_render_semantic_extraction_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = SemanticExtractionRunContext(
        artifact_paths={
            "component_run_path": "semantic_run_001/component_run.json",
            "overview_summary_min_path": "semantic_run_001/overview_summary_min.json",
            "parsed_output_path": "semantic_run_001/parsed_output.json",
            "validation_report_path": "semantic_run_001/validation_report.json",
            "runtime_metrics_path": "semantic_run_001/runtime_metrics.json",
        },
        component_run={
            "batch_id": "semantic_batch_001_portscan",
            "model_name": "gpt-4.1-mini",
            "status": "ok",
            "validation_ok": True,
        },
        overview_summary_min={"dataset_name": "Friday-WorkingHours-Afternoon-PortScan.csv"},
        partition_context={},
        projected_evidence={},
        prompt_text="prompt",
        raw_response_text="response",
        parsed_output={
            "compressed_regions": [{"region_id": "region-1"}],
            "preserved_weak_signals": [{"weak_signal_id": "weak-1"}],
        },
        validation_report={},
        runtime_metrics={"duration_ms": 15.0},
        replay_metadata=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_semantic_extraction_run_review(run_context)

    assert "semantic_batch_001_portscan" in cli._last_rendered
    assert "Friday-WorkingHours-Afternoon-PortScan.csv" in cli._last_rendered
    assert "parsed_output.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered