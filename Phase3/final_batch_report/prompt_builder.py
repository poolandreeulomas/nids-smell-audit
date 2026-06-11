"""Prompt assembly for the Phase 3 Final Partition Audit Report Generator."""

from __future__ import annotations

import json
from typing import Any


PROMPT_VERSION = "phase3.final_batch_report.prompt.v1"


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, default=str)


def _indent(text: str, spaces: int = 2) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else "" for line in text.splitlines())


def _build_impact_rubric() -> str:
    return """Impact Assessment Rubric:

Impact measures: "If this finding is real and relevant, how much could it affect modelling outcomes?"

Impact must be assessed relative to the intended behavioural scenario described in the Partition Audit Context. The same finding may receive different impact assessments in different partition types.

Scale:
  0-20   Minimal expected modelling effect.
         Examples: cosmetic patterns, weak structural observations.

  21-40  Limited modelling influence.
         Examples: localized feature effects, small distribution shifts.

  41-60  Moderate modelling influence.
         Examples: meaningful feature redundancy, moderate dataset biases, localized shortcut risks.

  61-80  High modelling influence.
         Examples: strong class-conditioned artifacts, major dependency structures, significant shortcut signals.

  81-100 Potentially dominant modelling influence.
         Examples: near-deterministic shortcut features, severe leakage risks, major dataset construction artifacts, extreme structural distortions."""


def _build_confidence_rubric() -> str:
    return """Confidence Assessment Rubric:

Confidence measures: "How much evidence supports the current assessment?"

Confidence evaluates the assessment. It does NOT evaluate the importance of the finding.

Confidence must be driven primarily by:
  - investigation coverage
  - evidence quantity
  - evidence consistency
  - direct verification

NOT by:
  - severity
  - importance
  - intuition

Confidence should decrease when conclusions are primarily inferred from neighbouring evidence, analogous contexts, or indirect observations rather than directly verified.

Scale:
  0-20   Very limited evidence. Minimal investigation.

  21-40  Early evidence only. Large uncertainty remains.

  41-60  Moderate evidence. Several questions remain unresolved.

  61-80  Strong supporting evidence. Only limited uncertainty remains.

  81-100 Extensively investigated. Consistent evidence across multiple analyses. Few remaining uncertainties."""


def _build_report_example() -> str:
    return """Report Formatting Example:

## Strong Dependency Pairs
Impact: 72/100 (High)
Confidence: 89/100 (Strong)

This finding indicates that several features are near-perfect linear transformations of each other.

Why it matters:
These redundant features could cause multicollinearity issues in linear models, inflate feature importance estimates in tree-based models, and create misleading interpretability results. Models may learn to rely on artifact correlations rather than genuine structural signals.

Potential modelling implications:
- Feature selection should account for redundancy clusters
- Regularization strength may need adjustment
- Interpretation of feature importance requires cross-validation against de-correlated subsets

Remaining uncertainties:
The extent to which these dependencies are class-conditioned versus dataset-wide requires further investigation. The dependency structure may shift across different time windows."""


def _build_section_structure() -> str:
    return """Required Report Structure:

1. Partition Audit Context
   Explain: partition meaning, expected behavior, audit risks.
   Include the Intended Behavioral Scenario.

2. Executive Summary
   High-level synthesis. Researcher-oriented.
   Include: most important findings overview, overall risk profile, key modelling considerations, recommended next step.
   The Executive Summary should be readable in isolation.

    A researcher should be able to read only this section and understand:

    - what was being audited,
    - what the main risks are,
    - whether the partition appears trustworthy,
    - whether modelling should proceed.

3. Most Important Investigated Findings
   Detailed discussion. Deep explanations. Not bullet-point summaries.
   For each finding present: Finding, Impact Assessment, Confidence Assessment, Explanation, Why It Matters, Potential Modelling Implications, Remaining Uncertainties.
   Order by Impact Assessment (descending), then Confidence Assessment (descending).
   For each finding include:
    - Potential Modelling Implications
    - Potential Further Auditing Directions

4. Additional Findings And Open Risks
   Less investigated findings. Still discussed meaningfully.
   For each: Finding, Impact Assessment, Confidence Assessment, Why It Emerged, Potential Implications, Why More Investigation May Be Needed.
   Order by Estimated Impact Assessment (descending), then Confidence Assessment (descending).
   For each finding include:
    - Potential Modelling Implications
    - Potential Further Auditing Directions

5. Cross-Finding Interpretation
   Connect findings together.
   Questions: Are findings related? Do they reinforce each other? Do they point to a common underlying issue? Do they collectively increase or reduce risk?
    Discuss whether multiple findings may originate from the same underlying dataset characteristic.
    Discuss whether multiple findings together increase modelling risk beyond their individual impact assessments.
    Discuss whether findings collectively suggest:
    - shortcut learning opportunities
    - dataset construction artifacts
    - feature engineering artifacts
    - partition-specific behavioural effects 

6. Remaining Audit Gaps
   Explain: what remains uncertain, what was not explored, where confidence remains limited.
   Prioritize gaps according to:
    1. Expected impact if the gap hides a real issue.
    2. Current uncertainty.
    3. Cost-effectiveness of further investigation.

7. Auditor Recommendation
   Choose one: Ready For Modeling, Model With Caution, Additional Auditing Recommended.
   Must include justification.
   The recommendation must explicitly explain:
    - why modelling should or should not proceed,
    - which findings most strongly influenced the recommendation,
    - what conditions would change the recommendation."""
   


