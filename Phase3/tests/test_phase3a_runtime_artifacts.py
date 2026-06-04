from phase3_runtime.ledger import (
    BatchLedger,
    FinalizationRecord,
    HypothesisExecutionRecord,
    RoundManifest,
)
from phase3_runtime.runtime_artifacts import (
    build_phase3a_runtime_artifact_paths,
    load_phase3a_runtime_bundle,
    save_phase3a_runtime_artifacts,
)
from utils.run_logging import write_json


def test_phase3a_runtime_artifacts_persist_batch_ledger_and_round_manifests(tmp_path):
    ledger = BatchLedger(
        batch_id="batch-runtime-001",
        dataset_path="C:/data/partition.csv",
        model_name="gpt-4.1-mini",
        max_rounds=3,
        critic_enabled=False,
        status="completed",
        created_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:10:00+00:00",
        semantic_extraction_run_path="semantic/component_run.json",
        initial_investigation_analysis_run_path="analysis/component_run.json",
        initial_state_path="runtime/initial_state.json",
        initial_state_version=1,
        round_manifests=[
            RoundManifest(
                round_id="round-001",
                round_index=1,
                analysis_mode="initial",
                analysis_run_path="analysis/component_run.json",
                frozen_snapshot_path="round_manifests/round-001_snapshot.json",
                ranking_run_path="ranking/component_run.json",
                planner_run_path="planner/component_run.json",
                selected_hypothesis_ids=["hyp-1"],
                deferred_hypothesis_ids=["hyp-2"],
                start_state_version=1,
                end_state_version=2,
                status="completed",
                hypothesis_runs=[
                    HypothesisExecutionRecord(
                        hypothesis_id="hyp-1",
                        planner_strategy_id="strategy-1",
                        router_run_path="router/component_run.json",
                        task_ids=["task-1", "task-2"],
                        worker_run_paths=[
                            "worker/task-1/component_run.json",
                            "worker/task-2/component_run.json",
                        ],
                        aggregation_run_path="aggregation/component_run.json",
                        state_manager_run_path="state_manager/component_run.json",
                        start_state_version=1,
                        end_state_version=2,
                        status="completed",
                    )
                ],
            )
        ],
        finalization=FinalizationRecord(
            terminal_reason="max_rounds_reached",
            final_state_manager_run_path="state_manager/component_run.json",
            final_batch_auditor_run_path="final_batch_auditor/component_run.json",
            final_state_version=2,
            final_status="completed",
        ),
    )
    artifact_paths = build_phase3a_runtime_artifact_paths(
        batch_id=ledger.batch_id,
        log_dir=tmp_path,
    )

    persisted = save_phase3a_runtime_artifacts(
        artifact_paths=artifact_paths,
        component_run={
            "component": "phase3a_runtime",
            "batch_id": ledger.batch_id,
            "status": "completed",
        },
        batch_ledger=ledger,
        initial_runtime_context={
            "batch_id": ledger.batch_id,
            "dataset_path": ledger.dataset_path,
        },
        finalization_summary={
            "terminal_reason": ledger.finalization.terminal_reason,
            "final_state_version": ledger.finalization.final_state_version,
        },
        runtime_metrics={
            "round_count": 1,
            "final_state_version": 2,
        },
        replay_metadata={
            "fresh_execution": True,
        },
        runtime_summary={
            "run_id": "runtime-run-001",
            "batch_id": ledger.batch_id,
            "mode": "full_batch",
            "status": "completed",
            "terminal_reason": "max_rounds_reached",
            "warnings": ["w1"],
            "errors": [],
        },
    )
    artifact_paths["event_stream_path"].write_text(
        '{"event_type":"BATCH_START","source":"runtime"}\n',
        encoding="utf-8",
    )
    artifact_paths["terminal_log_path"].write_text(
        "[BATCH] START batch_id=batch-runtime-001\n",
        encoding="utf-8",
    )
    write_json(artifact_paths["initial_state_path"], {"state_version": 1})

    loaded = load_phase3a_runtime_bundle(artifact_paths["run_dir"])

    assert persisted["batch_ledger_path"].endswith("batch_ledger.json")
    assert persisted["round_manifests_dir"].endswith("round_manifests")
    assert persisted["terminal_log_path"].endswith("runtime_terminal.log")
    assert loaded["component_run"]["batch_id"] == "batch-runtime-001"
    assert loaded["batch_ledger"].batch_id == "batch-runtime-001"
    assert loaded["batch_ledger"].round_manifests[0].round_id == "round-001"
    assert loaded["batch_ledger"].round_manifests[0].hypothesis_runs[0].task_ids == ["task-1", "task-2"]
    assert loaded["finalization_summary"]["terminal_reason"] == "max_rounds_reached"
    assert loaded["runtime_summary"]["run_id"] == "runtime-run-001"
    assert loaded["event_stream"][0]["event_type"] == "BATCH_START"
    assert "[BATCH] START" in loaded["terminal_log_text"]
