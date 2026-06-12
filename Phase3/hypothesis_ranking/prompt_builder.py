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


def _render_investigation_coverage_section(
    projected_ranking_state: dict[str, Any],
) -> str:
    hypothesis_state_refs = projected_ranking_state.get("hypothesis_state_refs")
    if not isinstance(hypothesis_state_refs, list):
        return ""

    previously_selected: list[str] = []
    not_yet_selected: list[str] = []

    for ref in hypothesis_state_refs:
        if not isinstance(ref, dict):
            continue
        hypothesis_id = ref.get("hypothesis_id", "")
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            continue

        state_notes = ref.get("state_notes")
        if not isinstance(state_notes, list):
            continue

        revision_count = 0
        for note in state_notes:
            if isinstance(note, str) and note.startswith("revision_count="):
                try:
                    revision_count = int(note.split("=", 1)[1])
                except (ValueError, IndexError):
                    revision_count = 0
                break

        if revision_count > 0:
            previously_selected.append(f"* {hypothesis_id}")
        else:
            not_yet_selected.append(f"* {hypothesis_id}")

    lines = [
        "=== INVESTIGATION COVERAGE ===",
        "",
        "Previously Selected:",
    ]

    if previously_selected:
        lines.extend(previously_selected)
    else:
        lines.append("* (none)")

    lines.append("")
    lines.append("Not Yet Selected:")

    if not_yet_selected:
        lines.extend(not_yet_selected)
    else:
        lines.append("* (none)")

    lines.append("")
    lines.append("Interpretation:")
    lines.append("")
    lines.append("Previously Selected hypotheses have already received investigation attention but may still contain unresolved questions.")
    lines.append("")
    lines.append("Not Yet Selected hypotheses have not yet received direct investigation attention.")
    lines.append("")
    lines.append("Selection history is an attention-allocation signal, not a resolution signal.")
    lines.append("")
    lines.append("Previously Selected DOES NOT mean resolved.")
    lines.append("")
    lines.append("Not Yet Selected DOES NOT mean correct.")
    lines.append("")

    if not_yet_selected:
        lines.append("When one or more Not Yet Selected hypotheses exist:")
        lines.append("")
        lines.append("At least one selection slot should normally be allocated to that group unless the evidence strongly indicates that continued investigation of already-selected hypotheses is substantially more valuable.")

    lines.append("")
    lines.append("Important:")
    lines.append("")
    lines.append("This section is informational.")
    lines.append("")

    return "\n".join(lines)


def _render_output_contract() -> str:
    return """
{
  "batch_id": string,
  "round_id": string,
  "selected_hypothesis_ids": [string],
  "deferred_hypothesis_ids": [string],
  "selection_rationales": [
    {
      "hypothesis_id": string,
      "reason": string
    }
  ]
}
"""

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

    coverage_section = _render_investigation_coverage_section(
        projected_ranking_state
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
            "=== OUTPUT CONTRACT ===",
            _render_output_contract(),
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
            coverage_section,
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
            "Hypothesis involving potential  shortcut learning, label leakage, or suspicious separability are of high priority",
            "",
            "Repeated selection is allowed.",
            "=== MAINTAIN INVESTIGATION COVERAGE ===",
            "",
            "The ranking stage is responsible for allocating",
            "attention across the available hypothesis space.",
            "If one or more hypotheses have never been selected:",
            "- You MUST allocate at least one selection slot to a never-selected hypothesis.",
            "Coverage is mandatory.",
            "When two hypotheses appear similarly valuable, prefer the allocation that improves overall investigation quality rather than automatically reinforcing prior selections.",
            "",
            "Selection history signals such as times_selected and rounds_since_last_selected are provided to help reason about prior attention allocation.",
            "These signals are advisory and should not be treated as hard penalties.",
            "",
            "Hypothesis involving potential  shortcut learning, label leakage, or suspicious separability may deserve continued selection until direct verification (when there is too strong a shortcut signal to ignore but not enough evidence to confirm or reject).",
            "A hypothesis that has already received substantial investigation attention may still be selected IF there is strong evidence that additional investigation is likely to produce meaningful findings.",
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
            "=== FIELD RULES ===",
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