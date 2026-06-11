"""Prompt assembly for the Phase 3A State Manager component."""

from __future__ import annotations

import json
from typing import Any

from state_manager.contracts import VALID_HYPOTHESIS_STATUSES


PROMPT_VERSION = "phase3a.state_manager.prompt.v1"


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def build_state_manager_prompt(
    *,
    batch_id: str,
    round_id: str,
    hypothesis_id: str,
    state_manager_context: dict[str, Any],
) -> str:
    sections = [
        "GLOBAL_MISSION:",
        "Preserve one evidence-grounded canonical batch state for the active batch.",
        "The grounded structural substrate is stable. Only the targeted interpretive hypothesis may change here.",
        "",
        "LOCAL_ROLE:",
        "You are State Manager. Apply one conservative, evidence-referenced, hypothesis-local update after Aggregation and before Critic or the next planning round.",
        "Do not rewrite the structural substrate, re-aggregate worker results, reroute work, replan strategy, or emit critic feedback.",
        "",
        "ARCHITECTURAL_BOUNDARIES:",
        "Prefer patch-style updates over whole-state reconstruction.",
        "Carry forward contradictions, open gaps, and traceable evidence unless the current inputs explicitly justify a bounded shift.",
        "Only emit the resulting state delta record for the targeted hypothesis.",
        "",
        "TASK:",
        _json_block(
            {
                "batch_id": batch_id,
                "round_id": round_id,
                "hypothesis_id": hypothesis_id,
                "previous_state_version": state_manager_context.get("state_version", 0),
            }
        ),
        "",
        "CURRENT_TARGET_STATE:",
        _json_block(state_manager_context.get("target_hypothesis", {})),
        "",
        "STRUCTURAL_SUBSTRATE_REFERENCE:",
        _json_block(state_manager_context.get("structural_substrate_ref", {})),
        "",
        "RECENT_REVISION_CONTEXT:",
        _json_block(state_manager_context.get("recent_revision_log", [])),
        "",
        "AGGREGATION_HANDOFF:",
        _json_block(state_manager_context.get("aggregation_handoff", {})),
        "",
        "OPEN_GAP_PERSISTENCE_RULES:",
        "open_gaps are persistent state, not transient handoff data.",
        "Start from CURRENT_TARGET_STATE.open_gaps.",
        "Treat newly observed open gaps from the handoff as additions to the existing state.",
        "Do NOT replace the existing open_gaps list with the handoff list.",
        "A previously existing open gap may only disappear if it is explicitly resolved.",
        "Any resolved open gap must be documented in applied_updates.",
        "Removing an existing open gap without an explicit resolution is invalid.",
        "",
        "CONTRADICTION_PERSISTENCE_RULES:",
        "Start from CURRENT_TARGET_STATE.preserved_contradictions.",
        "Treat newly observed contradictions from the handoff as additive.",
        "Do not remove prior contradictions unless explicitly resolved and documented in applied_updates.",
        "",
        "MERGED_FINDINGS_PERSISTENCE_RULES:",
        "Start from CURRENT_TARGET_STATE.merged_findings.",
        "Merge newly supported findings from the handoff.",
        "Do not silently remove previously accepted findings.",
        "",
        "",
        "IMMUTABLE_STATE_ITEMS_RULE:",
        "For merged_findings, open_gaps, preserved_contradictions, and evidence_refs:",
        "Treat all items already present in CURRENT_TARGET_STATE as immutable state records.",
        "When constructing the final state:",
        "1. Copy every existing item from CURRENT_TARGET_STATE verbatim.",
        "2. Append genuinely new items from AGGREGATION_HANDOFF.",
        "3. Never rewrite, paraphrase, summarize, merge, replace, deduplicate, or remove an existing item.",
        "4. Existing items may only disappear if explicitly resolved and documented in applied_updates using the corresponding field name.",
        "5. Semantic equivalence is not sufficient. Existing items must be preserved as exact strings.",
        "If uncertain whether a new item replaces an existing item, preserve both.",
        "",
        "VERBATIM_PERSISTANCE_RULES:",
        "When carrying forward existing presered_contradictions, open_gaps, or merged_findings, copy the exact text from the CURRENT_TARGET_STATE.",
        "Do not paraphrase, rewrite, normalize, summarize, merge or restate existing entries.",
        "If a prior entry remains valid, reproduce it verbatim in the resulting state.",
        "",
        "STATE UPDATE MODEL:",
        "result_open_gaps = prior_open_gaps + newly_discovered_open_gaps + explicitly_resolved_open_gaps",
        "result_contradictions = prior_contradictions + newly_preserved_contradictions + explicitly_resolved_contradictions",
        "result_merged_findings = prior_findings + newly_supported_findings + explicitly_retracted_findings",
        "",
        "STRICT OUTPUT CONTRACT:",
        "The output schema is closed.",
        "The object inside state_delta_record must contain exactly and only the following fields:",
        "* batch_id",
        "* round_id",
        "* hypothesis_id",
        "* summary",
        "* status",
        "* evidence_refs",
        "* preserved_contradictions",
        "* open_gaps",
        "* merged_findings",
        "* update_focus",
        "* applied_updates",
        "Do NOT emit any additional fields.",
        "Forbidden examples include:",
        "* last_updated_round",
        "* revision_count",
        "* state_version",
        "* timestamp",
        "* confidence",
        "* metadata",
        "If an additional field is emitted, the response will fail validation.",
        "Do not attempt to track revision counters, state versions, timestamps, or bookkeeping information inside the state_delta_record.",
        "",
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        "The output lists must represent the resulting target-hypothesis state after this round, not only the newly introduced items.",
        "Preserve all current and newly supplied evidence_refs, preserved_contradictions, open_gaps, and merged_findings unless a field is genuinely unchanged and already present.",
        "If any open_gaps remain unresolved, keep them explicit; if one is resolved, state that resolution in applied_updates.",
        f"Use only these status values: {sorted(VALID_HYPOTHESIS_STATUSES)}.",
        "Do not mention planning, worker execution, routing, critic supervision, or canonical-state commit mechanics in the content fields.",
        _json_block(
            {
                "state_delta_record": {
                    "batch_id": batch_id,
                    "round_id": round_id,
                    "hypothesis_id": hypothesis_id,
                    "summary": "updated concise interpretive summary for the target hypothesis",
                    "status": "active",
                    "evidence_refs": ["carried-forward evidence_ref"],
                    "preserved_contradictions": ["explicit unresolved contradiction"],
                    "open_gaps": ["remaining unresolved verification gap"],
                    "merged_findings": ["resulting evidence-grounded finding carried in state"],
                    "update_focus": "short orientation for the touched interpretive area",
                    "applied_updates": [
                            {
                                "field": "summary",
                                "reason": "why this bounded change is justified..."
                            },
                            {
                                "field": "merged_findings",
                                "reason": "new findings were added while preserving all prior findings"
                            },   
                    ],
                    
                }
            }
        ),
    ]

    return "\n".join(sections).strip() + "\n"
