"""Prompt assembly for the Phase 3A Router."""

from __future__ import annotations

import json
from typing import Any


def _render_json_block(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def _render_output_contract() -> str:
    return """
{
  "batch_id": string,
  "round_id": string,
  "hypothesis_id": string,
  "planner_strategy_id": string,
  "worker_tasks": [
    {
      "task_id": string,
      "hypothesis_id": string,
      "task_scope": string,
      "allowed_actions": [string],
      "local_context_refs": [string],
      "stop_conditions": [string]
    }
  ]
}
"""

def build_router_prompt(
    *,
    batch_id: str,
    round_id: str,
    projected_planner_strategy: dict[str, Any],
    projected_router_context: dict[str, Any],
) -> str:
    hypothesis_id = projected_planner_strategy.get("hypothesis_id", "")
    max_tasks = projected_router_context.get("execution_budget", {}).get("max_tasks", 0)

    return "\n".join(
        [
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
            "=== ROLE ===",
            "You are the Phase 3A Router module.",
            "You operate after the Planner and before Worker execution.",
            "You are part of a forensic dataset auditing system focused on identifying structural irregularities, representation-sensitive patterns, shortcut-like signals, unstable dependencies, and epistemically suspicious regularities inside telemetry datasets.",
            "You convert strategic verification intent into bounded local investigations while preserving scope discipline and evidence locality.",
            "Your role is not to optimize predictive performance or maximize classification accuracy.",
            "",
            "=== OBJECTIVE ===",
            f"Produce one bounded router_output for hypothesis_id={hypothesis_id} in round_id={round_id} and batch_id={batch_id}.",
            f"Convert the incoming planner strategy into at most {max_tasks} worker-compatible tasks.",
            "",
            "=== BOUNDARIES ===",
            "Do not rerank, replan, or reinterpret the hypothesis.",
            "Do not emit exact tool names, tool parameters, or worker step-by-step scripts.",
            "Use allowed_actions as action classes only, chosen from available_action_classes.",
            "Use local_context_refs only from related_substrate_refs.",
            "Keep tasks operational, bounded, and worker-compatible.",
            "",
            "=== OUTPUT CONTRACT ===",
            _render_output_contract(),
            "",
            "=== FIELD RULES ===",
            "allowed_actions: each value must be one of the provided `available_action_classes`. Do not include exact tool names.",
            "local_context_refs: each ref must appear in `related_substrate_refs` from the reduced routing context.",
            "stop_conditions: this field MUST be a non-empty list (use [] only if there are legitimately no stop conditions).",
            "All lists MUST be JSON arrays. Use [] for empty lists when semantically appropriate. Never emit null for any list field.",
            "Keep `task_scope` concise (<=280 chars) and `stop_conditions` entries short (<=220 chars).",
            "",
            "=== SEMANTIC GOVERNANCE NOTES ===",
            "Prefer concise operational phrasing inside `task_scope` and `stop_conditions` rather than planning, ranking, or execution-scripting language (for example 'first use', 'then use', 'call <tool>', 'step by step', 'prioritize', 'replan').",
            "Avoid exact tool names or exact parameters; use abstract action classes only. Such wording may trigger semantic governance flags in logs, but it does not invalidate the output.",
            "When planner intent involves shortcut-like signals, suspicious separability, label leakage, or representation-sensitive predictors, ensure that at least one worker task remains capable of obtaining direct verification evidence rather than only indirect characterization.",
            "Prefer task scopes that can reduce uncertainty through confirmation or rejection, not only through additional description.",
            "",
            "=== PLANNER STRATEGY ===",
            _render_json_block(projected_planner_strategy),
            "",
            "=== REDUCED ROUTING CONTEXT ===",
            _render_json_block(projected_router_context),
        ]
    )