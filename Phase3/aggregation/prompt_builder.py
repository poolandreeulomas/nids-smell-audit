"""Prompt assembly for the Phase 3A Aggregation component."""

from __future__ import annotations

import json
from typing import Any


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _render_contradiction_block(source_contradictions: list[dict[str, Any]]) -> str:
    if not source_contradictions:
        return "SOURCE_CONTRADICTIONS: []"
    lines = ["SOURCE_CONTRADICTIONS:"]
    for c in source_contradictions:
        lines.append(f'  id={c["id"]}  text="{c["text"]}"')
    return "\n".join(lines)


def _render_output_contract() -> str:
    return """
{
  "aggregation_handoff": {
    "batch_id": string,
    "round_id": string,
    "hypothesis_id": string,
    "merged_findings": [string],
    "evidence_refs": [string],
    "preserved_contradiction_ids": [string],
    "open_gaps": [string],
    "update_focus": string
  }
}
"""


def build_aggregation_prompt(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    normalized_inputs: dict[str, Any],
) -> str:
    source_contradictions = normalized_inputs.get("source_contradictions", [])
    sections = [
        "ROLE:",
        "You are Aggregation. Stay inside one hypothesis-local, round-local merge after Worker and before State Manager.",
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
        "Do not reroute, replan, mutate canonical state, emit critic feedback, or summarize raw traces.",
        "Preserve grounded contradictions and unresolved gaps instead of flattening them away.",
        "",
        "TASK:",
        _json_block(
            {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "worker_result_count": normalized_inputs.get("worker_result_count", 0),
                "expected_task_ids": normalized_inputs.get("expected_task_ids", []),
                "selected_task_ids": normalized_inputs.get("selected_task_ids", []),
            }
        ),
        "",
        "SOURCE_WORKER_RESULTS:",
        _json_block(normalized_inputs.get("worker_results", [])),
        "",
        "OVERLAP_DIAGNOSTICS:",
        _json_block(normalized_inputs.get("overlap_diagnostics", [])),
        "",
        _render_contradiction_block(source_contradictions),
        "",
        "OUTPUT CONTRACT (typed JSON tree — this is the authoritative schema):",
        _render_output_contract(),
        "",
        "=== FIELD RULES ===",
        "Only cite evidence_refs that appear in SOURCE_WORKER_RESULTS.",
        'For preserved_contradiction_ids: output ID STRINGS ONLY, never contradiction text.',
        'IDs must come from SOURCE_CONTRADICTIONS shown above.',
        'Do not invent, summarize, paraphrase, merge, or synthesize contradiction text.',
        'Do not include a "preserved_contradictions" field in your output — only preserved_contradiction_ids.',
        "Keep update_focus state-facing and grounded, but do not describe state mutation.",
        "",
        "=== EXAMPLES ===",
        'GOOD (ID only):  "preserved_contradiction_ids": ["contr_0", "contr_3"]',
        'BAD (no text):  "preserved_contradictions": ["some text here"]',
        'BAD (no text):  "preserved_contradiction_ids": ["Unknown ref that is not in SOURCE_CONTRADICTIONS"]',
    ]

    return "\n".join(sections).strip() + "\n"