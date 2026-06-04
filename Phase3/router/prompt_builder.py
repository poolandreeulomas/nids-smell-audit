"""Prompt assembly for the Phase 3A Router."""

from __future__ import annotations

import json
from typing import Any


def _render_json_block(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


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
            "=== OUTPUT RULES ===",
            "Return valid JSON only.",
            "Do not use markdown or code fences.",
            "Return exactly these top-level fields:",
            "batch_id, round_id, hypothesis_id, planner_strategy_id, worker_tasks.",
            "Each worker_task must contain exactly:",
            "task_id, hypothesis_id, task_scope, allowed_actions, local_context_refs, stop_conditions.",
            "REQUIREMENTS for these fields:",
            "- `allowed_actions`: a JSON LIST of short strings. Each value must be one of the provided `available_action_classes`. Do not include exact tool names.",
            "- `local_context_refs`: a JSON LIST of short strings. Each ref must appear in `related_substrate_refs` from the reduced routing context.",
            "- `stop_conditions`: a JSON LIST of short strings describing termination criteria for the task. This field MUST be a non-empty list (use [] only if there are legitimately no stop conditions).",
            "All lists MUST be JSON arrays. Use [] for empty lists when semantically appropriate. Never emit null for any list field.",
            "Keep `task_scope` concise (<=280 chars) and `stop_conditions` entries short (<=220 chars).",
            "=== CANONICAL JSON SHAPES ===",
            "Use these exact nested shapes. Do not flatten, rename keys, or change types.",
            "router_output (top-level):",
            "{",
            '  "batch_id": "...",',
            '  "round_id": "...",',
            '  "hypothesis_id": "...",',
            '  "planner_strategy_id": "...",',
            '  "worker_tasks": [',
            "    {",
            '      "task_id": "task_1",',
            '      "hypothesis_id": "hyp_42",',
            '      "task_scope": "Short operational task description",',
            '      "allowed_actions": ["action_a", "action_b"],',
            '      "local_context_refs": ["region_3", "evidence_e12"],',
            '      "stop_conditions": ["collected N=1000 samples", "distribution stabilized"]',
            "    }",
            "  ]",
            "}",
            "=== SEMANTIC GOVERNANCE NOTES ===",
            "Prefer concise operational phrasing inside `task_scope` and `stop_conditions` rather than planning, ranking, or execution-scripting language (for example 'first use', 'then use', 'call <tool>', 'step by step', 'prioritize', 'replan').",
            "Avoid exact tool names or exact parameters; use abstract action classes only. Such wording may trigger semantic governance flags in logs, but it does not invalidate the output.",
            "",
            "=== PLANNER STRATEGY ===",
            _render_json_block(projected_planner_strategy),
            "",
            "=== REDUCED ROUTING CONTEXT ===",
            _render_json_block(projected_router_context),
        ]
    )