def build_final_batch_report_prompt(
    *,
    partition_name: str,
    partition_audit_context: dict[str, Any],
    intended_behavioral_scenario: str,
    researcher_audit_context: dict[str, Any],
    investigated_findings: list[dict[str, Any]],
    additional_findings: list[dict[str, Any]],
) -> str:
    """Build the complete report generation prompt.

    Args:
        partition_name: Human-readable partition name.
        partition_audit_context: Output from input_resolver.build_partition_audit_context().
        intended_behavioral_scenario: Deterministic scenario description.
        researcher_audit_context: Audit coverage summary.
        investigated_findings: Prioritized list of investigated findings.
        additional_findings: Prioritized list of additional findings.

    Returns:
        Complete prompt string ready for LLM consumption.
    """
    sections: list[str] = []

    # Section 1: Mission
    sections.append(
        "MISSION:\n"
        "You are the Final Partition Audit Report Generator.\n"
        "Your role is to transform a Final Updated State into a human-readable audit report.\n"
        "This is not a findings summary.\n"
        "\n"
        "This is a research audit report.\n"
        "\n"
        "The purpose of the report is to help a researcher:\n"
        "- understand the most important structural risks discovered,\n"
        "- understand which risks remain uncertain,\n"
        "- decide whether modelling can proceed safely,\n"
        "- decide where further auditing effort would have the highest value.\n"
        "\n"
        "The report should support both modelling decisions and continued auditing.\n"
        "You are not performing new analysis.\n"
        "You are not generating new findings.\n"
        "You are synthesizing the audit outcome.\n"
        "\n"
        "The report must explain:\n"
        "  - What was discovered?\n"
        "  - Why might it matter?\n"
        "  - How confident are we?\n"
        "  - What remains uncertain?\n"
        "  - What should a researcher do next?\n"
        "\n"
        "The report must NOT simply enumerate findings.\n"
        "The report must synthesize them into a coherent audit narrative.\n"
        "\n"
        "This report summarizes the results of a structural audit of a single dataset partition.\n"
        "The objective is to identify potential modelling risks, structural artifacts, dataset biases,\n"
        "shortcut signals, and unresolved uncertainties that may influence downstream model behaviour.\n"
        "The report is intended to support both modelling decisions and further auditing."
    )

    # Section 2: Partition Audit Context (MANDATORY)
    semantics_text = "\n".join(
        f"- {s}" for s in partition_audit_context.get("semantics", [])
    )
    expected_text = "\n".join(
        f"- {p}" for p in partition_audit_context.get("expected_properties", [])
    )
    warnings_text = "\n".join(
        f"- {w}" for w in partition_audit_context.get("epistemic_warnings", [])
    )
    guidance_text = "\n".join(
        f"- {g}" for g in partition_audit_context.get("investigation_guidance", [])
    )

    sections.append(
        f"PARTITION AUDIT CONTEXT:\n"
        f"Partition Name: {partition_name}\n"
        f"\n"
        f"Semantics:\n{_indent(semantics_text or 'No semantics available.')}\n"
        f"\n"
        f"Expected Properties:\n{_indent(expected_text or 'No expected properties available.')}\n"
        f"\n"
        f"Epistemic Warnings:\n{_indent(warnings_text or 'No epistemic warnings available.')}\n"
        f"\n"
        f"Investigation Guidance:\n{_indent(guidance_text or 'No investigation guidance available.')}\n"
        f"\n"
        f"INTENDED BEHAVIORAL SCENARIO:\n"
        f"{intended_behavioral_scenario}"
    )

    # Section 3: Researcher Audit Context
    total = researcher_audit_context.get("total_hypotheses", 0)
    investigated_count = researcher_audit_context.get("investigated_hypotheses", 0)
    less_explored_count = researcher_audit_context.get("less_explored_hypotheses", 0)
    revision_rounds = researcher_audit_context.get("revision_rounds", 0)
    major_updates = researcher_audit_context.get("major_updates", [])

    updates_text = "\n".join(f"- {u}" for u in major_updates) if major_updates else "No major updates recorded."

    sections.append(
        f"RESEARCHER AUDIT CONTEXT:\n"
        f"Total hypotheses that existed: {total}\n"
        f"Hypotheses that received meaningful investigation: {investigated_count}\n"
        f"Hypotheses that remained lightly explored: {less_explored_count}\n"
        f"Number of audit revisions: {revision_rounds}\n"
        f"\n"
        f"Major updates applied during auditing:\n{_indent(updates_text)}\n"
        f"\n"
        f"IMPORTANT: Describe what was audited, not only what was found.\n"
        f"Investigation depth and impact are independent. A lightly investigated finding\n"
        f"may still represent a major modelling risk. A heavily investigated finding may\n"
        f"ultimately have limited impact."
    )

    # Section 4: Impact Assessment Rubric
    sections.append(_build_impact_rubric())

    # Section 5: Confidence Assessment Rubric
    sections.append(_build_confidence_rubric())

    # Section 6: Explicit Rule
    sections.append(
        "CRITICAL RULE - Independence of Impact and Confidence:\n"
        "Impact and confidence are independent dimensions.\n"
        "A finding may have: High impact + low confidence.\n"
        "A finding may have: Low impact + high confidence.\n"
        "Both combinations are valid and must be represented accurately.\n"
        "Do not inflate confidence for high-impact findings.\n"
        "Do not deflate impact for low-confidence findings."
    )

    # Section 7: Report Example
    sections.append(
        f"REPORT FORMATTING EXAMPLE:\n{_build_report_example()}"
    )

    # Section 8: Report Structure
    sections.append(
        f"REQUIRED REPORT STRUCTURE:\n{_build_section_structure()}"
    )

    # Investigated Findings
    if investigated_findings:
        sections.append(
            f"INVESTIGATED FINDINGS (most important first):\n"
            f"{_json_block(investigated_findings)}\n"
            f"\n"
            f"These findings received substantial investigation effort.\n"
            f"Present them in Section 3 (Most Important Investigated Findings) of the report.\n"
            f"Provide deep explanations, not bullet-point summaries.\n"
            f"For each finding include: Finding, Impact Assessment, Confidence Assessment,\n"
            f"Explanation, Why It Matters, Potential Modelling Implications, Remaining Uncertainties."
        )
    else:
        sections.append(
            "INVESTIGATED FINDINGS: None. No findings received substantial investigation.\n"
            "State this clearly in the Executive Summary."
        )

    # Additional Findings
    if additional_findings:
        sections.append(
            f"ADDITIONAL FINDINGS (most important first):\n"
            f"{_json_block(additional_findings)}\n"
            f"\n"
            f"These findings received less investigation than the primary findings.\n"  
            f"They should not be treated as secondary risks.\n"
            f"Some may ultimately prove more important than the heavily investigated findings.\n"
            f"The lower confidence reflects investigation coverage, not estimated impact..\n"
            f"Present them in Section 4 (Additional Findings And Open Risks) of the report.\n"
            f"IMPORTANT: These findings are NOT necessarily low impact. They simply received less investigation.\n"
            f"Avoid language implying otherwise.\n"
            f"For each finding include: Finding, Impact Assessment, Confidence Assessment,\n"
            f"Why It Emerged, Potential Implications, Why More Investigation May Be Needed."
        )
    else:
        sections.append(
            "ADDITIONAL FINDINGS: None. All hypotheses received investigation.\n"
            "Note this in the report."
        )

    # Grounding Rules
    sections.append(
        "GROUNDING RULES:\n"
        "The report must never invent:\n"
        "  - evidence not present in the provided findings\n"
        "  - mechanisms not supported by the provided findings\n"
        "  - causal explanations not supported by the provided findings\n"
        "  - modelling implications not reasonably supported by the provided findings\n"
        "  - attack behaviours not described in the partition context\n"
        "  - dataset properties not described in the partition context\n"
        "\n"
        "Reasonable synthesis across findings is encouraged.\n"
        "Fabrication of new information is prohibited.\n"
        "Do not expose internal IDs, hypothesis IDs, evidence IDs, region IDs, revision counts, or timestamps.\n"
        "When discussing impact, always explain impact through the lens of model behaviour.\n"
        "\n"
        "Prefer explaining:\n"
        "\n"
        "- feature selection consequences\n"
        "- shortcut learning opportunities\n"
        "- representation distortions\n"
        "- evaluation risks\n"
        "- generalization risks\n"
        "\n"
        "rather than abstract severity statements.\n"
    )

    # Style Requirements
    sections.append(
        "STYLE REQUIREMENTS:\n"
        "The report should read like a research audit report, not a JSON summary.\n"
        "Use: paragraphs, explanations, reasoning, interpretation.\n"
        "Avoid: raw data dumps, implementation terminology, internal state language.\n"
        "The report should feel useful to an experienced researcher deciding whether to model or continue auditing.\n"
        "\n"
        "OUTPUT FORMAT:\n"
        "Return the complete report as Markdown text.\n"
        "Do not wrap in code fences. Do not add JSON wrapper.\n"
        "Start directly with the report title and content."
    )

    return "\n\n".join(sections).strip() + "\n"