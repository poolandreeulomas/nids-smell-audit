"""Contracts and constants for the Phase 3 Final Partition Audit Report Generator.

Phase 3a: Per-partition final batch report generation constants.
Phase 3b: Pydantic models for the Final Dataset Report (Dataset Merger output).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Phase 3a constants ─────────────────────────────────────────────────────

SCHEMA_VERSION = "phase3.final_batch_report.v1"
PROMPT_VERSION = "phase3.final_batch_report.prompt.v1"

PARTITION_SCENARIOS: dict[str, str] = {
    "ddos": (
        "This partition models a DDoS (Distributed Denial of Service) scenario "
        "in which attack traffic is expected to target a limited service surface. "
        "Expected characteristics include: "
        "strong concentration patterns, "
        "repetitive flow structures, "
        "skewed feature distributions, "
        "and high traffic volume concentration. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "portscan": (
        "This partition models a PortScan scenario in which reconnaissance traffic "
        "systematically probes multiple ports and hosts. "
        "Expected characteristics include: "
        "widespread connection attempts across many destinations, "
        "high protocol diversity, "
        "and distinctive temporal scanning patterns. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "web": (
        "This partition models Web Attack scenarios including XSS and SQL injection. "
        "Expected characteristics include: "
        "HTTP-level pattern concentration, "
        "specific payload structure repetition, "
        "and application-layer behavioral signatures. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "infiltration": (
        "This partition models an Infiltration scenario where an attacker "
        "gradually compromises internal network resources. "
        "Expected characteristics include: "
        "low-and-slow traffic patterns, "
        "internal lateral movement signatures, "
        "and blended benign-malicious sequences. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "bruteforce": (
        "This partition models Brute Force authentication attacks (FTP/SSH). "
        "Expected characteristics include: "
        "repeated authentication failure patterns, "
        "high connection attempt rates, "
        "and distinctive credential-guessing signatures. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "benign": (
        "This partition models Benign (normal) network traffic. "
        "Expected characteristics include: "
        "diverse traffic patterns, "
        "no dominant attack signatures, "
        "natural protocol and destination variety, "
        "and typical business-hour usage profiles. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
}

# ── Phase 3b Dataset Merger constants ──────────────────────────────────────

MERGER_SCHEMA_VERSION = "phase3.dataset_merger.v1"
MERGER_PROMPT_VERSION = "phase3.dataset_merger.prompt.v1"


# ── Phase 3b Pydantic models for Final Dataset Report ──────────────────────


class BatchSummary(BaseModel):
    """Summary of one batch report from Phase 3a."""

    batch_id: str
    batch_label: str
    source_file: str
    total_findings: int
    key_themes: list[str]
    summary: str


class ArtifactPattern(BaseModel):
    """A pattern of artifact observed across batches."""

    pattern_name: str
    description: str
    observed_in_batches: list[str]
    severity: Optional[str] = None


class RecurringFinding(BaseModel):
    """A finding that appears in multiple batches."""

    finding_id: str
    description: str
    batch_ids: list[str]
    finding_type: str
    consistency_note: Optional[str] = None


class PartitionSummary(BaseModel):
    """Summary for a single partition."""

    partition_id: str
    partition_label: str
    artifact_category_counts: dict[str, int]
    notable_findings: list[str]
    summary: str


class Contradiction(BaseModel):
    """A contradiction between findings in different batches."""

    contradiction_id: str
    batch_a: str
    finding_a: str
    batch_b: str
    finding_b: str
    description: str
    resolution_status: str = "unresolved"


class CoverageSummary(BaseModel):
    """Coverage data summary."""

    total_packets: int = 0
    analyzed_packets: int = 0
    coverage_percentage: float = 0.0
    uncovered_categories: list[str] = []
    coverage_notes: Optional[str] = None


class ReportMetadata(BaseModel):
    """Metadata for the final dataset report."""

    report_version: str
    generated_at: datetime
    batch_sources: list[str]
    merger_version: str


class FinalDatasetReport(BaseModel):
    """Complete final dataset report produced by the Dataset Merger."""

    title: str
    dataset_overview: str
    batch_summaries: list[BatchSummary]
    recurring_artifact_families: list[ArtifactPattern]
    recurring_findings: list[RecurringFinding]
    coverage_interpretation: str
    partition_summaries: list[PartitionSummary]
    cross_partition_synthesis: str
    contradictions: list[Contradiction]
    final_recommendation: str
    metadata: ReportMetadata