"""Prompt assembly for the Phase 3A Worker with investigation-stage reasoning."""

from __future__ import annotations

import json
from typing import Any


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _history_snapshot(tool_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a compact execution history from tool events (last 10)."""
    snapshot: list[dict[str, Any]] = []
    for event in tool_events[-10:]:
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


def _render_reasoning_only_contract() -> str:
    return """
{
  "decision": string,
  "reasoning": string
}"""


def _render_action_contract() -> str:
    return """
{
  "decision": string,
  "reasoning": string,
  "actions": [
    {
      "action_class": string,
      "context_ref": string,
      "feature_name": string
    }
  ]
}"""


def _render_finish_contract() -> str:
    return """
{
  "decision": string,
  "reasoning": string,
  "worker_result": {
    "task_id": string,
    "hypothesis_id": string,
    "status": string,
    "findings": [
      string
    ],
    "evidence_refs": [
      string
    ],
    "contradictions": [
      string
    ],
    "limitations": [
      string
    ]
  }
}"""


def _step_investigation_stage(current_step: int, max_steps: int) -> str:
    """Map step index to investigation stage."""
    if current_step >= max_steps:
        return "final_synthesis"
    mapping = {
        1: "bootstrap",
        2: "strategy_refinement",
        3: "evidence_acquisition_1",
        4: "interpretation",
        5: "evidence_acquisition_2",
        6: "investigation_review",
        7: "final_verification",
    }
    return mapping.get(current_step, "evidence_acquisition")


def _build_bootstrap_objectives() -> list[str]:
    return [
        "BOOTSTRAP OBJECTIVES",
        "",
        "Review:",
        "- hypothesis",
        "- task goal",
        "- feature summaries",
        "- local evidence",
        "",
        "Identify:",
        "- important features",
        "- likely investigation directions",
        "- key uncertainties",
        "",
        "Create:",
        "- initial investigation strategy",
        "- verification priorities",
        "- coverage targets",
        "",
        "Do not request actions.",
        "Do not draw conclusions.",
    ]


def _build_strategy_refinement_objectives() -> list[str]:
    return [
        "STRATEGY REFINEMENT OBJECTIVES",
        "",
        "Review current strategy.",
        "",
        "Determine:",
        "- highest priority targets",
        "- most important unanswered questions",
        "- highest-value evidence",
        "",
        "Identify:",
        "- what remains unknown",
        "- what should be verified first",
        "",
        "Prepare for evidence acquisition.",
        "",
        "Do not request actions.",
    ]


def _build_evidence_acquisition_objectives() -> list[str]:
    return [
        "ACTION OBJECTIVES",
        "",
        "Select actions that maximize:",
        "1. uncertainty reduction",
        "2. task progress",
        "3. verification value",
        "",
        "Prioritize:",
        "- direct verification",
        "- unresolved high-priority targets",
        "- unresolved task questions",
        "",
        "Avoid redundant exploration.",
    ]


def _build_interpretation_objectives() -> list[str]:
    return [
        "INTERPRETATION OBJECTIVES",
        "",
        "Review new evidence.",
        "",
        "Determine:",
        "- what changed",
        "- what gained support",
        "- what weakened",
        "",
        "Update investigation strategy.",
        "Update priorities.",
        "Update unresolved questions.",
        "",
        "Interpret evidence.",
        "Do not summarize.",
    ]


def _build_investigation_review_objectives() -> list[str]:
    return [
        "INVESTIGATION REVIEW OBJECTIVES",
        "",
        "Determine:",
        "- what has been resolved",
        "- what remains unresolved",
        "- whether direct verification remains available",
        "",
        "Identify remaining obligations.",
    ]


def _build_final_verification_objectives() -> list[str]:
    return [
        "FINAL VERIFICATION OBJECTIVES",
        "",
        "Prioritize:",
        "- unresolved task questions",
        "- unresolved high-priority targets",
        "- contradiction resolution",
        "",
        "Avoid exploratory actions.",
        "Focus on closure.",
    ]


def _build_final_synthesis_objectives() -> list[str]:
    return [
        "FINAL SYNTHESIS OBJECTIVES",
        "",
        "Produce:",
        "- findings",
        "- evidence",
        "- contradictions",
        "- limitations",
        "",
        "Assign status based on:",
        "- evidence quality",
        "- investigation completeness",
        "- remaining uncertainty",
        "",
        "Do not generate new hypotheses.",
    ]


def _build_investigation_stage_objectives(stage: str) -> list[str]:
    mapping = {
        "bootstrap": _build_bootstrap_objectives,
        "strategy_refinement": _build_strategy_refinement_objectives,
        "evidence_acquisition_1": _build_evidence_acquisition_objectives,
        "interpretation": _build_interpretation_objectives,
        "evidence_acquisition_2": _build_evidence_acquisition_objectives,
        "investigation_review": _build_investigation_review_objectives,
        "final_verification": _build_final_verification_objectives,
        "final_synthesis": _build_final_synthesis_objectives,
    }
    builder = mapping.get(stage, _build_evidence_acquisition_objectives)
    return builder()


def _build_investigation_memory(
    current_investigation_memory: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the investigation memory section from system-provided state."""
    if current_investigation_memory and isinstance(current_investigation_memory, dict):
        memory = dict(current_investigation_memory)
    else:
        memory = {}

    return {
        "task_goal": memory.get("task_goal", "Not yet defined."),
        "current_strategy": memory.get("current_strategy", "Not yet defined."),
        "high_priority_targets": list(memory.get("high_priority_targets", [])),
        "verified_targets": list(memory.get("verified_targets", [])),
        "remaining_targets": list(memory.get("remaining_targets", [])),
        "open_questions": list(memory.get("open_questions", [])),
    }


def _build_coverage_tracking(
    current_investigation_memory: dict[str, Any] | None,
) -> dict[str, list[str]]:
    """Build coverage tracking from system-provided investigation memory."""
    if not current_investigation_memory or not isinstance(current_investigation_memory, dict):
        return {
            "verified_targets": [],
            "remaining_targets": [],
        }
    return {
        "verified_targets": list(current_investigation_memory.get("verified_targets", [])),
        "remaining_targets": list(current_investigation_memory.get("remaining_targets", [])),
    }


def _build_completion_guidance() -> list[str]:
    return [
        "COMPLETION GUIDANCE",
        "",
        "Do not conclude while:",
        "",
        "- high-priority targets remain unverified",
        "- direct verification opportunities remain available",
        "- key task questions remain unresolved",
        "",
        "Coverage supports task completion.",
        "Coverage is not itself the task objective.",
        "Do not require verification of every feature.",
        "Focus on task resolution.",
    ]


def _build_investigation_guidance_lines(stage: str) -> list[str]:
    """Build stage-specific guidance about the investigation process."""
    guidance = {
        "bootstrap": [
            "This is the bootstrap stage. Build your initial investigation strategy.",
            "Do not request actions. Do not draw conclusions.",
        ],
        "strategy_refinement": [
            "This is a strategy refinement step. Review and prioritize before acquiring evidence.",
            "Do not request actions.",
        ],
        "evidence_acquisition_1": [
            "This is an evidence acquisition step. Request actions to gather the highest-value evidence.",
            "Focus on uncertainty reduction and task progress.",
        ],
        "interpretation": [
            "This is an interpretation step. Review new evidence and update your understanding.",
            "Do not request actions.",
        ],
        "evidence_acquisition_2": [
            "This is an evidence acquisition step. Focus on reducing remaining uncertainty.",
            "Prioritize unresolved questions and high-priority targets.",
        ],
        "investigation_review": [
            "This is an investigation review step. Evaluate completeness and identify remaining obligations.",
            "Do not request actions.",
        ],
        "final_verification": [
            "This is a final verification step. Close remaining gaps before concluding.",
            "Prioritize unresolved task questions. Avoid exploratory actions.",
        ],
        "final_synthesis": [
            "This is the final synthesis step. Produce conclusions based on all evidence collected.",
            "Do not propose actions.",
        ],
    }
    return guidance.get(stage, ["Continue the investigation."])


def _build_feature_summaries(
    local_context_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract compact feature summaries from local context records.

    Uses structured signals and metrics from feature_summary() outputs
    rather than free-text parsing whenever possible.
    """
    summaries: list[dict[str, Any]] = []
    seen_features: set[str] = set()
    for record in local_context_records:
        if not isinstance(record, dict):
            continue
        context_ref = str(record.get("context_ref") or "")
        feature_names = list(record.get("feature_names") or [])
        source_items = list(record.get("source_items") or [])
        for feature_name in feature_names:
            if feature_name in seen_features:
                continue
            seen_features.add(feature_name)
            signals: list[str] = []
            for source in source_items:
                if not isinstance(source, dict):
                    continue
                source_kind = str(source.get("source_kind") or "")
                summary_text = str(source.get("summary") or "")
                # Prefer structured signals from feature_summary outputs
                if source_kind == "feature_summary":
                    summary_lower = summary_text.lower()
                    for token in summary_lower.split(","):
                        token = token.strip()
                        if token in ("low_variance", "low_diversity", "high_variance_imbalance"):
                            signals.append(token)
                # Fallback text matching for non-structured sources
                else:
                    if "low_variance" in summary_text.lower():
                        signals.append("low_variance")
                    if "low_diversity" in summary_text.lower():
                        signals.append("low_diversity")
                    if "high_variance" in summary_text.lower() or "variance_ratio" in summary_text.lower():
                        signals.append("high_variance_imbalance")
            summaries.append(
                {
                    "feature": feature_name,
                    "context_ref": context_ref,
                    "signals": sorted(set(signals)),
                    "source_count": len(source_items),
                }
            )
    return summaries


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
    investigation_memory: dict[str, Any] | None = None,
) -> str:
    task_id = str(worker_task.get("task_id") or "unknown_task")
    hypothesis_id = str(worker_task.get("hypothesis_id")
                        or "unknown_hypothesis")
    max_steps = int(budget_rules.get("max_steps") or 0)
    investigation_stage = _step_investigation_stage(current_step, max_steps)
    investigation_stage_objectives = _build_investigation_stage_objectives(
        investigation_stage)
    investigation_guidance = _build_investigation_guidance_lines(
        investigation_stage)

    # Determine step mode for contract selection
    is_reasoning_stage = investigation_stage in {
        "bootstrap", "strategy_refinement", "interpretation", "investigation_review"
    }
    is_action_stage = investigation_stage in {
        "evidence_acquisition_1", "evidence_acquisition_2", "final_verification"
    }
    is_final_synthesis = investigation_stage == "final_synthesis"
    # Coverage tracking starts at step 5 (evidence_acquisition_2 onward)
    has_coverage_tracking = investigation_stage in {
        "evidence_acquisition_2", "investigation_review", "final_verification", "final_synthesis"
    }
    # Completion guidance for step 7 (final_verification) and step 8 (final_synthesis)
    has_completion_guidance = investigation_stage in {
        "final_verification", "final_synthesis"
    }

    output_examples: list[str] = []
    step_rules: list[str] = []

    if is_reasoning_stage:
        step_rules.extend(
            [
                "This is a reasoning-only step.",
                "Do not propose actions and do not finish the task on this step.",
                "Return decision='continue' with a short bounded reasoning update.",
            ]
        )

        output_examples.extend(
            [
                "=== OUTPUT CONTRACT ===",
                _render_reasoning_only_contract(),
                "",
                "=== FIELD RULES ===",
                "decision must be 'continue'.",
            ]
        )

    elif is_action_stage:
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
                "IF decision='action':",
                _render_action_contract(),
                "",
                "FIELD RULES:",
                "decision must be 'action'.",
                "action_class must be one of the allowed action classes.",
                "context_ref must be one of the allowed local_context_refs.",
                "related_feature_name must be a non-empty string when present.",
                "related_feature_name is OPTIONAL.",
                "IF NOT REQUIRED, OMIT THE FIELD COMPLETELY.",
                "DO NOT EMIT related_feature_name WITH '', ' ', null, OR ANY EMPTY VALUE.",
                "ONLY INCLUDE related_feature_name FOR RELATIONSHIP-STYLE ACTIONS THAT REQUIRE A SECOND FEATURE.",
                "",
                "IF decision='continue':",
                _render_reasoning_only_contract(),
                "",
                "FIELD RULES:",
                "decision must be 'continue'.",
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
                "=== OUTPUT CONTRACT ===",
                _render_finish_contract(),
                "",
                "=== FIELD RULES ===",
                "decision must be 'finish'.",
                "status must be one of: completed, partial, failed, inconclusive.",
            ]
        )

    sections: list[str] = [
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
        "=== CRITICAL OUTPUT COMPLIANCE REQUIREMENT ===",
        "",
        "THE OUTPUT CONTRACT IS THE HIGHEST PRIORITY REQUIREMENT IN THIS PROMPT.",
        "",
        "BEFORE RETURNING ANY RESPONSE:",
        "",
        "1. VERIFY THAT THE RESPONSE EXACTLY MATCHES THE REQUIRED OUTPUT SCHEMA.",
        "2. VERIFY THAT NO REQUIRED FIELD IS MISSING.",
        "3. VERIFY THAT NO EXTRA FIELD IS PRESENT.",
        "4. VERIFY THAT ALL ENUM VALUES ARE VALID.",
        "5. VERIFY THAT ALL REQUIRED LISTS ARE PRESENT AND CORRECTLY TYPED.",
        "6. IF ANY PART OF THE RESPONSE WOULD VIOLATE THE OUTPUT CONTRACT, REVISE THE RESPONSE BEFORE RETURNING IT.",
        "",
        "OUTPUT CONTRACT COMPLIANCE TAKES PRIORITY OVER REASONING COMPLETENESS.",
        "",
        "DO NOT RETURN AN APPROXIMATE RESPONSE.",
        "DO NOT RETURN A PARTIALLY VALID RESPONSE.",
        "DO NOT RETURN ADDITIONAL EXPLANATIONS.",
        "DO NOT RETURN MARKDOWN.",
        "DO NOT RETURN CODE FENCES.",
        "",
        "DO NOT INFER PERMITTED OUTPUTS.",
        "DO NOT GENERALIZE THE SCHEMA.",
        "ONLY EMIT FIELDS AND VALUES EXPLICITLY ALLOWED.",
        "",
        "FINAL CHECK:",
        "",
        "IMMEDIATELY BEFORE PRODUCING THE RESPONSE,",
        "PERFORM A SELF-CHECK AGAINST THE OUTPUT RULES.",
        "",
        "IF THE RESPONSE DOES NOT SATISFY EVERY OUTPUT RULE,",
        "REWRITE IT BEFORE RETURNING IT.",
        "",
        "OUTPUT VALIDITY IS MORE IMPORTANT THAN ANALYSIS QUALITY.",
        "",
        "RETURN ONLY A FULLY VALID OUTPUT OBJECT.",
        "",
        "HIGH-VALUE VERIFICATION RULES:",
        "When local evidence suggests that a specific feature or small feature set may act as a shortcut-like signal, label-sensitive separator, leakage candidate, or unusually strong predictor, direct verification should be treated as HIGH VALUE evidence acquisition.",
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
    ]

    # Phase 2: Feature summaries injected only during bootstrap (step 1)
    if investigation_stage == "bootstrap":
        feature_summaries = _build_feature_summaries(local_context_records)
        if feature_summaries:
            sections.extend([
                "",
                "FEATURE_SUMMARIES:",
                _json_block(feature_summaries),
                "",
                "These are bootstrap information to help initialize your investigation.",
                "They will not appear in subsequent steps.",
                "Use them to identify suspicious features and prioritize investigations.",
            ])

    # Phase 3: Investigation memory — system-provided reference state
    investigation_memory_block = _build_investigation_memory(
        investigation_memory)
    sections.extend([
        "",
        "INVESTIGATION_MEMORY:",
        _json_block(investigation_memory_block),
        "",
        "Use INVESTIGATION_MEMORY as the current investigation reference.",
        "The 'task_goal' describes what you need to resolve.",
        "The 'current_strategy' describes the investigation approach.",
        "'high_priority_targets' are features that most need verification.",
        "'verified_targets' are features already confirmed.",
        "'remaining_targets' are features still needing verification.",
        "'open_questions' are unresolved questions that need answers.",
    ])

    # Phase 5: Coverage tracking (starts at step 5)
    if has_coverage_tracking:
        coverage = _build_coverage_tracking(investigation_memory)
        sections.extend([
            "",
            "COVERAGE_TRACKING:",
            _json_block(coverage),
        ])

    # Phase 6: Completion guidance (steps 7 and 8)
    if has_completion_guidance:
        sections.extend([
            "",
            *_build_completion_guidance(),
        ])

    sections.extend([
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
                "step_mode": investigation_stage,
            }
        ),
        "",
        "INVESTIGATION_STAGE:",
        investigation_stage.replace("_", " ").title(),
        "",
        *investigation_guidance,
        "",
        *investigation_stage_objectives,
        "",
        "STEP_RULES:",
        *step_rules,
        "",
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        *output_examples,
        "Only cite evidence_refs that already appeared in EXECUTION_HISTORY.",
        "Keep findings local and grounded in observed signals or explicit failure limits.",
    ])

    if repair_note:
        sections.extend([
            "",
            "REPAIR_NOTE:",
            repair_note,
            "Correct the last response and return one valid JSON object now.",
        ])

    return "\n".join(sections).strip() + "\n"