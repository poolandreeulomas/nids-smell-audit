"""Metric extraction script for the evaluation pipeline (v3 — REFACTORED).

Changes from v2:
- Renamed: Finding Consistency → Evidence Production Stability
- Renamed: Recommendation Consistency → Evidence Volume Stability
- Added: Architectural Properties classification for state metrics
- Updated: All output field names
- Updated: All documentation

Usage:
    python scripts/extract_metrics.py

Outputs:
    ../outputs/run_metrics_corrected.json
    ../outputs/run_metrics_corrected.csv
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# --- Configuration -----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE3_LOGS = REPO_ROOT / "nids-smell-audit" / "Phase3" / "logs"
RUNTIME_RUNS = PHASE3_LOGS / "phase3a_runtime_runs"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
BATCH_REPORTS_DIR = REPO_ROOT / "docs" / "batch_reports"
FINAL_DATASET_REPORT = REPO_ROOT / "final_dataset" / "final_dataset_report.json"

APPROVED_RUNS: Dict[str, Dict[str, str]] = {
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
    "080": {"dataset": "unsw_nb15", "partition": "Training"},
    "081": {"dataset": "unsw_nb15", "partition": "Testing"},
    "082": {"dataset": "cicids2017", "partition": "Friday-PortScan"},
}

PARTITIONS_WITH_MULTIPLE_RUNS: Dict[str, List[str]] = {
    "Friday-Morning": ["050", "064", "067", "074"],
    "Friday-DDoS": ["053", "070"],
    "Friday-PortScan": ["073", "082"],
}


# --- Helpers -----------------------------------------------------------------


def _load_json(path: Path) -> Optional[Any]:
    """Safely load a JSON file. Returns None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _find_run_directory(run_id: str) -> Optional[Path]:
    """Locate the run directory for a given run ID."""
    pattern = f"phase3a_runtime_run_{run_id}_*"
    matches = sorted(RUNTIME_RUNS.glob(pattern))
    return matches[0] if matches else None


def _collect_all_worker_data(run_dir: Path) -> Tuple[List[Dict], List[Dict], int, int]:
    """Collect worker tool_events and parsed_steps from batch_ledger."""
    ledger = _load_json(run_dir / "batch_ledger.json")
    if ledger is None:
        return [], [], 0, 0

    round_count = len(ledger.get("round_manifests", []))
    all_te: List[Dict] = []
    all_ps: List[Dict] = []
    total_steps = 0

    for rm in ledger.get("round_manifests", []):
        for hr in rm.get("hypothesis_runs", []):
            for wp in hr.get("worker_run_paths", []):
                worker_dir = Path(wp).parent
                te = _load_json(worker_dir / "tool_events.json") or []
                ps = _load_json(worker_dir / "parsed_steps.json") or []
                wrm = _load_json(worker_dir / "runtime_metrics.json") or {}
                all_te.extend(te)
                all_ps.extend(ps)
                total_steps += wrm.get("steps_used", 0)

    return all_te, all_ps, total_steps, round_count


# --- Behavioural Metric 1: Tool Diversity Index -----------------------------


def compute_tool_diversity(tool_events: List[Dict]) -> float:
    """Shannon entropy of tool_name distribution from tool_events.json.

    Formula: H = -Σ p_i log(p_i)
    Measures: How evenly distributed tool usage is across available tools.
    Interpretation: Higher values indicate more diverse tool utilization.
    """
    tools = [e.get("tool_name", "") for e in tool_events if e.get("tool_name")]
    if not tools:
        return 0.0

    total = len(tools)
    counter = Counter(tools)
    entropy = -sum(
        (c / total) * math.log(c / total) for c in counter.values()
    )
    return entropy


# --- Behavioural Metric 2: Feature Revisit Rate -----------------------------


def compute_feature_revisit_rate(tool_events: List[Dict]) -> float:
    """Proportion of features that are revisited.

    Uses tool_events[].action.feature_name (verified schema).
    Measures: How frequently workers revisit previously examined features.
    Note: Measures the OBSERVATION of revisiting, not the INTENT.
    """
    seen: Set[str] = set()
    revisited: Set[str] = set()

    for event in tool_events:
        action = event.get("action", {})
        feature = action.get("feature_name", "")
        if not feature:
            continue
        if feature in seen:
            revisited.add(feature)
        seen.add(feature)

    if not seen:
        return 0.0
    return len(revisited) / len(seen)


# --- Behavioural Metric 3: Hypothesis Stability -----------------------------


