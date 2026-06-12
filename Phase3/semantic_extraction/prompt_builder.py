"""Prompt assembly for Phase 3A Semantic Extraction."""

from __future__ import annotations

import json
from typing import Any

from semantic_extraction.contracts import (
    VALID_LOCALITY_SCOPE_TYPES,
    VALID_REGION_KINDS,
    VALID_REGION_STATUSES,
)


def _render_json_block(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def _render_output_contract() -> str:
    return """{
  "substrate_id": string,
  "batch_id": string,
  "compressed_regions": [
    {
      "region_id": string,
      "region_kind": string,
      "status": string,
      "summary": string,
      "structural_descriptors": [string],
      "feature_scope": {
        "features": [string],
        "feature_groups": [string],
        "locality": {
          "scope_type": string,
          "scope_value": string,
          "localized": boolean,
          "notes": [string]
        }
      },
      "evidence_refs": [string],
      "supporting_patterns": [string],
      "contextual_modifiers": [string],
      "uncertainty_notes": [string],
      "contradiction_refs": [string],
      "tension_refs": [string]
    }
  ],
  "preserved_weak_signals": [
    {
      "weak_signal_id": string,
      "descriptor": string,
      "feature_scope": {
        "features": [string],
        "feature_groups": [string],
        "locality": {
          "scope_type": string,
          "scope_value": string,
          "localized": boolean,
          "notes": [string]
        }
      },
      "evidence_refs": [string],
      "preservation_reason": string,
      "contextual_modifiers": [string],
      "uncertainty_notes": [string]
    }
  ],
  "contradictions": [
    {
      "contradiction_id": string,
      "contradiction_kind": string,
      "description": string,
      "feature_scope": {
        "features": [string],
        "feature_groups": [string],
        "locality": {
          "scope_type": string,
          "scope_value": string,
          "localized": boolean,
          "notes": [string]
        }
      },
      "supporting_evidence_refs": [string],
      "conflicting_evidence_refs": [string],
      "context_notes": [string],
      "downstream_relevance": string
    }
  ],
  "unresolved_tensions": [
    {
      "tension_id": string,
      "description": string,
      "related_region_ids": [string],
      "evidence_refs": [string],
      "context_notes": [string],
      "reason_unresolved": string
    }
  ]
}"""


def build_semantic_extraction_prompt(
    *,
    batch_id: str,
    projected_evidence: dict[str, Any],
    normalized_partition_context: dict[str, list[str]],
) -> str:
    region_kinds = ", ".join(sorted(VALID_REGION_KINDS))
    region_statuses = ", ".join(sorted(VALID_REGION_STATUSES))
    locality_scope_types = ", ".join(sorted(VALID_LOCALITY_SCOPE_TYPES))

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
            "You are the Phase 3A Semantic Extraction module.",
            "Your job is to compress grounded overview evidence into a broad structural substrate.",
            "You are part of a forensic dataset auditing system focused on identifying structural irregularities, representation-sensitive patterns, shortcut-like signals, unstable dependencies, and epistemically suspicious regularities inside telemetry datasets.",
            "Your role is not to optimize predictive performance or maximize classification accuracy.",
            "Your role is to preserve uncertainty, isolate bounded observable patterns, and support investigation of potentially misleading, unstable, shortcut-like, or structurally concentrated signals.",
            "",
            "=== OBJECTIVE ===",
            f"Initialize the structural substrate for batch_id={batch_id}.",
            "Preserve broad structural regions, weak but coherent signals, contradictions, and unresolved tensions.",
            "",
            "=== BOUNDARIES ===",
            "Use partition context only to temper interpretation, never to validate evidence.",
            "Do not generate hypotheses.",
            "Do not prioritize, rank, plan, route, or recommend next steps.",
            "Do not introduce causal explanations or artifact-family conclusions.",
            "=== SEMANTIC GOVERNANCE NOTES ===",
            "Prefer descriptive, probabilistic, and evidence-based phrasing in explanation fields (for example `uncertainty_notes` and `contextual_modifiers`).",
            "Action, causal, and validation wording such as 'artifact', 'cause', 'causal', 'validate', 'confirm', 'prove', 'hypothesis', 'plan', 'prioritiz(e|ation)', 'route', or 'worker' may trigger semantic governance flags in logs, but it does not invalidate the output.",
            "When practical, rewrite those phrases into descriptive or evidence-based formulations. Examples:",
            "- Instead of 'X causes Y' write 'X may be associated with Y' or 'evidence is consistent with an association between X and Y'.",
            "- Instead of 'we should validate' write 'this pattern is consistent with the evidence and may merit further validation' or 'evidence supports additional verification steps'.",
            "- Instead of 'artifact' write 'observable pattern' or 'signal consistent with a family of artifacts'.",
            "Keep `uncertainty_notes` descriptive, probabilistic, and grounded; causal or operational wording is observable telemetry rather than a blocking condition.",
            "Keep the output compact and grounded in the provided evidence IDs.",
            "",
            "=== OUTPUT CONTRACT ===",
            _render_output_contract(),
            "",
            "=== FIELD RULES ===",
            f"Allowed region_kind values: {region_kinds}.",
            f"Allowed status values: {region_statuses}.",
            f"Allowed locality.scope_type values: {locality_scope_types}.",
            "features MUST be a non-empty JSON list. If no concrete feature names are present in the overview evidence, choose one representative feature from projected_evidence.feature_scope_refs (prefer the top-ranked) or use the sentinel __dataset__ explicitly to indicate a pure partition-level observation. Never emit an empty list for features.",
            "Use [] for empty lists. Never emit null for any list field.",
            "All evidence_refs must cite only evidence_id values present in the overview evidence input.",
            "",
            "=== NESTED TYPE RULES ===",
            "feature_scope.features must be a JSON array of strings.",
            "feature_scope.feature_groups must be a JSON array of strings.",
            "feature_scope.locality.scope_type must be one of the allowed locality scope types.",
            "feature_scope.locality.scope_value must be a string.",
            "feature_scope.locality.localized must be a boolean.",
            "feature_scope.locality.notes must be a JSON array of strings.",
            "",
            "=== PARTITION CONTEXT ===",
            _render_json_block(normalized_partition_context),
            "",
            "=== PROJECTED OVERVIEW EVIDENCE ===",
            _render_json_block(projected_evidence),
        ]
    )