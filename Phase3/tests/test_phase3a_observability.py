from interface.phase3a_observability import build_worker_step_traces


def test_build_worker_step_traces_groups_attempts_actions_and_history():
    traces = build_worker_step_traces(
        prompt_snapshots=[
            {
                "step_index": 1,
                "step_mode": "reasoning_only",
                "attempt_index": 0,
                "prompt_text": "prompt-1",
                "repair_note": None,
            },
            {
                "step_index": 2,
                "step_mode": "action_window",
                "attempt_index": 0,
                "prompt_text": "prompt-2-attempt-0",
                "repair_note": None,
            },
            {
                "step_index": 2,
                "step_mode": "action_window",
                "attempt_index": 1,
                "prompt_text": "prompt-2-attempt-1",
                "repair_note": "repair invalid action payload",
            },
            {
                "step_index": 3,
                "step_mode": "final_synthesis",
                "attempt_index": 0,
                "prompt_text": "prompt-3",
                "repair_note": None,
            },
        ],
        raw_model_responses=[
            {
                "step_index": 1,
                "step_mode": "reasoning_only",
                "attempt_index": 0,
                "raw_response_text": "response-1",
            },
            {
                "step_index": 2,
                "step_mode": "action_window",
                "attempt_index": 0,
                "raw_response_text": "response-2-attempt-0",
            },
            {
                "step_index": 2,
                "step_mode": "action_window",
                "attempt_index": 1,
                "raw_response_text": "response-2-attempt-1",
            },
            {
                "step_index": 3,
                "step_mode": "final_synthesis",
                "attempt_index": 0,
                "raw_response_text": "response-3",
            },
        ],
        parsed_steps=[
            {
                "step_index": 1,
                "step_mode": "reasoning_only",
                "attempt_index": 0,
                "parsed_step": {
                    "decision": "continue",
                    "reasoning": "reasoning-1",
                },
                "validation": {
                    "ok": True,
                    "warnings": [],
                    "errors": [],
                },
            },
            {
                "step_index": 2,
                "step_mode": "action_window",
                "attempt_index": 1,
                "parsed_step": {
                    "decision": "action",
                    "reasoning": "reasoning-2",
                    "actions": [
                        {
                            "action_class": "distribution_verification",
                            "context_ref": "e8",
                            "feature_name": "Average Packet Size",
                        }
                    ],
                },
                "validation": {
                    "ok": True,
                    "warnings": [{"message": "bounded local scope maintained"}],
                    "errors": [],
                },
            },
            {
                "step_index": 3,
                "step_mode": "final_synthesis",
                "attempt_index": 0,
                "parsed_step": {
                    "decision": "finish",
                    "reasoning": "reasoning-3",
                    "worker_result": {
                        "status": "completed",
                        "findings": ["finding-1"],
                    },
                },
                "validation": {
                    "ok": True,
                    "warnings": [],
                    "errors": [],
                },
            },
        ],
        tool_events=[
            {
                "step_index": 2,
                "action_index": 1,
                "call_id": "task-1-step-02",
                "action": {
                    "action_class": "distribution_verification",
                    "feature_name": "Average Packet Size",
                },
                "tool_name": "distribution_analysis",
                "tool_result": {
                    "status": "ok",
                    "observations": {
                        "feature_name": "Average Packet Size",
                        "value": 0.75,
                    },
                    "limitations": [],
                    "evidence_refs": [{"artifact": "parsed_output", "path": "tool_run/parsed_output.json"}],
                },
                "tool_metrics": {"duration_ms": 12.5},
                "request_validation": {"ok": True, "warnings": [], "errors": []},
                "result_validation": {"ok": True, "warnings": [{"message": "cache miss"}], "errors": []},
                "error_message": "",
            }
        ],
        retry_events=[
            {
                "step_index": 2,
                "attempt_index": 0,
                "reason": "parse_repair",
                "message": "actions list missing",
            }
        ],
        failure_events=[
            {
                "step_index": 2,
                "attempt_index": 0,
                "failure_kind": "parse_error",
                "message": "response schema mismatch",
            }
        ],
    )

    assert [trace.step_index for trace in traces] == [1, 2, 3]

    step_two = traces[1]
    assert len(step_two.attempts) == 2
    assert step_two.latest_attempt.attempt_index == 1
    assert step_two.decision == "action"
    assert step_two.proposed_actions[0]["action_class"] == "distribution_verification"
    assert step_two.executed_actions[0]["feature_name"] == "Average Packet Size"
    assert step_two.action_results[0]["tool_name"] == "distribution_analysis"
    assert step_two.action_results[0]["tool_metrics"]["duration_ms"] == 12.5
    assert any("bounded local scope maintained" in flag for flag in step_two.flags)
    assert any("cache miss" in flag for flag in step_two.flags)
    assert any("parse_repair" in flag for flag in step_two.flags)
    assert any("parse_error" in flag for flag in step_two.flags)

    step_three = traces[2]
    assert step_three.decision == "finish"
    assert step_three.execution_history_before_step == [
        {
            "step_index": 2,
            "call_id": "task-1-step-02",
            "tool_name": "distribution_analysis",
            "status": "ok",
            "action": {
                "action_class": "distribution_verification",
                "feature_name": "Average Packet Size",
            },
            "observation_preview": "feature_name=Average Packet Size",
            "tool_metrics": {"duration_ms": 12.5},
        }
    ]
