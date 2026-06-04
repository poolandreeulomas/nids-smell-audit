"""Prompt assembly for the Phase 3A Aggregation component."""

from __future__ import annotations

import json
from typing import Any


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_aggregation_prompt(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    normalized_inputs: dict[str, Any],
) -> str:
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
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        "Only cite evidence_refs that appear in SOURCE_WORKER_RESULTS.",
        "Only preserve contradictions that already appear in SOURCE_WORKER_RESULTS.",
        "Keep update_focus state-facing and grounded, but do not describe state mutation.",
        _json_block(
            {
                "aggregation_handoff": {
                    "batch_id": batch_id,
                    "round_id": round_id,
                    "hypothesis_id": hypothesis_id,
                    "merged_findings": ["grounded merged finding"],
                    "evidence_refs": ["source evidence_ref"],
                    "preserved_contradictions": ["unresolved source contradiction"],
                    "open_gaps": ["remaining unresolved gap or limitation"],
                    "update_focus": "orientation for the touched interpretive area",
                }
            }
        ),
    ]

    return "\n".join(sections).strip() + "\n"