def compute_hypothesis_stability(ledger: Dict) -> Optional[float]:
    """Average Jaccard similarity of selected hypothesis IDs across rounds.

    Uses batch_ledger.round_manifests[].selected_hypothesis_ids (verified source).
    Measures: How much the active hypothesis set changes between rounds.
    Interpretation: 1.0 = no change, 0.0 = complete turnover.
    """
    active_sets: List[Set[str]] = []
    for rm in ledger.get("round_manifests", []):
        ids = set(rm.get("selected_hypothesis_ids", []))
        if ids:
            active_sets.append(ids)

    if len(active_sets) < 2:
        return None

    similarities: List[float] = []
    for i in range(len(active_sets) - 1):
        h1, h2 = active_sets[i], active_sets[i + 1]
        if not h1 and not h2:
            similarities.append(1.0)
        elif not h1 or not h2:
            similarities.append(0.0)
        else:
            intersection = h1 & h2
            union = h1 | h2
            similarities.append(len(intersection) / len(union))

    return sum(similarities) / len(similarities) if similarities else None


# --- Behavioural Metric 4: Hypothesis Revision Rate -------------------------


def _extract_revision_count_from_snapshot(snapshot: Dict) -> int:
    """Sum revision_count across all hypotheses in a round snapshot."""
    total = 0
    current_ref = snapshot.get("current_state_ref", {})
    for note in current_ref.get("state_notes", []):
        if isinstance(note, str) and "revision_count=" in note:
            match = re.search(r"revision_count=(\d+)", note)
            if match:
                total += int(match.group(1))
    return total


def compute_hypothesis_revision_rate(
    run_dir: Path, round_count: int, total_worker_steps: int
) -> Optional[float]:
    """Formula: revisions / steps
    
    Measures: Frequency of hypothesis revisions relative to worker step count.
    """
    if total_worker_steps == 0:
        return None
    total_revisions = 0
    manifests_dir = run_dir / "round_manifests"
    for i in range(1, round_count + 1):
        snap = _load_json(manifests_dir / f"round-{i:03d}_snapshot.json")
        if snap is not None:
            total_revisions += _extract_revision_count_from_snapshot(snap)
    return total_revisions / total_worker_steps


# --- Architectural Property 5: State Version Churn --------------------------
# Classified as architectural property — determined by state machine design,
# not by investigation outcomes.


def compute_state_version_churn(
    runtime_metrics: Dict, round_count: int
) -> Optional[float]:
    """final_state_version / round_count
    
    NOTE: This is an ARCHITECTURAL PROPERTY, not a behavioural metric.
    For all 3-round runs, final_state_version = 10 and churn = 3.33.
    This is determined by the state machine design (3 hypotheses × 3 rounds + 1 initial).
    """
    if round_count == 0:
        return None
    return runtime_metrics.get("final_state_version", 0) / round_count


# --- Behavioural Metrics 6, 7, 10: Evidence-related -------------------------


def compute_evidence_metrics(tool_events: List[Dict]) -> Dict[str, Any]:
    """Compute evidence-related metrics from tool_events.json (correct schema)."""
    features: Set[str] = set()
    total_evidence = 0
    evidence_with_provenance = 0

    for event in tool_events:
        raw_output = event.get("raw_tool_output", {})
        evidence = raw_output.get("evidence", {})
        if not evidence:
            continue
        total_evidence += 1

        provenance = evidence.get("provenance", {})
        if provenance and (provenance.get("source") or provenance.get("tool")):
            evidence_with_provenance += 1

        feature = evidence.get("feature", "")
        if feature:
            features.add(feature)

        # Also track feature from action field
        action = event.get("action", {})
        af = action.get("feature_name", "")
        if af:
            features.add(af)

    n_features = len(features)
    return {
        "total_evidence_blocks": total_evidence,
        "investigated_features": n_features,
        "evidence_per_feature": total_evidence / n_features if n_features > 0 else 0.0,
        "provenance_completeness": (
            evidence_with_provenance / total_evidence if total_evidence > 0 else 1.0
        ),
    }


# --- Behavioural Metric 8: History Completeness -----------------------------


def compute_history_completeness(
    parsed_steps: List[Dict], runtime_metrics: Dict
) -> Optional[float]:
    """Proportion of executed steps that are recorded in parsed_steps.
    
    Measures: Whether the framework's step recording is complete.
    """
    recorded = len(parsed_steps)
    executed = runtime_metrics.get("steps_used", 0)
    if executed == 0:
        return None
    return min(recorded, executed) / executed


# --- (REMOVED) Metric 8 (old): Artifact Family Count -------------------------
# This metric has been removed because:
# 1. The regex pattern didn't match actual batch report format
# 2. It silently returned 0 or 1 for all runs
# 3. It was not discriminative
# Artifact family analysis is now performed through the findings corpus pipeline.


