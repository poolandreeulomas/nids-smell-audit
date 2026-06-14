"""Load compact Judge context for dataset partitions.

Supports multiple datasets through a registry of context directories.
Dataset-specific context text files are stored in subdirectories named after
the dataset's config name (e.g. cicids2017/, unsw_nb15/).
"""

from __future__ import annotations

from pathlib import Path
import re

from data.dataset_config import DatasetConfig, get_default_dataset_config

_CONTEXT_DIR = Path(__file__).resolve().parent / "context"
_SECTION_SPLIT_RE = re.compile(r"\n\s*\n+")
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ddos", ("ddos", "dos")),
    ("portscan", ("portscan",)),
    ("web", ("webattacks", "webattack", "xss", "sqli")),
    ("infiltration", ("infiltration",)),
    ("bruteforce", ("ftp", "ssh", "bruteforce")),
    ("benign", ("monday", "benign")),
)


def _context_dir_for_dataset(dataset_config: DatasetConfig) -> Path:
    """Resolve the context directory for a given dataset config.

    Falls back to cicids2017 for backward compatibility.
    """
    dataset_id = dataset_config.dataset_name
    candidate = _CONTEXT_DIR / dataset_id
    if candidate.is_dir():
        return candidate
    # Fallback: try cicids2017 (original default)
    fallback = _CONTEXT_DIR / "cicids2017"
    if fallback.is_dir():
        return fallback
    return candidate


def _read_context_file(name: str, dataset_config: DatasetConfig | None = None) -> str:
    cfg = dataset_config or get_default_dataset_config()
    context_dir = _context_dir_for_dataset(cfg)
    path = context_dir / f"{name}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _resolve_phenomenon(text: str) -> str | None:
    """Infer partition phenomenon from text using token matching."""
    tokens = _TOKEN_SPLIT_RE.split(text.lower())
    for phenomenon, keywords in _TOKEN_PRIORITY:
        if any(kw in tokens for kw in keywords):
            return phenomenon
    return None


def get_judge_partition_context(
    partition_name: str,
    dataset_config: DatasetConfig | None = None,
) -> str:
    """Return Judge partition context text for the given partition name.

    Args:
        partition_name: Name of the dataset partition (e.g. a filename).
        dataset_config: DatasetConfig to resolve the correct context directory.
            Falls back to default if not provided.

    Returns:
        Context text string, or an empty string if no context is available.
    """
    cfg = dataset_config or get_default_dataset_config()
    phenomenon = resolve_judge_partition_phenomenon(partition_name)
    if not phenomenon:
        return _read_context_file("generic_network_traffic", cfg)

    scenario = _read_context_file(phenomenon, cfg)
    if scenario:
        return scenario

    global_context = _read_context_file("global", cfg)
    if global_context:
        return global_context

    return _read_context_file("generic_network_traffic", cfg)


def get_judge_global_context(
    dataset_config: DatasetConfig | None = None,
) -> str:
    """Return the global Judge context text.

    Args:
        dataset_config: DatasetConfig to resolve the correct context directory.
            Falls back to default if not provided.

    Returns:
        Global context text string, or empty string if unavailable.
    """
    cfg = dataset_config or get_default_dataset_config()
    return _read_context_file("global", cfg)


def get_judge_context_sections(
    partition_name: str,
    dataset_config: DatasetConfig | None = None,
) -> tuple[str, str, str]:
    """Split the Judge context text into its three logical sections.

    The context file for a phenomenon is expected to contain three sections
    separated by blank lines:
        (1) dataset phenomenon description,
        (2) expected structure / evaluation guidelines,
        (3) evaluation lens.

    The partition name is first resolved to a phenomenon via
    ``resolve_judge_partition_phenomenon``, then the corresponding context
    file is read and split.

    Args:
        partition_name: Name of the dataset partition (e.g. a filename).
        dataset_config: Optional DatasetConfig for multi-dataset support.

    Returns:
        A 3-tuple of (dataset_phenomenon, expected_structure, evaluation_lens).
        Each section defaults to an empty string if not found.
    """
    # Resolve the partition name to a phenomenon identifier
    phenomenon_name = resolve_judge_partition_phenomenon(partition_name)
    if not phenomenon_name:
        return ("", "", "")

    # Read the phenomenon's context file
    text = _read_context_file(phenomenon_name, dataset_config)
    if not text:
        return ("", "", "")

    # Split into sections using the section split regex
    sections = _SECTION_SPLIT_RE.split(text)
    # We expect exactly 3 sections; pad with empty strings if fewer.
    while len(sections) < 3:
        sections.append("")
    # Truncate to 3 if more (unlikely but safe).
    return tuple(sections[:3])


def resolve_judge_partition_phenomenon(partition_name: str) -> str | None:
    """Map a partition name to a phenomenon identifier."""
    return _resolve_phenomenon(partition_name)
