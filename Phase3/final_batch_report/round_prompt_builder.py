"""Prompt assembly for Phase 3A Round-Level Final Reports.

Builds an evidence-grounded prompt instructing the LLM to generate a comprehensive,
readable Markdown report strictly reflecting the evidence and state transitions of a single round.
"""

from __future__ import annotations

import json
from typing import Any

from final_batch_report.round_contracts import (
    ROUND_REPORT_PROMPT_VERSION,
    ROUND_REPORT_SECTIONS,
)


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, default=str)


def build_round_report_prompt(
    round_context: dict[str, Any],
) -> str:
    """Build the LLM prompt for single-round Final Report generation.

    Args:
        round_context: Output from resolve_round_report_context().

    Returns:
        Rendered prompt string with strict grounding instructions and structured evidence.
    """
    exec_id = round_context.get("execution_identity", {})
    round_id = exec_id.get("round_id", "round-001")
    partition_name = exec_id.get("partition_name", "unknown")
    intended_scenario = round_context.get("intended_behavioral_scenario", "")
    partition_context = round_context.get("partition_audit_context", {})
    objectives = round_context.get("investigation_objectives", {})
    evidence = round_context.get("round_evidence", {})
    state_transitions = round_context.get("state_transitions", {})
    provenance = round_context.get("provenance_and_limitations", {})

    prompt_lines = [
        "You are the Phase 3A Round Report Generator for ATLAS, an automated audit system for Network Intrusion Detection Datasets (NIDS).",
        "",
        f"Your task is to generate a formal, researcher-oriented Markdown audit report for Round {round_id} on partition '{partition_name}'.",
        "",
        "=== STRICT AUDIT & REPORTING INSTRUCTIONS ===",
        "1. GROUND ALL CLAIMS IN EVIDENCE: Report only findings supported by the supplied round evidence and tool executions.",
        "2. DISTINGUISH LEVELS OF CERTAINTY: Explicitly separate raw observations (tool outputs), verified empirical evidence, and interpretations (hypotheses).",
        "3. INCLUDE NUMERICAL VALUES: Whenever numerical metrics (e.g. Pearson correlation, p-values, duplicate rates, entropy, class distributions) are present in the evidence, cite the exact numbers.",
        "4. EXPLAIN NIDS SHORTCUT-LEARNING RELEVANCE: Explain why each observed artifact matters to NIDS modeling integrity (e.g. models learning non-causal shortcuts or dataset artifacts instead of intrusion behavior).",
        "5. SEPARATE ROUND EVIDENCE FROM PRIOR STATE: Explicitly distinguish new evidence gathered in this round from conclusions inherited from earlier rounds or initialization.",
        "6. HIGHLIGHT GAPS & CONTRADICTIONS: Document unresolved hypotheses, contradictions, and missing evidence without trying to smooth over uncertainties.",
        "7. AVOID DEFINITIVE DATASET CLAIMS: Do not claim this single round proves or disproves overall dataset validity. Mark findings as provisional where appropriate.",
        "8. NO FABRICATION: Do not invent statistics, feature names, tool calls, findings, or state transitions not present in the supplied context.",
        "9. RESPECT PARTITION CONTEXT: Use the supplied behavioral scenario and domain context to interpret results, but never treat general domain context as evidence of a finding.",
        "",
        "=== REQUIRED MARKDOWN REPORT STRUCTURE ===",
        "You MUST structure the report using the following 9 sections as Markdown headings (level 1 or 2):",
        "",
        f"# Round Report: {round_id} ({partition_name})",
        "",
        "## 1. Execution Identity and Status",
        "Summarize round metadata: Round ID, batch ID, partition, analysis mode, start/end state versions, and execution status.",
        "",
        "## 2. Executive Summary",
        "High-level researcher summary: What was investigated in this round, what the primary empirical findings are, key risks discovered, and overall round outcome.",
        "",
        "## 3. Investigation Objectives and Hypotheses",
        "Detail the hypotheses targeted during this round, why they were prioritized, and the specific worker tasks planned.",
        "",
        "## 4. Investigation Process and Tools Used",
        "Describe the tools executed during the round, features examined, action classes used, and how workers explored the feature space.",
        "",
        "## 5. Evidence and Statistical Results",
        "Present the empirical results and numerical metrics (correlations, duplicate counts, distribution statistics) gathered from tool calls. Quote exact values.",
        "",
        "## 6. Findings and Their Interpretation",
        "Analyze the findings in detail: What structural patterns or shortcut opportunities do they reveal? What is the impact on NIDS models trained on this partition?",
        "",
        "## 7. State Changes and Critic Assessment",
        "Detail how the canonical state evolved during this round: Which hypotheses were confirmed, updated, disproven, or left unresolved. Include the Critic's assessment and guidance.",
        "",
        "## 8. Unresolved Questions and Contradictions",
        "Document preserved contradictions, open gaps, and questions that remain unanswered after this round's investigation.",
        "",
        "## 9. Limitations and Evidence Provenance",
        "State execution limitations, validation warnings, missing data, source artifact references, and the single-round scope notice.",
        "",
        "=== AUDIT CONTEXT & STRUCTURED EVIDENCE ===",
        "",
        "--- Execution Identity ---",
        _json_block(exec_id),
        "",
        "--- Partition & Behavioral Scenario ---",
        f"Partition Context:\n{_json_block(partition_context)}\n\nIntended Behavioral Scenario:\n{intended_scenario}",
        "",
        "--- Investigation Objectives & Worker Tasks ---",
        _json_block(objectives),
        "",
        "--- Round-Specific Evidence & Numerical Results ---",
        _json_block(evidence),
        "",
        "--- State Transitions & Revision Records ---",
        _json_block(state_transitions),
        "",
        "--- Provenance & Limitations ---",
        _json_block(provenance),
        "",
        "=== GENERATION DIRECTIVE ===",
        "Produce the full Markdown report now. Do not wrap the entire output in a markdown code block (```markdown). Output clean, beautifully formatted Markdown starting with '# Round Report: ...'.",
    ]

    return "\n".join(prompt_lines)

