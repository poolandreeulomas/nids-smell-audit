from pathlib import Path

import phase3_runtime.orchestrator as orchestrator_module
from phase3_runtime.runtime_artifacts import load_phase3a_runtime_bundle


def test_run_phase3a_batch_persists_failure_bundle_on_runtime_error(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.csv"
    dataset_path.write_text("feature_a,feature_b\n1,2\n", encoding="utf-8")

    def _explode(*_args, **_kwargs):
        raise RuntimeError("boom during phase 3A runtime")

    monkeypatch.setattr(
        orchestrator_module,
        "build_initial_semantic_inputs",
        _explode,
    )

    bundle = orchestrator_module.run_phase3a_batch(
        dataset_path,
        batch_id="crash-batch",
        log_dir=tmp_path,
        caller_mode="test",
    )

    assert bundle["component_run"]["status"] == "failed"
    assert bundle["component_run"]["terminal_reason"] == "runtime_error"
    assert Path(bundle["artifact_paths"]["run_dir"]).is_dir()
    assert Path(bundle["artifact_paths"]["runtime_summary_path"]).is_file()
    assert Path(bundle["artifact_paths"]["event_stream_path"]).is_file()
    assert Path(bundle["artifact_paths"]["terminal_log_path"]).is_file()

    loaded = load_phase3a_runtime_bundle(
        Path(bundle["artifact_paths"]["run_dir"]))

    assert loaded["component_run"]["status"] == "failed"
    assert loaded["component_run"]["terminal_reason"] == "runtime_error"
    assert loaded["component_run"]["error"]["message"] == "boom during phase 3A runtime"
    assert loaded["runtime_summary"]["status"] == "failed"
    assert loaded["runtime_summary"]["terminal_reason"] == "runtime_error"
    assert any(event["event_type"] == "EXCEPTION" for event in loaded["event_stream"])
    assert "[BATCH] START" in loaded["terminal_log_text"]
    assert "RuntimeError: boom during phase 3A runtime" in loaded["terminal_log_text"]
