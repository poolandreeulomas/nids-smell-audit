import json
from pathlib import Path

from investigation_analysis.input_builder import build_analysis_context_min
from investigation_analysis.parser import parse_investigation_analysis_response
from investigation_analysis.prompt_builder import build_investigation_analysis_prompt
from investigation_analysis.runner import run_investigation_analysis
from investigation_analysis.runtime_artifacts import load_investigation_analysis_bundle
from investigation_analysis.validator import validate_hypothesis_set


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
                "structural_descriptors": ["paired variation", "broad dependency"],
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
                "contextual_modifiers": ["Repeated activity can arise naturally in this partition."],
                "uncertainty_notes": ["Dependency scope remains broad."],
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
            "description": "Broad paired movement may reflect a stable structural regularity rather than a single narrow handle.",
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
                "summary": "The broad dependency region may reflect a batch-wide regularity that coexists with a narrower port-sensitive interpretation instead of replacing it.",
                "evidence_refs": ["e1", "e2", "e3"],
                "open_questions": [
                    "Does the localized dst_port signal remain when the broad dependency-linked flow-size structure is controlled?"
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


def test_parse_investigation_analysis_response_accepts_wrapped_payload():
    payload = _build_valid_response_payload()

    parsed = parse_investigation_analysis_response(json.dumps({"hypothesis_set": payload}))

    assert parsed["analysis_id"] == "analysis-batch-001"
    assert parsed["hypotheses"][0]["hypothesis_id"] == "hyp-1"


def test_run_investigation_analysis_returns_valid_bundle_and_artifacts(tmp_path: Path):
    response_payload = _build_valid_response_payload()
    analysis_context = build_analysis_context_min(
        _build_partition_context(),
        _build_artifact_framing_refs(),
    )

    bundle = run_investigation_analysis(
        _build_semantic_substrate(),
        analysis_context,
        llm_callable=lambda prompt_text: json.dumps(response_payload),
        model_name="gpt-4.1-mini",
        log_dir=str(tmp_path),
    )

    assert bundle["component_run"]["status"] == "ok"
    assert bundle["validation_report"]["ok"] is True
    assert bundle["hypothesis_set"]["batch_id"] == "batch-001"
    assert bundle["hypothesis_set"]["hypotheses"][0]["hypothesis_id"] == "hyp-1"
    assert "Generate up to 10 bounded investigation hypotheses for batch_id=batch-001." in bundle["prompt_text"]
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["hypothesis_index_path"]).exists()

    loaded = load_investigation_analysis_bundle(Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["parsed_output"]["analysis_id"] == "analysis-batch-001"
    assert loaded["hypothesis_index"]["hypothesis_count"] == 2
    assert loaded["runtime_metrics"]["status"] == "ok"
    assert loaded["replay_metadata"]["fresh_execution"] is True


def test_validate_hypothesis_set_rejects_planning_language():
    payload = _build_valid_response_payload()
    payload["hypotheses"][0]["summary"] = "Plan the first worker package around this interpretive framing."

    report = validate_hypothesis_set(
        payload,
        valid_evidence_ids={"e1", "e2", "e3", "e4"},
        expected_batch_id="batch-001",
    )

    assert report["ok"] is True
    assert any("Semantic language flag detected" in warning["message"] for warning in report["warnings"])


def test_run_investigation_analysis_rejects_invalid_analysis_context_before_calling_llm(tmp_path: Path):
    llm_called = {"value": False}

    def _unexpected_call(prompt_text: str) -> str:
        llm_called["value"] = True
        return json.dumps(_build_valid_response_payload())

    bundle = run_investigation_analysis(
        _build_semantic_substrate(),
        {
            "partition_context_ref": {
                "semantics": ["valid"],
                "expected_properties": ["valid"],
                "epistemic_warnings": ["valid"],
                "investigation_guidance": ["valid"],
            },
            "artifact_framing_refs": "not-a-list",
        },
        llm_callable=_unexpected_call,
        log_dir=str(tmp_path),
    )

    assert bundle["component_run"]["status"] == "error"
    assert bundle["validation_report"]["analysis_context_validation"]["ok"] is False
    assert bundle["prompt_text"] == ""
    assert llm_called["value"] is False


def test_build_investigation_analysis_prompt_sanitizes_forbidden_saturation_terms():
    prompt = build_investigation_analysis_prompt(
        batch_id="batch-001",
        projected_substrate={
            "compressed_regions": [
                {
                    "summary": "This region appears saturated and may saturate under burst conditions.",
                    "notes": ["saturation can hide weaker local signals"],
                }
            ]
        },
        projected_analysis_context={
            "partition_context_ref": {
                "semantics": ["This partition models saturation, spikes, and load."]
            }
        },
        projected_iteration_context={},
    )

    lowered = prompt.lower()
    assert "this partition models saturation, spikes, and load." not in lowered
    assert "this region appears saturated and may saturate under burst conditions." not in lowered
    assert "saturation can hide weaker local signals" not in lowered

    assert "this partition models load concentration, spikes, and load." in lowered
    assert "this region appears heavily loaded and may increase load concentration under burst conditions." in lowered
    assert "load concentration can hide weaker local signals" in lowered