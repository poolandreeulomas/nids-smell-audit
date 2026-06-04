from investigation_analysis.contracts import build_hypothesis, build_hypothesis_set
from semantic_extraction.contracts import (
    build_feature_scope,
    build_locality_descriptor,
    build_region,
    build_semantic_substrate,
)
from state.schema import CanonicalBatchState
from state.store import (
    apply_interpretive_hypothesis_patch,
    canonical_state_to_dict,
    get_interpretive_hypothesis,
    init_canonical_batch_state,
)

import pytest


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
                open_questions=["Need to verify whether the dependency stays local."],
            ),
            build_hypothesis(
                hypothesis_id="hyp-2",
                summary="The dependency may still hide a representation-sensitive effect.",
                evidence_refs=["region-e1"],
                open_questions=["Need to compare the signal across partitions."],
            ),
        ],
    )


def test_init_canonical_batch_state_registers_two_layer_state():
    state = init_canonical_batch_state(
        batch_id="batch-001",
        structural_substrate=_build_semantic_substrate(),
        hypothesis_set=_build_hypothesis_set(),
    )

    assert state.batch_id == "batch-001"
    assert state.state_version == 1
    assert state.structural_substrate["substrate_id"] == "substrate-001"
    assert len(state.interpretive_hypotheses) == 2
    assert state.interpretive_hypotheses[0].hypothesis_id == "hyp-1"
    assert state.interpretive_hypotheses[0].status == "unresolved"
    assert state.interpretive_hypotheses[0].open_gaps == [
        "Need to verify whether the dependency stays local."
    ]
    assert state.revision_log[-1].revision_type == "initialization"

    payload = canonical_state_to_dict(state)
    restored = CanonicalBatchState.from_dict(payload)
    assert restored.batch_id == state.batch_id
    assert restored.interpretive_hypotheses[1].hypothesis_id == "hyp-2"
    assert restored.structural_substrate == state.structural_substrate


def test_apply_interpretive_hypothesis_patch_returns_new_state_version():
    state = init_canonical_batch_state(
        batch_id="batch-001",
        structural_substrate=_build_semantic_substrate(),
        hypothesis_set=_build_hypothesis_set(),
    )

    updated_state = apply_interpretive_hypothesis_patch(
        state,
        round_id="round-001",
        hypothesis_id="hyp-1",
        summary="The dependency remained plausible after local verification but is not resolved.",
        status="active",
        evidence_refs=["region-e1", "task-hyp-1-1_step_01"],
        merged_findings=["The dependency signal remained visible in the targeted local slice."],
        preserved_contradictions=[
            "The shortcut framing still conflicts with narrower local port evidence."
        ],
        open_gaps=["Need one more counter-check before status can strengthen further."],
        update_focus="Preserve the dependency framing while carrying forward unresolved local tension.",
    )

    original = get_interpretive_hypothesis(state, "hyp-1")
    target = get_interpretive_hypothesis(updated_state, "hyp-1")
    untouched = get_interpretive_hypothesis(updated_state, "hyp-2")

    assert original is not None
    assert target is not None
    assert untouched is not None
    assert state.state_version == 1
    assert updated_state.state_version == 2
    assert state.structural_substrate == updated_state.structural_substrate
    assert original.summary == "The dependency may reflect a shortcut-compatible framing."
    assert target.summary == (
        "The dependency remained plausible after local verification but is not resolved."
    )
    assert target.status == "active"
    assert target.revision_count == 1
    assert target.last_updated_round == "round-001"
    assert untouched.summary == (
        "The dependency may still hide a representation-sensitive effect."
    )

    revision = updated_state.revision_log[-1]
    assert revision.round_id == "round-001"
    assert revision.hypothesis_id == "hyp-1"
    assert any(item["field"] == "status" for item in revision.applied_updates)
    assert any(item["field"] == "merged_findings" for item in revision.applied_updates)


def test_apply_interpretive_hypothesis_patch_rejects_unknown_hypothesis():
    state = init_canonical_batch_state(
        batch_id="batch-001",
        structural_substrate=_build_semantic_substrate(),
        hypothesis_set=_build_hypothesis_set(),
    )

    with pytest.raises(KeyError):
        apply_interpretive_hypothesis_patch(
            state,
            round_id="round-001",
            hypothesis_id="missing-hypothesis",
            summary="No change",
        )