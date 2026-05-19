"""Reproducibility helpers for MVP runs.

Utilities in this module collect deterministic run metadata that can be
serialized with state and logs for run-to-run comparison.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import subprocess
from typing import Any


def hash_text_sha256(text: str) -> str:
    """Return SHA-256 hex digest for text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_feature_list(features: list[str]) -> str:
    """Return SHA-256 hash for sorted feature list content."""
    normalized = "\n".join(sorted(features))
    return hash_text_sha256(normalized)


def compute_file_sha256(file_path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 hash for a file using chunked reads."""
    hasher = hashlib.sha256()
    with Path(file_path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def get_dataset_snapshot_metadata(
    dataset_path: str | Path,
    include_file_hash: bool = False,
) -> dict[str, Any]:
    """Build dataset snapshot metadata for reproducibility logs."""
    path = Path(dataset_path)
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": None,
            "modified_utc": None,
            "sha256": None,
        }

    stats = path.stat()
    snapshot = {
        "path": str(path),
        "exists": True,
        "size_bytes": int(stats.st_size),
        "modified_utc": datetime.fromtimestamp(stats.st_mtime, tz=UTC).isoformat(),
        "sha256": None,
    }

    if include_file_hash:
        snapshot["sha256"] = compute_file_sha256(path)

    return snapshot


def get_code_version(repo_path: str | Path | None = None) -> str | None:
    """Return git commit hash when available; otherwise None."""
    cwd = str(repo_path) if repo_path else None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return None

    commit = result.stdout.strip()
    return commit or None


def build_reproducibility_metadata(
    *,
    model_name: str,
    model_version: str | None,
    prompt_text: str,
    temperature: float,
    seed: int | None,
    dataset_path: str | Path,
    dataset_config: dict[str, Any] | None,
    available_features: list[str],
    max_steps: int,
    top_p: float | None = None,
    repo_path: str | Path | None = None,
    include_dataset_hash: bool = False,
) -> dict[str, Any]:
    """Build reproducibility metadata block for one run."""
    return {
        "model_name": model_name,
        "model_version": model_version,
        "prompt_hash": hash_text_sha256(prompt_text),
        "temperature": float(temperature),
        "top_p": None if top_p is None else float(top_p),
        "seed": seed,
        "dataset_snapshot": get_dataset_snapshot_metadata(
            dataset_path,
            include_file_hash=include_dataset_hash,
        ),
        "dataset_config": dataset_config,
        "available_features_hash": hash_feature_list(available_features),
        "available_features_count": len(available_features),
        "max_steps": int(max_steps),
        "code_version": get_code_version(repo_path),
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
