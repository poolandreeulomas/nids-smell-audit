from pathlib import Path

import main as main_module


def test_main_phase3a_batch_routes_to_authoritative_runtime(monkeypatch):
    captured_call: dict[str, object] = {}

    monkeypatch.setattr(
        main_module,
        "_select_dataset_path",
        lambda data_dir: Path("dataset.csv"),
    )

    def _fake_run_phase3a_batch(dataset_path, **kwargs):
        captured_call["dataset_path"] = dataset_path
        captured_call.update(kwargs)
        return {
            "component_run": {
                "batch_id": "phase3a-batch-001",
            }
        }

    monkeypatch.setattr(main_module, "run_phase3a_batch", _fake_run_phase3a_batch)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.2")
    monkeypatch.setenv("PHASE3A_MAX_ROUNDS", "4")
    monkeypatch.setenv("PHASE3A_PLANNING_MODEL", "gpt-5-mini")
    monkeypatch.setenv("PHASE3A_WORKER_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("PHASE3A_SYNTHESIS_MODEL", "gpt-5.4")
    monkeypatch.setenv("PHASE3A_EXECUTION_MODE", "full_round")
    monkeypatch.setenv("PHASE3A_ENABLE_CRITIC", "1")
    monkeypatch.setenv("PHASE3A_BATCH_ID", "explicit-batch-id")
    monkeypatch.setenv("PHASE3A_LOG_DIR", "runtime_logs")

    result = main_module.main_phase3a_batch()

    assert result["component_run"]["batch_id"] == "phase3a-batch-001"
    assert captured_call["dataset_path"] == Path("dataset.csv")
    assert captured_call["batch_id"] == "explicit-batch-id"
    assert captured_call["model_name"] == "gpt-4.1-mini"
    assert captured_call["temperature"] == 0.2
    assert captured_call["max_rounds"] == 4
    assert captured_call["execution_mode"] == "full_round"
    assert captured_call["enable_critic"] is True
    assert captured_call["log_dir"] == "runtime_logs"
    assert captured_call["caller_mode"] == "main"
    assert captured_call["component_model_names"] == {
        "investigation_analysis": "gpt-5-mini",
        "hypothesis_ranking": "gpt-5-mini",
        "planner": "gpt-5-mini",
        "router": "gpt-5-mini",
        "worker": "gpt-4.1-mini",
        "aggregation": "gpt-5.4",
        "state_manager": "gpt-5.4",
        "critic": "gpt-5.4",
        "final_batch_auditor": "gpt-5.4",
    }
    assert set(captured_call["llm_callables"]) == set(main_module.PHASE3A_RUNTIME_COMPONENTS)
    assert all(callable(fn) for fn in captured_call["llm_callables"].values())