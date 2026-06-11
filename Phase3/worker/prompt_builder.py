"""Prompt assembly for the Phase 3A Worker."""

from __future__ import annotations

import json
from typing import Any


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _history_snapshot(tool_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for event in tool_events[-4:]:
        action = event.get("action", {}) if isinstance(
            event.get("action"), dict) else {}
        tool_result = event.get("tool_result", {}) if isinstance(
            event.get("tool_result"), dict) else {}
        observations = tool_result.get("observations", {}) if isinstance(
            tool_result.get("observations"), dict) else {}
        limitations = tool_result.get("limitations") if isinstance(
            tool_result.get("limitations"), list) else []
        error_message = event.get("error_message") if isinstance(
            event.get("error_message"), str) else ""
        if not error_message and limitations:
            first_limitation = limitations[0]
            if isinstance(first_limitation, dict):
                error_message = str(first_limitation.get("message") or "")
            elif isinstance(first_limitation, str):
                error_message = first_limitation
        snapshot.append(
            {
                "step_index": event.get("step_index"),
                "action_index": event.get("action_index"),
                "call_id": event.get("call_id"),
                "action_class": action.get("action_class"),
                "context_ref": action.get("context_ref"),
                "feature_name": action.get("feature_name"),
                "related_feature_name": action.get("related_feature_name"),
                "status": tool_result.get("status"),
                "signals": observations.get("signals", []),
                "error_message": error_message,
            }
        )
    return snapshot


def _step_mode(current_step: int, max_steps: int) -> str:
    if current_step >= max_steps:
        return "final_synthesis"
    if current_step in {1, 2}:
        return "reasoning_only"
    if current_step % 2 == 1:
        return "action_window"
    return "reasoning_only"


def build_worker_prompt(
    *,
    batch_id: str,
    round_id: str,
    worker_task: dict[str, Any],
    local_context_records: list[dict[str, Any]],
    action_guidance: list[dict[str, Any]],
    tool_events: list[dict[str, Any]],
    budget_rules: dict[str, Any],
    current_step: int,
    repair_note: str | None = None,
) -> str:
    task_id = str(worker_task.get("task_id") or "unknown_task")
    hypothesis_id = str(worker_task.get("hypothesis_id")
                        or "unknown_hypothesis")
    max_steps = int(budget_rules.get("max_steps") or 0)
    step_mode = _step_mode(current_step, max_steps)

    output_examples: list[str] = []
    step_rules: list[str] = []
    if step_mode == "reasoning_only":
        step_rules.extend(
            [
                "This is a reasoning-only step.",
                "Do not propose actions and do not finish the task on this step.",
                "Return decision='continue' with a short bounded reasoning update.",
            ]
        )
        output_examples.extend(
            [
                "Return:",
                _json_block(
                    {
                        "decision": "continue",
                        "reasoning": "State the most important local inference, the remaining uncertainty, and the next local focus.",
                    }
                ),
            ]
        )
    elif step_mode == "action_window":
        step_rules.extend(
            [
                "This is an action window.",
                "Reason briefly about what local check is still worth running.",
                "If a bounded in-scope check is useful, return decision='action' with one or more actions in 'actions'.",
                "During action windows:",
                "If a plausible shortcut candidate already exists in the local evidence and direct verification is available through the allowed actions, prefer direct verification over additional exploratory actions unless a clear unresolved prerequisite remains.",
                "Avoid repeatedly collecting indirect evidence around the same candidate when direct verification is already feasible.",
                "If no additional in-scope action is warranted, return decision='continue' with a short bounded reasoning update.",
            ]
        )
        output_examples.extend(
            [
                "If you need local evidence acquisition, return:",
                _json_block(
                    {
                        "decision": "action",
                        "reasoning": "Explain why these local checks are the narrowest useful next step.",
                        "actions": [
                            {
                                "action_class": "one allowed action_class",
                                "context_ref": "one listed local_context_ref",
                                "feature_name": "one feature inside that context when required",
                                "related_feature_name": "optional second feature for relation_verification only",
                            }
                        ],
                    }
                ),
                "If no bounded action is needed on this step, return:",
                _json_block(
                    {
                        "decision": "continue",
                        "reasoning": "Explain what the current evidence already says and what remains locally unresolved.",
                    }
                ),
            ]
        )
    else:
        step_rules.extend(
            [
                "This is the final synthesis step.",
                "Do not propose actions.",
                "Return decision='finish' with the authoritative worker_result for this task.",
            ]
        )
        output_examples.extend(
            [
                "Return:",
                _json_block(
                    {
                        "decision": "finish",
                        "reasoning": "Briefly summarize the reasoning progression and why the final task status is warranted.",
                        "worker_result": {
                            "task_id": task_id,
                            "hypothesis_id": hypothesis_id,
                            "status": "completed|partial|failed|inconclusive",
                            "findings": ["bounded evidence-oriented finding"],
                            "evidence_refs": ["tool_event call_id"],
                            "contradictions": ["local contradiction preserved"],
                            "limitations": ["local limitation if any"],
                        },
                    }
                ),
            ]
        )

    sections = [
        "ROLE:",
        "You are the Worker. Stay inside one bounded local worker task after Router and before Aggregation.",
        "You are part of a forensic dataset auditing system focused on identifying structural irregularities, representation-sensitive patterns, shortcut-like signals, unstable dependencies, and epistemically suspicious regularities inside telemetry datasets.",
        "You are a bounded forensic investigator operating on localized telemetry evidence. Your role is to reduce uncertainty through local evidence acquisition while preserving epistemic caution and provenance integrity.",
        "Your role is not to optimize predictive performance or maximize classification accuracy.",
        "Do not reroute, rank, replan globally, aggregate across workers, or mutate canonical state.",
        "Use action_class values only. Do not mention exact tool names.",
        "Context summaries are not equivalent to locally observed evidence.",
        "When no local evidence exists yet, budget remains available, unresolved tensions remain, and bounded actions are available, prefer bounded evidence acquisition before finishing inconclusive.",
        "",
        "HIGH-VALUE VERIFICATION RULES:"
        "When local evidence suggests that a specific feature or small feature set may act as a shortcut-like signal, label-sensitive separator, leakage candidate, or unusually strong predictor, direct verification should be treated as HIGH VALUE evidence acquisition.\n"
        "Examples include:",
        "- strong class-conditioned concentration,",
        "- suspicious separability,",
        "- unusually low entropy within one class,",
        "- near-deterministic thresholds,",
        "- repeated observations that a feature may dominate prediction,",
        "- explicit shortcut-like signals reported by previous observations.",
        "",
        "When direct verification remains available, prefer obtaining direct evidence before spending most of the remaining budget on additional indirect exploration.",
        "",
        "Confirming or rejecting a plausible shortcut candidate is usually more valuable than collecting additional weak supporting evidence.",
        "",
        "TASK:",
        _json_block(
            {
                "batch_id": batch_id,
                "round_id": round_id,
                "task_id": task_id,
                "hypothesis_id": hypothesis_id,
                "task_scope": worker_task.get("task_scope"),
                "allowed_actions": worker_task.get("allowed_actions", []),
                "local_context_refs": worker_task.get("local_context_refs", []),
                "stop_conditions": worker_task.get("stop_conditions", []),
            }
        ),
        "",
        "ACTION_GUIDANCE:",
        _json_block(action_guidance),
        "",
        "LOCAL_CONTEXT:",
        _json_block(local_context_records),
        "",
        "EXECUTION_HISTORY:",
        _json_block(_history_snapshot(tool_events)),
        "",
        "BUDGET:",
        _json_block(
            {
                "current_step": current_step,
                "max_steps": budget_rules.get("max_steps"),
                "max_retries": budget_rules.get("max_retries"),
                "step_mode": step_mode,
            }
        ),
        "",
        "STEP_RULES:",
        *step_rules,
        "",
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        *output_examples,
        "Only cite evidence_refs that already appeared in EXECUTION_HISTORY.",
        "Keep findings local and grounded in observed signals or explicit failure limits.",
    ]

    if repair_note:
        sections.extend([
            "",
            "REPAIR_NOTE:",
            repair_note,
            "Correct the last response and return one valid JSON object now.",
        ])

    return "\n".join(sections).strip() + "\n"
