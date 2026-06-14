"""Contracts and constants for the Phase 3B Partition Memory Extractor."""

from __future__ import annotations

SCHEMA_VERSION = "phase3.partition_memory.v1"
PROMPT_VERSION = "phase3.partition_memory.prompt.v1"

ARTIFACT_FAMILIES: list[str] = [
    "Shortcut / Highly Dependent Features",
    "Artificial Dependency Structures",
    "Distribution Collapse / Low Diversity",
    "Duplicate / Near-Duplicate Structures",
    "Label Inconsistency / Suspicious Label Structures",
    "Representation Artifacts",
]