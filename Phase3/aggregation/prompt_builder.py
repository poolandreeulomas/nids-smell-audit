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
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        "Only cite evidence_refs that appear in SOURCE_WORKER_RESULTS.",
        'For preserved_contradiction_ids: output ID STRINGS ONLY, never contradiction text.',
        'IDs must come from SOURCE_CONTRADICTIONS shown above.',
        'Do not invent, summarize, paraphrase, merge, or synthesize contradiction text.',
        'Do not include a "preserved_contradictions" field in your output — only preserved_contradiction_ids.',
        "Keep update_focus state-facing and grounded, but do not describe state mutation.",
        "",
        "=== OUTPUT SCHEMA ===",
        _json_block(
            {
                "aggregation_handoff": {
                    "batch_id": batch_id,
                    "round_id": round_id,
                    "hypothesis_id": hypothesis_id,
                    "merged_findings": ["grounded merged finding"],
                    "evidence_refs": ["source evidence_ref"],
                    "preserved_contradiction_ids": ["contr_1", "contr_2"],
                    "open_gaps": ["remaining unresolved gap or limitation"],
                    "update_focus": "orientation for the touched interpretive area",
                }
            }
        ),
        "",
        "=== EXAMPLES ===",
        'GOOD (ID only):  "preserved_contradiction_ids": ["contr_0", "contr_3"]',
        'BAD (no text):  "preserved_contradictions": ["some text here"]',
        'BAD (no text):  "preserved_contradiction_ids": ["Unknown ref that is not in SOURCE_CONTRADICTIONS"]',
    ]

    return "\n".join(sections).strip() + "\n"
