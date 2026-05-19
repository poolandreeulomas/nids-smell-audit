from pathlib import Path

from data.dataset_config import get_default_dataset_config
from interface.cli import NidsAgentCli, ToolRunContext
from tests.test_tools_phase3a_runtime import _build_synthetic_df
from tools.contracts import build_tool_call_request
from tools.execution import execute_tool_call


def test_load_tool_run_context_reads_saved_bundle(tmp_path: Path):
    df, valid_numeric_features = _build_synthetic_df()
    request = build_tool_call_request(
        call_id="tool-call-cli-001",
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

    cli = object.__new__(NidsAgentCli)
    loaded = cli._load_tool_run_context(Path(bundle["artifact_paths"]["component_run_path"]).parent)

    assert isinstance(loaded, ToolRunContext)
    assert loaded.component_run["tool_name"] == "feature_summary"
    assert loaded.parsed_output["call_id"] == "tool-call-cli-001"


def test_render_tool_run_review_uses_component_artifacts():
    cli = object.__new__(NidsAgentCli)
    run_context = ToolRunContext(
        artifact_paths={
            "component_run_path": "tool_run_001/component_run.json",
            "tool_call_request_path": "tool_run_001/tool_call_request.json",
            "parsed_output_path": "tool_run_001/parsed_output.json",
            "validation_report_path": "tool_run_001/validation_report.json",
            "tool_metrics_path": "tool_run_001/tool_metrics.json",
        },
        component_run={
            "tool_name": "feature_summary",
            "target_scope": "feature",
            "status": "ok",
            "validation_ok": True,
        },
        tool_call_request={},
        tool_capability_record={},
        normalized_inputs={},
        raw_tool_output={},
        parsed_output={},
        validation_report={},
        tool_metrics={"duration_ms": 12.0},
        cache_record=None,
    )

    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._render_tool_run_review(run_context)

    assert "feature_summary" in cli._last_rendered
    assert "parsed_output.json" in cli._last_rendered
    assert "validation_report.json" in cli._last_rendered