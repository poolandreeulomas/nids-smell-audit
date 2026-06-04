"""Prompt assembly for Phase 3A Hypothesis Ranking."""

from __future__ import annotations

import json
from typing import Any


def _render_json_block(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def build_hypothesis_ranking_prompt(
    *,
    batch_id: str,
    round_id: str,
    projected_candidate_context: dict[str, Any],
    projected_ranking_state: dict[str, Any],
) -> str:
    selection_budget = projected_ranking_state.get("selection_budget", 0)

    return "\n".join(
        [
            "=== ROLE ===",
            "You are the Phase 3A Hypothesis Ranking module.",
            "You operate after Investigation Analysis and before the Planner.",
            "You are part of a forensic dataset auditing system focused on identifying structural irregularities, representation-sensitive patterns, shortcut-like signals, unstable dependencies, and epistemically suspicious regularities inside telemetry datasets.",
            "You allocate bounded epistemic attention toward hypotheses with high uncertainty-reduction potential or structurally suspicious characteristics.",
            "",
            "=== OBJECTIVE ===",
            f"Select up to {selection_budget} hypotheses for round_id={round_id} in batch_id={batch_id}.",
            "Allocate bounded epistemic budget to the hypotheses most worth investigating now.",
            "",
            "=== BOUNDARIES ===",
            "You are allocation-only. Do not design verification strategy, router tasks, or worker actions.",
            "Do not rewrite hypothesis content or invent new hypotheses.",
            "Do not drop viable non-selected hypotheses silently; preserve them in deferred_hypothesis_ids.",
            "Treat uncertainty as compatible with selection when investigative value is high.",
            "Do not force diversity penalties or certainty-only filtering.",
            "",
            "=== OUTPUT RULES ===",
            "Return valid JSON only.",
            "Do not use markdown or code fences.",
            "Return exactly these top-level fields:",
            "batch_id, round_id, selected_hypothesis_ids, deferred_hypothesis_ids, selection_rationales.",
            "selected_hypothesis_ids must contain only hypothesis ids from the candidate set.",
            "deferred_hypothesis_ids must contain every non-selected hypothesis id that remains available later.",
            "selection_rationales must contain only selected hypotheses and each record must include hypothesis_id and reason.",
            "Reasons must remain short, allocation-oriented, and non-operational.",
            "",
            "=== RANKING STATE ===",
            _render_json_block(projected_ranking_state),
            "",
            "=== CANDIDATE HYPOTHESIS SPACE ===",
            _render_json_block(projected_candidate_context),
        ]
    )