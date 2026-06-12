"""Prompt assembly for the Phase 3A Final Batch Auditor component."""

from __future__ import annotations

import json
from typing import Any


PROMPT_VERSION = "phase3a.final_batch_auditor.prompt.v1"


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_final_batch_auditor_prompt(
    *,
    batch_id: str,
    final_audit_input: dict[str, Any],
    final_state_summary: dict[str, Any],
    round_history_summary: list[dict[str, Any]],
    process_signal_summary: dict[str, Any],
) -> str:
    sections = [
        "GLOBAL_MISSION:",
        "Inspect one completed batch investigation so the architecture remains debuggable, traceable, and contradiction-aware.",
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
        "This is terminal retrospective inspection, not future-round control.",
        "",
        "LOCAL_ROLE:",
        "You are the Final Batch Auditor for Phase 3A.",
        "Explain how the completed investigation behaved across rounds, what survived unresolved, and where the architecture visibly weakened.",
        "Stay debugging-oriented rather than polished, verdict-oriented, or researcher-facing.",
        "",
        "ARCHITECTURAL_BOUNDARIES:",
        "Do not mutate canonical state, do not rerank hypotheses, do not replan, do not reroute, and do not give future-round instructions.",
        "Preserve contradiction, uncertainty, and overlap pressure instead of forcing closure.",
        "Keep grounded evidence and interpretive conclusions distinct and traceable.",
        "Use only the provided summaries and artifact references.",
        
        "=== IMPACT CALIBRATION GUIDANCE ===",

        "Impact scores should reflect modelling risk,",
        "not only evidence certainty.",

        "LOW IMPACT (0-35)",

        "Examples:",
        "- weak correlation",
        "- small class imbalance",
        "- localized instability",
        "- weak dependency",

        "These findings may affect analysis but are",
        "unlikely to dominate model behaviour.",

        "MEDIUM IMPACT (35-70)",

        "Examples:",
        "- moderate feature dependence",
        "- regional concentration effects",
        "- partial class separability",
        "- instability affecting subsets of the dataset",

        "These findings can influence model behaviour",
        "but are unlikely to become dominant predictors.",

        "HIGH IMPACT (70-100)",

        "Examples:",
        "- low entropy within a class",
        "- dominant value concentration",
        "- strong class-conditioned separation",
        "- repeated independent confirmation",
        "- positive shortcut verification",
        "- near-deterministic predictive behaviour",

        "These findings indicate substantial risk that",
        "models may exploit representation-sensitive",
        "signals rather than learn the intended phenomenon.",

        "When multiple high-risk indicators co-occur,",
        "prefer scores in the upper impact range",
        "(80-100) rather than moderate scores."
        "",
        "FINAL_AUDIT_INPUT:",
        _json_block(final_audit_input),
        "",
        "FINAL_STATE_SUMMARY:",
        _json_block(final_state_summary),
        "",
        "ROUND_HISTORY_SUMMARY:",
        _json_block(round_history_summary),
        "",
        "PROCESS_SIGNAL_SUMMARY:",
        _json_block(process_signal_summary),
        "",
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        "trajectory_summary, hypothesis_summary, and failure_summary must stay compact and debugging-oriented.",
        "surviving_contradictions and open_pressures must preserve unresolved pressure instead of collapsing it.",
        "traceability_refs must use only evidence refs or artifact refs visible in the supplied context.",
        "Do not present canonical truth, polished conclusions, or future-round recommendations.",
        _json_block(
            {
                "debugging_audit_report": {
                    "batch_id": batch_id,
                    "trajectory_summary": "Across the completed rounds, investigation pressure stayed concentrated on one active framing while preserving one unresolved contradiction and limited overlap pressure.",
                    "hypothesis_summary": "hyp-1 remained active and gained local support, but its closure stayed incomplete because the contradiction survived into the final refined state.",
                    "surviving_contradictions": [
                        "Local verification still conflicts with the broader dependency framing."
                    ],
                    "open_pressures": [
                        "The final state still carries an unresolved closure gap for hyp-1.",
                        "Overlap pressure remained inspectable through the saved aggregation diagnostics rather than being collapsed away."
                    ],
                    "failure_summary": "The architecture stayed traceable, but investigation breadth remained narrow relative to the surviving contradiction pressure.",
                    "traceability_refs": [
                        "region-e1",
                        "task-hyp-1-1_step_01",
                        "state_manager.updated_batch_state",
                    ],
                }
            }
        ),
    ]

    return "\n".join(sections).strip() + "\n"
