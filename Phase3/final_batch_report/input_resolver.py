"""Resolve report inputs from the Final Updated State (CanonicalBatchState).

Phase 3a:
  - Build Partition Audit Context (using existing partition descriptors)
  - Build Intended Behavioral Scenario (deterministic, not LLM-generated)
  - Build Researcher Audit Context (audit coverage summary)
  - Build Finding Inventory (investigated vs additional)
  - Finding Prioritization (lightweight ranking score, not shown to users)
  - Internal ID Removal (strip hypothesis IDs, evidence IDs, region IDs)

Phase 3b:
  - Resolve batch reports from disk (locate .md files)
  - Load batch report content
  - Load coverage data from coverage_builder JSON output
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from judge.context_loader import get_judge_partition_context, resolve_judge_partition_phenomenon
from semantic_extraction.input_builder import build_partition_context
from state.schema import CanonicalBatchState

from final_batch_report.contracts import CICIDS2017_PARTITION_SCENARIOS

logger = logging.getLogger(__name__)


# ── Phase 3a — Report context resolution from state ────────────────────────

_INTERNAL_ID_RE = __import__("re").compile(
    r"\b(?:e\d+|hyp_\d+|region_\d+|task_\d+_step_\d+)\b",
    __import__("re").IGNORECASE,
)


def _strip_internal_ids(text: str) -> str:
    cleaned = _INTERNAL_ID_RE.sub("[reference]", str(text or ""))
    cleaned = __import__("re").sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return list(dict.fromkeys(normalized))


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


# ─── Responsibility 1: Build Partition Audit Context ──────────────────────

def build_partition_audit_context(partition_name: str) -> dict[str, Any]:
    """Build partition audit context using existing partition descriptors.

    Reuses `judge.context_loader.get_judge_partition_context()` and
    `semantic_extraction.input_builder.build_partition_context()`.
    """
    raw_context = build_partition_context(partition_name)

    semantics = _string_list(raw_context.get("partition_semantics", []))
    expected_properties = _string_list(
        raw_context.get("expected_structural_properties", [])
    )
    epistemic_warnings = _string_list(raw_context.get("epistemic_warnings", []))
    investigation_guidance = _string_list(
        raw_context.get("investigation_guidance", [])
    )



    return {
        "partition_name": partition_name,
        "semantics": [
            _strip_internal_ids(s) for s in semantics
        ],
        "expected_properties": [
            _strip_internal_ids(p) for p in expected_properties
        ],
        "epistemic_warnings": [
            _strip_internal_ids(w) for w in epistemic_warnings
        ],
        "investigation_guidance": [
            _strip_internal_ids(g) for g in investigation_guidance
        ],
    }


# ─── Responsibility 2: Build Intended Behavioral Scenario ─────────────────

def build_intended_behavioral_scenario(partition_name: str) -> str:
    """Build intended behavioral scenario deterministically (not LLM-generated).

    Maps partition name to a phenomenon, then looks up the scenario description.
    Falls back to a generic network traffic scenario.
    """
    phenomenon = resolve_judge_partition_phenomenon(partition_name)

    if phenomenon and phenomenon in CICIDS2017_PARTITION_SCENARIOS:
        return CICIDS2017_PARTITION_SCENARIOS[phenomenon]

    # Generic fallback
    return (
        "This partition models network traffic behavior. "
        "Expected characteristics depend on the specific attack or benign "
        "scenario represented. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    )


# ─── Responsibility 3: Build Researcher Audit Context ─────────────────────

def build_researcher_audit_context(
    canonical_state: CanonicalBatchState,
) -> dict[str, Any]:
    """Build researcher audit context explaining how much auditing occurred."""
    hypotheses = canonical_state.interpretive_hypotheses
    total_hypotheses = len(hypotheses)

    # Investigated: revision_count > 0 OR non-empty merged_findings
    investigated_hypotheses = [
        h for h in hypotheses
        if h.revision_count > 0 or (h.merged_findings and len(h.merged_findings) > 0)
    ]
    less_explored_hypotheses = [
        h for h in hypotheses if h not in investigated_hypotheses
    ]

    revision_log = canonical_state.revision_log
    revision_rounds = len(revision_log)

    # Collect major updates from revision log (top 10)
    major_updates = []
    for record in revision_log[:10]:
        if record.applied_updates:
            for update in record.applied_updates:
                if isinstance(update, dict):
                    desc = update.get("description") or ""
                    if desc:
                        major_updates.append(_strip_internal_ids(desc))
                elif isinstance(update, str):
                    major_updates.append(_strip_internal_ids(update))

    return {
        "total_hypotheses": total_hypotheses,
        "investigated_hypotheses": len(investigated_hypotheses),
        "less_explored_hypotheses": len(less_explored_hypotheses),
        "revision_rounds": revision_rounds,
        "major_updates": major_updates[:10],  # keep bounded
    }


# ─── Responsibility 4: Build Finding Inventory ───────────────────────────

def _classify_finding(hypothesis: Any) -> str:
    """Classify a hypothesis as 'investigated' or 'additional'.

    Investigated: revision_count > 0 OR non-empty merged_findings.
    NOT using 'active'/'resolved'/'unresolved' as report-facing concepts.
    """
    if hasattr(hypothesis, "revision_count"):
        rev_count = hypothesis.revision_count
    else:
        rev_count = _int_value(hypothesis.get("revision_count", 0) if isinstance(hypothesis, dict) else 0)

    if hasattr(hypothesis, "merged_findings"):
        merged = hypothesis.merged_findings
    else:
        merged = hypothesis.get("merged_findings", []) if isinstance(hypothesis, dict) else []

    if rev_count > 0 or (merged and len(merged) > 0):
        return "investigated"
    return "additional"


def build_finding_inventory(
    canonical_state: CanonicalBatchState,
) -> dict[str, list[dict[str, Any]]]:
    """Build finding inventory classifying findings into investigated and additional.

    Does NOT use active/resolved/unresolved as report-facing concepts.
    """
    investigated_findings: list[dict[str, Any]] = []
    additional_findings: list[dict[str, Any]] = []

    for hypothesis in canonical_state.interpretive_hypotheses:
        classification = _classify_finding(hypothesis)

        finding = {
            "evidence_count": len(hypothesis.evidence_refs or []),
            "summary": _strip_internal_ids(hypothesis.summary or ""),
            "status": hypothesis.status,
            "merged_findings": [
                _strip_internal_ids(f)
                for f in _string_list(hypothesis.merged_findings)
            ],
            "open_gaps": [
                _strip_internal_ids(g)
                for g in _string_list(hypothesis.open_gaps)
            ],
            "preserved_contradictions": [
                _strip_internal_ids(c)
                for c in _string_list(hypothesis.preserved_contradictions)
            ],
            "revision_count": hypothesis.revision_count,
            "last_updated_round": hypothesis.last_updated_round,
        }

        if classification == "investigated":
            investigated_findings.append(finding)
        else:
            additional_findings.append(finding)

    return {
        "investigated_findings": investigated_findings,
        "additional_findings": additional_findings,
    }


def build_structural_context(
    canonical_state: CanonicalBatchState,
) -> dict[str, Any]:
    substrate = canonical_state.structural_substrate or {}

    return {
        "structural_regions": [
            _strip_internal_ids(
                r.get("summary", r)
                if isinstance(r, dict)
                else r
            )
            for r in substrate.get("compressed_regions", [])
        ],
        "weak_signals": [
            _strip_internal_ids(
                w.get("descriptor", w)
                if isinstance(w, dict)
                else w
            )
            for w in substrate.get("preserved_weak_signals", [])
        ],
        "contradictions": [
            _strip_internal_ids(
                c.get("summary", c)
                if isinstance(c, dict)
                else c
            )
            for c in substrate.get("contradictions", [])
        ],
        "unresolved_tensions": [
            _strip_internal_ids(
                t.get("summary", t)
                if isinstance(t, dict)
                else t
            )
            for t in substrate.get("unresolved_tensions", [])
        ],
    }

# ─── Master Resolver ─────────────────────────────────────────────────────

def resolve_report_context(
    final_state: CanonicalBatchState,
    partition_name: str,
) -> dict[str, Any]:
    """Master resolver that builds all context needed for the report prompt.

    Args:
        final_state: CanonicalBatchState (the Final Updated State).
        partition_name: Human-readable partition name.

    Returns:
        Dict with partition_audit_context, intended_behavioral_scenario,
        researcher_audit_context, investigated_findings, additional_findings.
    """
    partition_audit_context = build_partition_audit_context(partition_name)
    intended_behavioral_scenario = build_intended_behavioral_scenario(partition_name)
    researcher_audit_context = build_researcher_audit_context(final_state)
    finding_inventory = build_finding_inventory(final_state)

    investigated = finding_inventory["investigated_findings"]
    additional = finding_inventory["additional_findings"]
    structural_context = build_structural_context(final_state)

    return {
        "partition_audit_context": partition_audit_context,
        "intended_behavioral_scenario": intended_behavioral_scenario,
        "researcher_audit_context": researcher_audit_context,
        "structural_context": structural_context,
        "investigated_findings": investigated,
        "additional_findings": additional,
    }


# ── Phase 3b — Dataset Merger input resolution ─────────────────────────────

DEFAULT_BATCH_REPORTS_DIR = Path("docs/batch_reports")
DEFAULT_COVERAGE_FILE = (
    Path(__file__).resolve().parent.parent
    / "coverage_builder"
    / "coverage_output"
    / "coverage.json"
)


def resolve_batch_reports(
    batch_reports_dir: str = "docs/batch_reports",
) -> list[str]:
    """Scan the batch reports directory and return absolute paths to .md files.

    Args:
        batch_reports_dir: Directory containing .md batch report files.

    Returns:
        List of absolute file paths, sorted alphabetically.
        Returns empty list if directory doesn't exist.
    """
    reports_path = Path(batch_reports_dir)
    if not reports_path.is_dir():
        logger.warning("Batch reports directory does not exist: %s", batch_reports_dir)
        return []

    md_files = sorted(
        str(p.resolve())
        for p in reports_path.iterdir()
        if p.is_file() and p.suffix.lower() == ".md"
    )
    return md_files


def load_batch_report(file_path: str) -> str:
    """Load the content of a single batch report file.

    Args:
        file_path: Path to the .md batch report file.

    Returns:
        String content of the file.

    Raises:
        FileNotFoundError if file doesn't exist.
        IOError if file can't be read.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Batch report file not found: {file_path}")
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        raise IOError(f"Failed to read batch report file {file_path}: {exc}") from exc


def load_coverage_data(coverage_file: str) -> dict:
    """Load coverage data from the coverage_builder output.

    Args:
        coverage_file: Path to coverage JSON file.

    Returns:
        Dictionary with coverage data (may be empty if no coverage data exists).
    """
    cov_path = Path(coverage_file)
    if not cov_path.is_file():
        logger.warning("Coverage data file not found: %s", coverage_file)
        return {}
    try:
        raw = cov_path.read_text(encoding="utf-8")
        return dict(json.loads(raw))
    except Exception as exc:
        logger.warning("Failed to load coverage data from %s: %s", coverage_file, exc)
        return {}