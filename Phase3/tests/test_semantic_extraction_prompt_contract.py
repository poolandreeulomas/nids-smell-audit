from semantic_extraction.prompt_builder import build_semantic_extraction_prompt


def test_semantic_extraction_prompt_explicitly_states_nested_schema():
    prompt = build_semantic_extraction_prompt(
        batch_id="semantic_batch_076_friday-workinghours-afternoon-ddos.pcap_iscx",
        projected_evidence={
            "batch_id": "semantic_batch_076_friday-workinghours-afternoon-ddos.pcap_iscx",
            "evidence_count": 1,
            "evidence_records": [
                {
                    "evidence_id": "e1",
                    "feature_names": ["Feature A"],
                    "metric_names": ["metric"],
                    "observation_text": "Feature A is observed.",
                    "source_name": "demo",
                    "source_type": "overview_summary",
                }
            ],
            "feature_frequency": {"Feature A": 1},
            "feature_scope_refs": ["Feature A"],
            "global_observation_refs": ["e1"],
            "source_type_counts": {"overview_summary": 1},
        },
        normalized_partition_context={
            "semantics": ["partition semantics"],
            "expected_properties": ["expected properties"],
            "epistemic_warnings": ["warnings"],
            "investigation_guidance": ["guidance"],
        },
    )

    assert "=== OUTPUT CONTRACT ===" in prompt
    assert '"compressed_regions": [' in prompt
    assert '"feature_scope": {' in prompt
    assert '"features": [string]' in prompt
    assert '"feature_groups": [string]' in prompt
    assert '"locality": {' in prompt
    assert '"scope_type": string' in prompt
    assert '"scope_value": string' in prompt
    assert '"localized": boolean' in prompt
    assert '"notes": [string]' in prompt
    assert '"preserved_weak_signals": [' in prompt
    assert '"contradictions": [' in prompt
    assert '"unresolved_tensions": [' in prompt
