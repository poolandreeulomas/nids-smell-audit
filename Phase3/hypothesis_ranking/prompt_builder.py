"""Prompt assembly for Phase 3A Hypothesis Ranking."""

from __future__ import annotations

import json
from typing import Any


def _render_json_block(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def _render_critic_guidance_section(critic_guidance: list[str] | None) -> str:
    normalized_guidance = [
        snippet.strip()
        for snippet in critic_guidance or []
        if isinstance(snippet, str) and snippet.strip()
    ]

    if not normalized_guidance:
        return "\n".join(
            [
                "=== CRITIC GUIDANCE ===",
                "No critic guidance is available for this round.",
                "This is expected during early rounds.",
                "Proceed using the ranking state and candidate hypothesis information only.",
                "",
            ]
        )

    return "\n".join(
        [
            "=== CRITIC GUIDANCE ===",
            "Critic guidance represents higher-order observations about investigation behavior across prior rounds.",
            "These observations are derived from investigation history, ranking history, and investigation outcomes.",
            "They should be treated as important signals about search quality and epistemic allocation.",
            "",
            "Critic guidance is NOT a hard constraint.",
            "However, it should meaningfully influence allocation decisions when compatible with available evidence.",
            "",
            *[f"- {snippet}" for snippet in normalized_guidance],
            "",
        ]
    )


def build_hypothesis_ranking_prompt(
    *,
    batch_id: str,
    round_id: str,
    projected_candidate_context: dict[str, Any],
    projected_ranking_state: dict[str, Any],
    critic_guidance: list[str] | None = None,
) -> str:
    selection_budget = projected_ranking_state.get("selection_budget", 0)

    critic_guidance_block = _render_critic_guidance_section(
        critic_guidance
    )

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
            "You are allocation-only.",
            "Do not design verification strategy, router tasks, or worker actions.",
            "Do not rewrite hypothesis content or invent new hypotheses.",
            "Do not drop viable non-selected hypotheses silently; preserve them in deferred_hypothesis_ids.",
            "Treat uncertainty as compatible with selection when investigative value is high.",
            "Do not force diversity penalties or certainty-only filtering.",
            "",
            "=== SELECTION PRINCIPLES ===",
            "Balance expected information gain, unresolved uncertainty, prior investigation investment, and critic observations.",
            "",
            "Repeated selection is allowed.",
            "However, repeated selection should be justified by continuing uncertainty-reduction potential or meaningful expected information gain.",
            "",
            "When two hypotheses appear similarly valuable, prefer the allocation that improves overall investigation quality rather than automatically reinforcing prior selections.",
            "",
            "Selection history signals such as times_selected and rounds_since_last_selected are provided to help reason about prior attention allocation.",
            "These signals are advisory and should not be treated as hard penalties.",
            "",
            "Hypothesis involving potential  shortcut learning, label leakage, or suspicious separability may deserve continued seletion until direct verification (when there is too strong a shortcut signal to ignore but not enough evidence to confirm or reject).",
            "A hypothesis that has already received substantial investigation attention may still be selected IF there is strong evidence that additional investigation is likely to produce meaningful findings.",
            "",
            "A hypothesis that has received little or no attention may deserve consideration if critic guidance or current uncertainty suggests potential value.",
            "",
            "=== EXPLORATION GUIDANCE ===",
            "Investigation quality depends on both exploitation AND exploration.",
            "",
            "When selection_budget >= 3, AVOID allocating all available budget to the same repeatedly selected hypothesis set unless there is strong evidence that all selected hypotheses continue to provide substantially higher expected information gain than every alternative.",
            "",
            "Prefer maintaining AT LEAST ONE exploration-oriented allocation slot WHEN plausible alternatives exist.",
            "",
            "Exploration-oriented selections should favor hypotheses that:",
            "- have received comparatively little investigation attention,",
            "- remain epistemically unresolved,",
            "- MAY REVEAL HIGH-IMPACT structural issues if confirmed,",
            "- or represent important untested explanations not covered by currently dominant hypotheses.",
            "",
            "A hypothesis should NOT be selected solely because it is underexplored.",
            "However, underexplored hypotheses with meaningful potential value deserve periodic investigation.",
            "",
            "Repeated concentration on the same hypothesis subset across many rounds requires stronger justification than early-round concentration.",
            "",
            critic_guidance_block,
            "=== CRITIC INTERPRETATION RULES ===",
            "When critic guidance is available, incorporate it as an additional ranking signal.",
            "",
            "Do not blindly follow critic guidance.",
            "Do NOT IGNORE critic guidance without reason.",
            "",
            "When critic guidance suggests broader exploration, consider WHETHER continued concentration on the same active hypotheses remains justified.",
            "",
            "When critic guidance highlights productive active lines, continued investment in those hypotheses may be appropriate.",
            "",
            "If strong local evidence and critic guidance point in different directions, attempt to balance both considerations rather than treating either as absolute.",
            "",
            "=== OUTPUT RULES ===",
            "Return valid JSON only.",
            "Do not use markdown or code fences.",
            "Return exactly these top-level fields:",
            "batch_id, round_id, selected_hypothesis_ids, deferred_hypothesis_ids, selection_rationales.",
            "",
            "selected_hypothesis_ids must contain only hypothesis ids from the candidate set.",
            "deferred_hypothesis_ids must contain every non-selected hypothesis id that remains available later.",
            "",
            "selection_rationales must contain only selected hypotheses and each record must include hypothesis_id and reason.",
            "",
            "Reasons must remain short, allocation-oriented, and non-operational.",
            "",
            "=== RANKING STATE ===",
            _render_json_block(projected_ranking_state),
            "",
            "=== CANDIDATE HYPOTHESIS SPACE ===",
            _render_json_block(projected_candidate_context),
        ]
    )