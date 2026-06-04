from pathlib import Path

import pandas as pd

from data.dataset_config import get_default_dataset_config
from tools.contracts import build_tool_call_request
from tools.execution import execute_tool_call
from tools.registry import get_tool_capability_record, get_tool_capability_records
from tools.runtime_artifacts import load_tool_run_bundle


def _build_synthetic_df():
    base = pd.DataFrame(
        {
            "summary_feature": [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            "distribution_feature": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6],
            "cardinality_feature": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            "shortcut_feature": [0] * 10 + [1] * 10,
            "neighborhood_feature": [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4],
            "rel_a": list(range(1, 21)),
            "rel_b": [value * 2 for value in range(1, 21)],
            "dep_anchor": [12, 1, 18, 4, 9, 7, 15, 3, 20, 6, 11, 2, 17, 5, 8, 14, 10, 13, 16, 19],
            "dep_partner": [25, 3, 37, 9, 19, 15, 31, 7, 41, 13, 23, 5, 35, 11, 17, 29, 21, 27, 33, 39],
            "rel_noise_1": [0, 3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3, 2, 3, 8],
            "rel_noise_2": [8, 6, 7, 5, 3, 0, 9, 9, 7, 9, 3, 2, 3, 8, 4, 6, 2, 6, 4, 3],
            "Label": ["BENIGN"] * 10 + ["ATTACK"] * 10,
        }
    )
    df = pd.concat([base, base], ignore_index=True)
    valid_numeric_features = [
        "summary_feature",
        "distribution_feature",
        "cardinality_feature",
        "shortcut_feature",
        "neighborhood_feature",
        "rel_a",
        "rel_b",
        "dep_anchor",
        "dep_partner",
        "rel_noise_1",
        "rel_noise_2",
    ]
    return df, valid_numeric_features


def test_capability_inventory_exposes_phase3a_contract_metadata():
    records = get_tool_capability_records()

    assert set(records.keys()) == {
        "feature_summary",
        "distribution_analysis",
        "cardinality_analysis",
        "feature_relation",
        "shortcut_analysis",
        "neighborhood_consistency_analysis",
        "dependency_concentration_analysis",
        "duplication_analysis",
    }
    assert get_tool_capability_record("feature_relation") == records["feature_relation"]
    assert records["duplication_analysis"]["supported_scopes"] == ["dataset"]


def test_execute_tool_call_supports_new_phase3a_verification_tools(tmp_path: Path):
    df, valid_numeric_features = _build_synthetic_df()

    shortcut_bundle = execute_tool_call(
        build_tool_call_request(
            call_id="tool-call-005",
            tool_name="shortcut_analysis",
            target_scope="feature",
            input_refs={"feature_name": "shortcut_feature"},
            preprocessing_profile_ref="default",
            execution_constraints={"cache_policy": "reuse", "validation_mode": "strict"},
        ),
        dataset_path="synthetic.csv",
        config=get_default_dataset_config(),
        dataset_frame=df,
        valid_numeric_features=valid_numeric_features,
        log_dir=tmp_path,
    )
    dependency_bundle = execute_tool_call(
        build_tool_call_request(
            call_id="tool-call-006",
            tool_name="dependency_concentration_analysis",
            target_scope="feature",
            input_refs={"feature_name": "dep_anchor"},
            preprocessing_profile_ref="default",
            execution_constraints={"cache_policy": "reuse", "validation_mode": "strict"},
        ),
        dataset_path="synthetic.csv",
        config=get_default_dataset_config(),
        dataset_frame=df,
        valid_numeric_features=valid_numeric_features,
        log_dir=tmp_path,
    )

    assert shortcut_bundle["tool_result"]["status"] == "ok"
    assert "strong_shortcut_signal" in shortcut_bundle["tool_result"]["observations"]["signals"]
    assert dependency_bundle["tool_result"]["status"] == "ok"
    assert dependency_bundle["tool_result"]["observations"]["metrics"]["top_partner"] == "dep_partner"


def test_execute_tool_call_returns_phase3a_result_and_artifacts(tmp_path: Path):
    df, valid_numeric_features = _build_synthetic_df()
    request = build_tool_call_request(
        call_id="tool-call-001",
        tool_name="feature_summary",
        target_scope="feature",
        input_refs={"feature_name": "summary_feature"},
        preprocessing_profile_ref="default",
        execution_constraints={"cache_policy": "reuse", "validation_mode": "strict"},
    )

    bundle = execute_tool_call(
        request,
        dataset_path="synthetic.csv",
        config=get_default_dataset_config(),
        dataset_frame=df,
        valid_numeric_features=valid_numeric_features,
        log_dir=tmp_path,
    )

    result = bundle["tool_result"]
    assert result["status"] == "ok"
    assert result["call_id"] == "tool-call-001"
    assert result["tool_name"] == "feature_summary"
    assert result["observations"]["feature"] == "summary_feature"
    assert result["observations"]["metrics"]["variance_ratio"] is not None
    assert result["evidence_refs"]
    assert bundle["validation_report"]["ok"] is True
    assert Path(bundle["artifact_paths"]["component_run_path"]).exists()
    assert Path(bundle["artifact_paths"]["parsed_output_path"]).exists()

    loaded = load_tool_run_bundle(Path(bundle["artifact_paths"]["component_run_path"]).parent)
    assert loaded["parsed_output"]["call_id"] == "tool-call-001"
    assert loaded["tool_call_request"]["tool_name"] == "feature_summary"


def test_execute_tool_call_records_cache_visibility_on_repeat(tmp_path: Path):
    df, valid_numeric_features = _build_synthetic_df()
    request = build_tool_call_request(
        call_id="tool-call-002",
        tool_name="distribution_analysis",
        target_scope="feature",
        input_refs={"feature_name": "distribution_feature"},
        preprocessing_profile_ref="default",
        execution_constraints={"cache_policy": "reuse", "validation_mode": "strict"},
    )

    first_bundle = execute_tool_call(
        request,
        dataset_path="synthetic.csv",
        config=get_default_dataset_config(),
        dataset_frame=df,
        valid_numeric_features=valid_numeric_features,
        log_dir=tmp_path,
    )
    second_bundle = execute_tool_call(
        {**request, "call_id": "tool-call-003"},
        dataset_path="synthetic.csv",
        config=get_default_dataset_config(),
        dataset_frame=df,
        valid_numeric_features=valid_numeric_features,
        log_dir=tmp_path,
    )

    assert first_bundle["cache_record"]["status"] == "tracked"
    assert second_bundle["cache_record"]["status"] == "tracked"
    assert any(event["status"] == "hit" for event in second_bundle["cache_record"]["events"])


def test_execute_tool_call_fails_closed_for_invalid_requests(tmp_path: Path):
    request = build_tool_call_request(
        call_id="tool-call-004",
        tool_name="feature_summary",
        target_scope="feature",
        input_refs={},
        preprocessing_profile_ref="default",
        execution_constraints={"cache_policy": "reuse", "validation_mode": "strict"},
    )

    bundle = execute_tool_call(
        request,
        dataset_path="synthetic.csv",
        config=get_default_dataset_config(),
        dataset_frame=None,
        valid_numeric_features=None,
        log_dir=tmp_path,
    )

    assert bundle["tool_result"]["status"] == "error"
    assert bundle["validation_report"]["request_validation"]["ok"] is False
    assert bundle["tool_result"]["limitations"][0]["code"] == "INVALID_TOOL_REQUEST"