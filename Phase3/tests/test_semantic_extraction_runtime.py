import json
from pathlib import Path

from semantic_extraction.parser import parse_semantic_extraction_response
from semantic_extraction.runner import run_semantic_extraction
from semantic_extraction.runtime_artifacts import load_semantic_extraction_bundle
from semantic_extraction.validator import validate_semantic_substrate


def _build_overview_summary_min() -> dict[str, object]:
    return {
        "batch_id": "batch-001",
        "evidence_records": [
            {
                "evidence_id": "e1",
                "source_type": "dependency_observation",
                "source_name": "feature_relation",
                "feature_names": ["src_bytes", "dst_bytes"],
                "metric_names": ["correlation"],
                "observation_text": "src_bytes and dst_bytes move together across the partition.",
            },
            {
                "evidence_id": "e2",
                "source_type": "distribution_metric",
                "source_name": "distribution_analysis",
                "feature_names": ["src_bytes"],
                "metric_names": ["js_divergence"],
                "observation_text": "src_bytes shows a broad partition-level shift between classes.",
            },
            {
                "evidence_id": "e3",
                "source_type": "representation_observation",
                "source_name": "shortcut_analysis",
                "feature_names": ["dst_port"],
                "metric_names": ["cv_balanced_accuracy"],
                "observation_text": "dst_port shows localized separability but only in a narrow subset of evidence.",
            },
            {
                "evidence_id": "e4",
                "source_type": "duplication_observation",
                "source_name": "duplication_analysis",
                "feature_names": ["dst_port"],
                "metric_names": ["duplicate_ratio"],
                "observation_text": "Duplicate structure appears but its scope remains unclear.",
            },
        ],
        "feature_scope_refs": ["src_bytes", "dst_bytes", "dst_port"],
        "global_observation_refs": ["e1", "e2"],
    }


def _build_partition_context() -> dict[str, object]:
    return {
        "partition_semantics": ["This partition models scanning-like repetition."],
        "expected_structural_properties": ["Repeated destination activity can arise naturally."],
        "epistemic_warnings": ["Single-feature separation is weak evidence on its own."],
        "investigation_guidance": ["Retain localized counterevidence for downstream analysis."],
    }


def _build_valid_response_payload() -> dict[str, object]:
    return {
        "substrate_id": "substrate-batch-001",
        "batch_id": "batch-001",
        "compressed_regions": [
            {
                "region_id": "region-1",
                "region_kind": "dependency_region",
                "status": "active",
                "summary": "Broad dependency structure links src_bytes and dst_bytes at partition scope.",
                "structural_descriptors": ["paired variation", "broad dependency"],
                "feature_scope": {
                    "features": ["src_bytes", "dst_bytes"],
                    "feature_groups": ["flow_size"],
                    "locality": {
                        "scope_type": "partition_global",
                        "scope_value": "batch-001",
                        "localized": False,
                        "notes": ["Observed across the overview evidence."],
                    },
                },
                "evidence_refs": ["e1", "e2"],
                "supporting_patterns": ["paired movement", "partition-wide shift"],
                "contextual_modifiers": [
                    "Repeated activity can arise naturally in this partition, so the region remains descriptive only."
                ],
                "uncertainty_notes": ["The region is broad and not yet localized to a narrower cluster."],
                "contradiction_refs": ["contradiction-1"],
                "tension_refs": ["tension-1"],
            }
        ],
        "preserved_weak_signals": [
            {
                "weak_signal_id": "weak-1",
                "descriptor": "Localized separability appears around dst_port without broad confirmation.",
                "feature_scope": {
                    "features": ["dst_port"],
                    "locality": {
                        "scope_type": "feature_group",
                        "scope_value": "port_behavior",
                        "localized": True,
                        "notes": ["Signal is confined to a narrow slice."],
                    },
                },
                "evidence_refs": ["e3"],
                "preservation_reason": "Minority but coherent localized structure may matter later.",
                "contextual_modifiers": [
                    "Single-feature separation should be interpreted cautiously in this partition."
                ],
                "uncertainty_notes": ["The signal remains weak relative to the broader dependency region."],
            }
        ],
        "contradictions": [
            {
                "contradiction_id": "contradiction-1",
                "contradiction_kind": "representation_duplication_vs_scope_unclear",
                "description": "Duplicate-sensitive evidence coexists with a localized separability signal whose broader scope is unclear.",
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
                "context_notes": ["Single-feature separation remains weak evidence in this partition."],
                "downstream_relevance": "Preserve this contradiction so downstream analysis can compare scope-sensitive evidence.",
            }
        ],
        "unresolved_tensions": [
            {
                "tension_id": "tension-1",
                "description": "The broad dependency region and the localized dst_port signal may overlap without yet resolving to the same structural handle.",
                "related_region_ids": ["region-1"],
                "evidence_refs": ["e1", "e3"],
                "context_notes": ["Local structure should remain explicit instead of being folded into the broad region."],
                "reason_unresolved": "Current overview evidence does not determine whether the localized signal belongs inside the broad dependency region.",
            }
        ],
    }


def test_parse_semantic_extraction_response_accepts_wrapped_payload():
    payload = _build_valid_response_payload()

    parsed = parse_semantic_extraction_response(json.dumps({"semantic_substrate": payload}))

    assert parsed["substrate_id"] == "substrate-batch-001"
    assert parsed["compressed_regions"][0]["region_kind"] == "dependency_region"


def test_run_semantic_extraction_returns_valid_bundle_and_artifacts(tmp_path: Path):
    response_payload = _build_valid_response_payload()

    bundle = run_semantic_extraction(
        _build_overview_summary_min(),
        _build_partition_context(),
        llm_callable=lambda prompt_text: json.dumps(response_payload),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["ok"] is True
    assert bundle["semantic_substrate"]["batch_id"] == "batch-001"
    assert bundle["semantic_substrate"]["compressed_regions"][0]["region_kind"] == "dependency_region"
    assert "Initialize the structural substrate for batch_id=batch-001." in bundle["prompt_text"]
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["rendered_prompt_path"]).exists()

    loaded = load_semantic_extraction_bundle(Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["parsed_output"]["substrate_id"] == "substrate-batch-001"
    assert loaded["runtime_metrics"]["status"] == "ok"
    assert loaded["replay_metadata"]["fresh_execution"] is True


def test_validate_semantic_substrate_rejects_planning_language():
    payload = _build_valid_response_payload()
    payload["compressed_regions"][0]["summary"] = "Plan the next worker pass around this dependency region."

    report = validate_semantic_substrate(payload, valid_evidence_ids={"e1", "e2", "e3", "e4"})

    assert report["ok"] is True
    assert any("Semantic language flag detected" in warning["message"] for warning in report["warnings"])