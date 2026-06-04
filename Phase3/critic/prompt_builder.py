"""Prompt assembly for the Phase 3A Critic component."""

from __future__ import annotations

import json
from typing import Any

from critic.contracts import MAX_MODULE_FEEDBACK_ITEMS


PROMPT_VERSION = "phase3a.critic.prompt.v1"


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_critic_prompt(
    *,
    batch_id: str,
    round_id: str,
    critic_input_min: dict[str, Any],
    refined_state_summary: dict[str, Any],
    module_behavior_summaries: list[dict[str, Any]],
    process_signal_summary: dict[str, Any],
) -> str:
    sections = [
        "GLOBAL_MISSION:",
        "Improve future-round investigation behavior without taking control away from the existing modules.",
        "Critique process quality, not hypothesis truth.",
        "",
        "LOCAL_ROLE:",
        "You are Critic. Review one completed non-final round after State Manager and emit bounded reflective feedback.",
        "You receive compact input/output summaries for the observed components plus the refined end-of-round state result.",
        "Emit precise prompt-appendable corrections for observed modules only.",
        "Do not mutate canonical state, do not rerank, do not replan, do not reroute, and do not issue direct execution commands.",
        "",
        "ARCHITECTURAL_BOUNDARIES:",
        "Use only the bounded summaries and runtime references provided here.",
        f"Return no more than {MAX_MODULE_FEEDBACK_ITEMS} module_feedback items.",
        "Suggestions must stay short, behavioral, and advisory.",
        "",
        "TASK:",
        _json_block(
            {
                "batch_id": batch_id,
                "round_id": round_id,
                "critic_input_min": critic_input_min,
            }
        ),
        "",
        "REFINED_STATE_SUMMARY:",
        _json_block(refined_state_summary),
        "",
        "MODULE_BEHAVIOR_SUMMARIES:",
        _json_block(module_behavior_summaries),
        "",
        "PROCESS_SIGNAL_SUMMARY:",
        _json_block(process_signal_summary),
        "",
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        "Every module_feedback item must include module_name, observed_issue, evidence_refs, and suggestion.",
        "Use only evidence_refs that are visible in the provided summaries.",
        "Suggestions should be short enough to append directly to future module prompts.",
        "Do not claim truth authority over hypotheses or instruct the runtime to execute tools, rerank hypotheses, or mutate canonical state.",
        _json_block(
            {
                "critic_feedback_payload": {
                    "batch_id": batch_id,
                    "round_id": round_id,
                    "module_feedback": [
                        {
                            "module_name": "state_manager",
                            "observed_issue": "The round is carrying forward process friction without narrowing the verification target enough.",
                            "evidence_refs": ["task-hyp-1-1_step_01"],
                            "suggestion": "Keep the next round focused on one explicit closure test before broadening the investigation again.",
                        }
                    ],
                }
            }
        ),
    ]

    return "\n".join(sections).strip() + "\n"
