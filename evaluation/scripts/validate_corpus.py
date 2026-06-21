"""Corpus validation script for the evaluation pipeline.

Validates that all 14 approved runs have the required artifacts
before metric extraction begins.

Usage:
    python scripts/validate_corpus.py

Output:
    ../outputs/corpus_validation.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# --- Configuration -----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE3_LOGS = REPO_ROOT / "nids-smell-audit" / "Phase3" / "logs"
RUNTIME_RUNS = PHASE3_LOGS / "phase3a_runtime_runs"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

APPROVED_RUNS: Dict[str, Dict[str, str]] = {
    # CICIDS2017
    "050": {"dataset": "cicids2017", "partition": "Friday-Morning"},
    "053": {"dataset": "cicids2017", "partition": "Friday-DDoS"},
    "064": {"dataset": "cicids2017", "partition": "Friday-Morning"},
    "067": {"dataset": "cicids2017", "partition": "Friday-Morning"},
    "070": {"dataset": "cicids2017", "partition": "Friday-DDoS"},
    "071": {"dataset": "cicids2017", "partition": "Tuesday"},
    "072": {"dataset": "cicids2017", "partition": "Wednesday"},
    "073": {"dataset": "cicids2017", "partition": "Friday-PortScan"},
    "074": {"dataset": "cicids2017", "partition": "Friday-Morning"},
    "075": {"dataset": "cicids2017", "partition": "Monday"},
    "076": {"dataset": "cicids2017", "partition": "Thursday-Infiltration"},
    "077": {"dataset": "cicids2017", "partition": "Thursday-WebAttacks"},
    # UNSW-NB15
    "080": {"dataset": "unsw_nb15", "partition": "Training"},
    "081": {"dataset": "unsw_nb15", "partition": "Testing"},
}

REQUIRED_BATCH_FILES: List[str] = [
    "runtime_metrics.json",
    "batch_ledger.json",
    "event_stream.jsonl",
]

REQUIRED_WORKER_FILES: List[str] = [
    "parsed_steps.json",
    "tool_events.json",
    "runtime_metrics.json",
    "worker_result.json",
]


# --- Helpers -----------------------------------------------------------------


def _find_run_directory(run_id: str) -> Path | None:
    """Locate the run directory for a given run ID."""
    pattern = f"phase3a_runtime_run_{run_id}_*"
    matches = sorted(RUNTIME_RUNS.glob(pattern))
    return matches[0] if matches else None


def _get_dataset_from_path(dataset_path: str) -> str:
    """Extract dataset name from a full dataset path."""
    if "cic_ids_2017" in dataset_path or "CICIDS2017" in dataset_path:
        return "cicids2017"
    if "UNSW_NB15" in dataset_path or "unsw_nb15" in dataset_path:
        return "unsw_nb15"
    return "unknown"


def _get_partition_from_path(dataset_path: str) -> str:
    """Extract a short partition name from the dataset path."""
    p = Path(dataset_path)
    stem = p.stem
    # Clean up common suffixes
    for suffix in [".pcap_ISCX", ".pcap", ".csv"]:
        stem = stem.replace(suffix, "")
    # Map to short names
    mapping = {
        "Monday-WorkingHours": "Monday",
        "Tuesday-WorkingHours": "Tuesday",
        "Wednesday-WorkingHours": "Wednesday",
        "Thursday-WorkingHours-Morning-WebAttacks": "Thursday-WebAttacks",
        "Thursday-WorkingHours-Afternoon-Infilteration": "Thursday-Infiltration",
        "Friday-WorkingHours-Morning": "Friday-Morning",
        "Friday-WorkingHours-Afternoon-DDos": "Friday-DDoS",
        "Friday-WorkingHours-Afternoon-PortScan": "Friday-PortScan",
        "UNSW_NB15_training-set": "Training",
        "UNSW_NB15_testing-set": "Testing",
    }
    return mapping.get(stem, stem)


def _check_worker_artifacts(worker_dir: Path) -> List[str]:
    """Check that all required worker artifacts exist. Returns missing files."""
    missing: List[str] = []
    for fname in REQUIRED_WORKER_FILES:
        if not (worker_dir / fname).is_file():
            missing.append(f"worker_artifacts/{worker_dir.name}/{fname}")
    return missing


def _check_round_manifests(run_dir: Path, round_count: int) -> List[str]:
    """Check round manifest snapshots exist. Returns missing files."""
    missing: List[str] = []
    manifests_dir = run_dir / "round_manifests"
    if not manifests_dir.is_dir():
        return ["round_manifests/ (directory missing)"]
    for i in range(1, round_count + 1):
        snap = manifests_dir / f"round-{i:03d}_snapshot.json"
        if not snap.is_file():
            missing.append(f"round_manifests/round-{i:03d}_snapshot.json")
    return missing


def validate_run(run_id: str, info: Dict[str, str]) -> Dict[str, Any]:
    """Validate a single run. Returns a validation record."""
    record: Dict[str, Any] = {
        "run_id": f"run_{run_id}",
        "dataset": info["dataset"],
        "partition": info["partition"],
        "valid": False,
        "missing_files": [],
        "worker_count": 0,
        "workers_completed": 0,
        "workers_partial": 0,
        "notes": [],
    }

    run_dir = _find_run_directory(run_id)
    if run_dir is None:
        record["missing_files"].append(f"run directory for run_{run_id}")
        record["notes"].append("Run directory not found")
        return record

    # Check batch-level artifacts
    for fname in REQUIRED_BATCH_FILES:
        if not (run_dir / fname).is_file():
            record["missing_files"].append(fname)

    # Read batch_ledger to get worker paths and round count
    batch_ledger_path = run_dir / "batch_ledger.json"
    if batch_ledger_path.is_file():
        try:
            with open(batch_ledger_path, "r", encoding="utf-8") as f:
                ledger = json.load(f)

            round_count = len(ledger.get("round_manifests", []))
            record["round_count"] = round_count

            # Check round snapshots
            missing_snapshots = _check_round_manifests(run_dir, round_count)
            record["missing_files"].extend(missing_snapshots)

            # Check worker artifacts
            worker_paths: List[str] = []
            for rm in ledger.get("round_manifests", []):
                for hr in rm.get("hypothesis_runs", []):
                    for wp in hr.get("worker_run_paths", []):
                        worker_paths.append(wp)

            record["worker_count"] = len(worker_paths)

            for wp in worker_paths:
                worker_dir = Path(wp).parent
                if worker_dir.is_dir():
                    record["missing_files"].extend(
                        _check_worker_artifacts(worker_dir)
                    )
                    # Check worker status
                    wrm = worker_dir / "runtime_metrics.json"
                    if wrm.is_file():
                        with open(wrm, "r", encoding="utf-8") as f:
                            w_data = json.load(f)
                        status = w_data.get("worker_status", "unknown")
                        if status == "completed":
                            record["workers_completed"] += 1
                        elif status == "partial":
                            record["workers_partial"] += 1

            # Verify dataset/partition match
            dataset_path = ledger.get("dataset_path", "")
            actual_dataset = _get_dataset_from_path(dataset_path)
            actual_partition = _get_partition_from_path(dataset_path)
            if actual_dataset != info["dataset"]:
                record["notes"].append(
                    f"Dataset mismatch: expected {info['dataset']}, got {actual_dataset}"
                )
            if actual_partition != info["partition"]:
                record["notes"].append(
                    f"Partition mismatch: expected {info['partition']}, got {actual_partition}"
                )

        except (json.JSONDecodeError, KeyError) as e:
            record["missing_files"].append(f"batch_ledger.json (parse error: {e})")
    else:
        record["missing_files"].append("batch_ledger.json")

    # Check runtime_metrics.json for status
    rm_path = run_dir / "runtime_metrics.json"
    if rm_path.is_file():
        try:
            with open(rm_path, "r", encoding="utf-8") as f:
                rm_data = json.load(f)
            record["batch_status"] = rm_data.get("status", "unknown")
            record["round_count"] = rm_data.get("round_count", 0)
            record["final_state_version"] = rm_data.get("final_state_version", 0)
        except (json.JSONDecodeError, KeyError):
            record["missing_files"].append("runtime_metrics.json (parse error)")
    else:
        record["missing_files"].append("runtime_metrics.json")

    # Determine validity
    record["valid"] = len(record["missing_files"]) == 0
    return record


def main() -> None:
    """Validate all approved runs and produce corpus_validation.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    valid_count = 0
    invalid_count = 0

    for run_id in sorted(APPROVED_RUNS.keys(), key=int):
        info = APPROVED_RUNS[run_id]
        record = validate_run(run_id, info)
        results.append(record)
        if record["valid"]:
            valid_count += 1
        else:
            invalid_count += 1

        status = "VALID" if record["valid"] else "INVALID"
        print(
            f"  run_{run_id} ({info['dataset']}/{info['partition']}): "
            f"{status} — {len(record['missing_files'])} missing files, "
            f"{record['worker_count']} workers "
            f"({record['workers_completed']} completed, {record['workers_partial']} partial)"
        )

    summary = {
        "total_runs": len(APPROVED_RUNS),
        "valid_runs": valid_count,
        "invalid_runs": invalid_count,
        "runs": results,
    }

    output_path = OUTPUT_DIR / "corpus_validation.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Corpus validation complete.")
    print(f"  Total runs: {len(APPROVED_RUNS)}")
    print(f"  Valid:      {valid_count}")
    print(f"  Invalid:    {invalid_count}")
    print(f"  Output:     {output_path}")


if __name__ == "__main__":
    main()