# --- Architectural Property 9: State Version History ------------------------
# Classified as architectural property — determined by state machine design.


def compute_state_version_history(runtime_metrics: Dict) -> int:
    """Return final_state_version.
    
    NOTE: This is an ARCHITECTURAL PROPERTY.
    Always 10 for all 3-round runs.
    """
    return runtime_metrics.get("final_state_version", 0)


# --- Stability Metrics (RENAMED from "Consistency") -------------------------


def compute_cross_run_stability(
    all_metrics: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute Evidence Production Stability and Evidence Volume Stability.
    
    Formerly named "Finding Consistency" and "Recommendation Consistency".
    
    IMPORTANT: These do NOT measure finding content or recommendation agreement.
    They measure stability of evidence production metrics across runs.
    True finding/recommendation comparison requires the findings corpus.
    """
    results: Dict[str, Any] = {}

    for partition, run_ids in PARTITIONS_WITH_MULTIPLE_RUNS.items():
        available = [rid for rid in run_ids if rid in all_metrics]
        if len(available) < 2:
            results[partition] = {
                "evidence_production_stability": None,
                "evidence_volume_stability": None,
                "runs_compared": len(available),
                "note": "Insufficient runs for stability computation",
            }
            continue

        # Evidence Production Stability: 1 - CV(evidence_per_feature)
        epf_vals = [
            all_metrics[rid].get("evidence_per_feature", 0) for rid in available
        ]
        if epf_vals and max(epf_vals) > 0:
            mean_epf = sum(epf_vals) / len(epf_vals)
            std_epf = (sum((x - mean_epf) ** 2 for x in epf_vals) / len(epf_vals)) ** 0.5
            production_stability = max(0.0, 1.0 - (std_epf / mean_epf))
        else:
            production_stability = None

        # Evidence Volume Stability: 1 - CV(total_evidence_blocks)
        eb_vals = [
            all_metrics[rid].get("total_evidence_blocks", 0) for rid in available
        ]
        if eb_vals and max(eb_vals) > 0:
            mean_eb = sum(eb_vals) / len(eb_vals)
            std_eb = (sum((x - mean_eb) ** 2 for x in eb_vals) / len(eb_vals)) ** 0.5
            volume_stability = max(0.0, 1.0 - (std_eb / mean_eb))
        else:
            volume_stability = None

        results[partition] = {
            "evidence_production_stability": round(production_stability, 4) if production_stability is not None else None,
            "evidence_volume_stability": round(volume_stability, 4) if volume_stability is not None else None,
            "runs_compared": len(available),
        }

    return results


# --- Main Extraction ---------------------------------------------------------


def extract_run(run_id: str, info: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Extract all metrics for a single run."""
    run_dir = _find_run_directory(run_id)
    if run_dir is None:
        return None

    runtime_metrics = _load_json(run_dir / "runtime_metrics.json")
    ledger = _load_json(run_dir / "batch_ledger.json")
    if runtime_metrics is None or ledger is None:
        return None

    # Collect raw worker data
    all_te, all_ps, total_steps, round_count = _collect_all_worker_data(run_dir)

    # Per-worker history completeness
    hc_values: List[float] = []
    for rm in ledger.get("round_manifests", []):
        for hr in rm.get("hypothesis_runs", []):
            for wp in hr.get("worker_run_paths", []):
                wdir = Path(wp).parent
                wps = _load_json(wdir / "parsed_steps.json") or []
                wrm = _load_json(wdir / "runtime_metrics.json") or {}
                hc = compute_history_completeness(wps, wrm)
                if hc is not None:
                    hc_values.append(hc)

    # Compute all metrics
    results: Dict[str, Any] = {
        "run_id": f"run_{run_id}",
        "dataset": info["dataset"],
        "partition": info["partition"],
    }

    # --- BEHAVIOURAL METRICS ---

    # 1. Tool Diversity Index
    results["tool_diversity_index"] = round(compute_tool_diversity(all_te), 4)

    # 2. Feature Revisit Rate
    results["feature_revisit_rate"] = round(compute_feature_revisit_rate(all_te), 4)

    # 3. Hypothesis Stability
    hs = compute_hypothesis_stability(ledger)
    results["hypothesis_stability"] = round(hs, 4) if hs is not None else None

    # 4. Hypothesis Revision Rate
    hrr = compute_hypothesis_revision_rate(run_dir, round_count, total_steps)
    results["hypothesis_revision_rate"] = round(hrr, 4) if hrr is not None else None

    # 6-7, 10. Evidence metrics
    ev = compute_evidence_metrics(all_te)
    results["total_evidence_blocks"] = ev["total_evidence_blocks"]
    results["investigated_features"] = ev["investigated_features"]
    results["evidence_per_feature"] = round(ev["evidence_per_feature"], 4)
    results["provenance_completeness"] = round(ev["provenance_completeness"], 4)

    # 8. History Completeness
    results["history_completeness"] = (
        round(sum(hc_values) / len(hc_values), 4) if hc_values else None
    )

    # --- ARCHITECTURAL PROPERTIES ---

    # 5. State Version Churn (architectural)
    results["state_version_churn"] = round(compute_state_version_churn(runtime_metrics, round_count), 4) if round_count > 0 else None

    # 9. State Version History (architectural)
    results["state_version_history"] = compute_state_version_history(runtime_metrics)

    # Reference fields
    results["round_count"] = round_count
    results["worker_count"] = len(all_te)
    results["total_tool_events"] = len(all_te)
    results["total_worker_steps"] = total_steps

    return results


def main() -> None:
    """Run extraction for all approved runs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_metrics: Dict[str, Dict[str, Any]] = {}
    successful = 0
    failed = 0

    print("=" * 60)
    print("Metric Extraction Pipeline v3 (REFACTORED)")
    print("=" * 60)

    for run_id in sorted(APPROVED_RUNS.keys(), key=int):
        info = APPROVED_RUNS[run_id]
        print(f"\nProcessing run_{run_id} ({info['dataset']}/{info['partition']})...")

        results = extract_run(run_id, info)
        if results is None:
            print("  FAILED")
            failed += 1
            continue

        all_metrics[run_id] = results
        successful += 1

        print(f"  Tool Diversity:        {results.get('tool_diversity_index', 'N/A')}")
        print(f"  Feature Revisit:       {results.get('feature_revisit_rate', 'N/A')}")
        print(f"  Hypothesis Stability:  {results.get('hypothesis_stability', 'N/A')}")
        print(f"  Hypothesis Revision:   {results.get('hypothesis_revision_rate', 'N/A')}")
        print(f"  State Churn:           {results.get('state_version_churn', 'N/A')} [ARCHITECTURAL]")
        print(f"  Total Evidence:        {results.get('total_evidence_blocks', 'N/A')}")
        print(f"  Evidence/Feature:      {results.get('evidence_per_feature', 'N/A')}")
        print(f"  History Complete:      {results.get('history_completeness', 'N/A')}")
        print(f"  Provenance Complete:   {results.get('provenance_completeness', 'N/A')}")
        print(f"  State Version:         {results.get('state_version_history', 'N/A')} [ARCHITECTURAL]")
        print(f"  Tool Events:           {results.get('total_tool_events', 'N/A')}")
        print(f"  Workers Steps:         {results.get('total_worker_steps', 'N/A')}")

    # Cross-run stability (RENAMED from "consistency")
    print(f"\n{'='*60}")
    print("Cross-Run Stability (RENAMED from 'Consistency')")
    print("=" * 60)
    stability = compute_cross_run_stability(all_metrics)
    for part, data in stability.items():
        print(f"  {part}: production_stability={data.get('evidence_production_stability', 'N/A')}, "
              f"volume_stability={data.get('evidence_volume_stability', 'N/A')}, "
              f"runs={data.get('runs_compared', 0)}")

    # Attach stability to per-run metrics
    for rid, m in all_metrics.items():
        part = m.get("partition", "")
        c = stability.get(part, {})
        m["evidence_production_stability"] = c.get("evidence_production_stability")
        m["evidence_volume_stability"] = c.get("evidence_volume_stability")

    # --- JSON output ---
    json_path = OUTPUT_DIR / "run_metrics_corrected.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2, ensure_ascii=False)
    print(f"\nJSON: {json_path}")

    # --- CSV output ---
    csv_path = OUTPUT_DIR / "run_metrics_corrected.csv"
    fieldnames = [
        "run_id", "dataset", "partition",
        "tool_diversity_index", "feature_revisit_rate",
        "hypothesis_stability", "hypothesis_revision_rate",
        "state_version_churn",
        "total_evidence_blocks", "investigated_features", "evidence_per_feature",
        "history_completeness", "provenance_completeness",
        "state_version_history",
        "evidence_production_stability", "evidence_volume_stability",
        "round_count", "worker_count", "total_tool_events", "total_worker_steps",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for rid in sorted(all_metrics.keys(), key=int):
            w.writerow(all_metrics[rid])
    print(f"CSV:  {csv_path}")

    print(f"\n{'='*60}")
    print(f"Done. {successful} successful, {failed} failed.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()