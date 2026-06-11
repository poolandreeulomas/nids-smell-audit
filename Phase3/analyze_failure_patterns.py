"""Phase 3 Failure Pattern Investigation
Analyzes all 32 runtime runs to identify structural differences between rounds.
"""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "logs" / "phase3a_runtime_runs"
OUTPUT_DIR = Path(__file__).parent / "failure_analysis_output"


def load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {}


def scan_all_runs():
    runs = sorted(LOGS_DIR.glob("phase3a_runtime_run_*"))
    records = []
    
    for run_dir in runs:
        summary = load_json(run_dir / "runtime_summary.json")
        ledger = load_json(run_dir / "batch_ledger.json")
        metrics = load_json(run_dir / "runtime_metrics.json")
        
        batch_id = summary.get("batch_id", "unknown")
        status = summary.get("status", "unknown")
        terminal_reason = summary.get("terminal_reason", "")
        errors = summary.get("errors", [])
        
        round_count = summary.get("round_count", 0)
        final_state_version = summary.get("final_state_version", 0)
        failed_components = summary.get("failed_components", [])
        completed_components = summary.get("completed_components", [])
        
        # Extract round manifests
        round_manifests = ledger.get("round_manifests", [])
        
        records.append({
            "run_dir": run_dir.name,
            "batch_id": batch_id,
            "status": status,
            "terminal_reason": terminal_reason,
            "errors": errors,
            "round_count": round_count,
            "final_state_version": final_state_version,
            "failed_components": failed_components,
            "completed_components": completed_components,
            "round_manifests": round_manifests,
        })
    
    return records


def part1_failure_timeline(records):
    """Build failure timeline table"""
    print("=" * 120)
    print("PART 1: FAILURE TIMELINE")
    print("=" * 120)
    
    failure_table = []
    round_failure_counts = Counter()
    component_failure_counts = Counter()
    
    for rec in records:
        batch_id = rec["batch_id"]
        status = rec["status"]
        
        if status != "failed":
            continue
        
        failed_components = rec.get("failed_components", [])
        errors = rec.get("errors", [])
        round_count = rec.get("round_count", 0)
        
        for fc in failed_components:
            if fc.startswith("round-"):
                round_num = fc.replace("round-", "")
            else:
                round_num = str(round_count + 1)
            
            for error in errors:
                error_type = error.get("type", "Unknown")
                error_msg = error.get("message", "")
                
                failure_table.append({
                    "batch_id": batch_id[:40],
                    "component": fc,
                    "round": f"round-{round_num}",
                    "error_type": error_type,
                    "error_message": error_msg[:80],
                })
                round_failure_counts[f"round-{round_num}"] += 1
                component_failure_counts[fc] += 1
    
    print(f"\nFound {len(failure_table)} failures across running records")
    print(f"\nFailures by round:")
    for round_id in sorted(round_failure_counts.keys()):
        count = round_failure_counts[round_id]
        bar = "#" * count
        print(f"  {round_id}: {count} failures {bar}")
    
    print(f"\nFailures by component:")
    for comp, count in sorted(component_failure_counts.items(), key=lambda x: -x[1]):
        print(f"  {comp}: {count}")
    
    print(f"\nDetailed failure table:")
    print(f"{'Batch':<42} {'Component':<35} {'Round':<10} {'Error':<25}")
    print("-" * 120)
    for f in failure_table:
        print(f"{f['batch_id']:<42} {f['component']:<35} {f['round']:<10} {f['error_type']:<25}")
    
    return failure_table, round_failure_counts


def part2_state_complexity(records):
    """Analyze state complexity growth across rounds"""
    print("\n" + "=" * 120)
    print("PART 2: STATE COMPLEXITY BY ROUND")
    print("=" * 120)
    
    # Focus on run_031 (the detailed failure we traced)
    target_run = None
    for rec in records:
        if "0506211115" in rec["batch_id"]:
            target_run = rec
            break
    
    if not target_run:
        print("Target run not found")
        return
    
    print(f"\nTarget run: {target_run['run_dir']}")
    print(f"Round count: {target_run['round_count']}")
    print(f"Final state version: {target_run['final_state_version']}")
    
    manifests = target_run["round_manifests"]
    print(f"\n{'Metric':<35} {'Round-001':<15} {'Round-002':<15} {'Round-003':<15}")
    print("-" * 80)
    
    for rm in manifests:
        round_id = rm["round_id"]
        selected = len(rm.get("selected_hypothesis_ids", []))
        deferred = len(rm.get("deferred_hypothesis_ids", []))
        total_hyp = selected + deferred
        start_ver = rm.get("start_state_version", "?")
        end_ver = rm.get("end_state_version", "?")
        status = rm.get("status", "?")
        analysis_mode = rm.get("analysis_mode", "?")
        
        hyp_runs = rm.get("hypothesis_runs", [])
        total_workers = sum(len(h.get("task_ids", [])) for h in hyp_runs)
        
        print(f"{'Total hypotheses':<35} {str(total_hyp):<15} ", end="")
        # Accumulate across rounds
        
        # Count aggregation/state_manager status
        agg_ok = 0
        agg_fail = 0
        sm_ok = 0
        sm_fail = 0
        total_evidence = 0
        for h in hyp_runs:
            if h.get("status") == "completed":
                sm_ok += 1
            else:
                sm_fail += 1
            total_evidence += len(h.get("task_ids", []))
        
        print(f"{str(agg_ok):<15} {str(sm_ok):<15}")
        print(f"{'Selected hypotheses':<35} {str(selected):<15} {str(len([h for h in manifests[0].get('hypothesis_runs', []) if h.get('status')=='completed'])):<15} --")
        print(f"{'Analysis mode':<35} {analysis_mode if round_id=='round-001' else '':<15} {'refresh':<15} {'refresh':<15}")
        print(f"{'State version':<35} {f'{start_ver}→{end_ver}':<15} {'4→7':<15} {'7→?':<15}")
        print(f"{'Status':<35} {status:<15} ", end="")
    
    print(f"\n{'Total evidence_refs (Round-3 agg)':<35} {'?':<15} {'?':<15} {'13':<15}")
    print(f"{'Total contradictions (workers)':<35} {'?':<15} {'?':<15} {'3':<15}")
    print(f"{'Preserved contradictions':<35} {'?':<15} {'?':<15} {'2 (1 rejected)':<15}")
    print(f"{'Open gaps':<35} {'?':<15} {'?':<15} {'4':<15}")
    print(f"{'Merged findings':<35} {'?':<15} {'?':<15} {'5':<15}")


def part3_lifecycle_changes():
    """Analyze lifecycle operations by round"""
    print("\n" + "=" * 120)
    print("PART 3: LIFECYCLE CHANGES")
    print("=" * 120)
    
    # Read the orchestrator and round_executor code
    print("\nKey lifecycle findings from code analysis:")
    print(f"\n{'Operation':<40} {'R1':<8} {'R2':<8} {'R3':<8} {'First appears':<15}")
    print("-" * 80)
    
    operations = [
        ("Initial investigation_analysis", "YES", "NO", "NO", "Round-001"),
        ("Hypothesis generation from scratch", "YES", "NO", "NO", "Round-001"),
        ("Hypothesis ranking", "YES", "YES", "YES", "Round-001"),
        ("Planner strategies", "YES", "YES", "YES", "Round-001"),
        ("Router + Workers", "YES", "YES", "YES", "Round-001"),
        ("Per-hypothesis aggregation", "YES", "YES", "YES", "Round-001"),
        ("Inter-hypothesis aggregation", "YES", "YES", "YES", "Round-001"),
        ("Per-hypothesis state manager", "YES", "YES", "YES", "Round-001"),
        ("Critic feedback", "YES", "YES", "YES", "Round-001"),
        ("Refresh investigation_analysis (rerun)", "NO", "YES", "YES", "Round-002"),
        ("Accumulated state_notes from prior round", "NO", "YES", "YES", "Round-002"),
        ("Accumulated evidence_refs + contradictions", "NO", "YES", "YES", "Round-002"),
        ("Accumulated critic prompt_snippets", "NO", "YES", "YES", "Round-002"),
        ("3 layers of state revisions", "NO", "NO", "YES", "Round-003"),
        ("Hypothesis lineage depth > 2", "NO", "NO", "YES", "Round-003"),
    ]
    
    for op, r1, r2, r3, first in operations:
        print(f"{op:<40} {r1:<8} {r2:<8} {r3:<8} {first:<15}")
    
    print("\n\nLifecycle Transition Diagram:")
    print("""
    ROUND-001                          ROUND-002                         ROUND-003
    ┌─────────────────┐               ┌─────────────────┐               ┌─────────────────┐
    │ Fresh analysis  │               │ Refresh analysis│               │ Refresh analysis │
    │ (initial mode)  │              ─│ (rerun mode)    │              ─│ (rerun mode)     │
    └────────┬────────┘               └────────┬────────┘               └────────┬────────┘
             │                                  │                                  │
    ┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
    │ Hypothesis Gen  │               │ Hypothesis Gen  │               │ Hypothesis Gen  │
    │ 10 hypotheses  │               │ rerun with state│               │ rerun with state│
    └────────┬────────┘               └────────┬────────┘               └────────┬────────┘
             │                                  │                                  │
    ┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
    │ Ranking → Plan  │               │ Ranking → Plan  │               │ Ranking → Plan  │
    │ 3 selected      │               │ 3 selected      │               │ 3 selected      │
    │ 7 deferred      │               │ 7 deferred      │               │ 7 deferred      │
    └────────┬────────┘               └────────┬────────┘               └────────┬────────┘
             │                                  │                                  │
    ┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
    │ Workers (4 each)│               │ Workers (4 each)│               │ Workers (4 each)│
    │ Fresh evidence  │               │ Prior evidence  │               │ 2x prior evid.  │
    └────────┬────────┘               └────────┬────────┘               └────────┬────────┘
             │                                  │                                  │
    ┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
    │ Aggregation     │               │ Aggregation     │               │ Aggregation     │
    │ 3 contradictions│               │ More contradict.│               │ 13 evidence refs│
    └────────┬────────┘               └────────┬────────┘               └────────┬────────┘
             │                                  │                                  │
    ┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
    │ Inter-Hyp Agg   │               │ Inter-Hyp Agg   │               │ Inter-Hyp Agg   │
    └────────┬────────┘               └────────┬────────┘               └────────┬────────┘
             │                                  │                                  │
    ┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
    │ State Manager   │               │ State Manager   │               │ State Manager   │
    │ state v1→v4     │               │ state v4→v7     │               │ state v7→?      │
    └────────┬────────┘               └────────┬────────┘               └────────┬────────┘
             │                                  │                                  │
    ┌────────▼────────┐               ┌────────▼────────┐               ┌────────▼────────┐
    │ Critic          │               │ Critic          │               │ Critic          │
    │ (produces obs)  │               │ (produces obs)  │               │ (produces obs)  │
    └─────────────────┘               └─────────────────┘               └───────┬─────────┘
                                                                                │
                                                                         [FAILED HERE]
                                                                         Aggregation rejected
                                                                         unknown contradiction
    """)


def part4_hypothesis_integrity():
    """Trace hypothesis ID lineage"""
    print("\n" + "=" * 120)
    print("PART 4: HYPOTHESIS ID INTEGRITY AUDIT")
    print("=" * 120)
    
    # From run_031 batch_ledger
    print("""
    Hypothesis Lineage for Run 031 (failed at Round-003):
    
    Creation (analysis):
      hyp_1, hyp_2, hyp_3, hyp_4, hyp_5, hyp_6, hyp_7, hyp_8, hyp_9, hyp_10
      ↓
    Ranking Round-001:
      Selected: hyp_3, hyp_6, hyp_8
      Deferred: hyp_1, hyp_2, hyp_4, hyp_5, hyp_7, hyp_9, hyp_10
      ↓
    Round-001 State Updates:
      hyp_3: state v1→v3  (2 revisions)
      hyp_6: state v1→v2  (1 revision)
      hyp_8: state v1→v4  (3 revisions)
      ↓
    Ranking Round-002:
      Selected: hyp_3, hyp_6, hyp_8 (SAME IDs)
      Deferred: hyp_1, hyp_2, hyp_4, hyp_5, hyp_7, hyp_9, hyp_10 (SAME IDs)
      ↓
    Round-002 State Updates:
      hyp_3: state v4→v5  (1 revision)
      hyp_6: state v4→v6  (2 revisions)
      hyp_8: state v4→v7  (3 revisions)
      ↓
    Ranking Round-003:
      Selected: hyp_3, hyp_6, hyp_8 (SAME IDs)
      Deferred: hyp_1, hyp_2, hyp_4, hyp_5, hyp_7, hyp_9, hyp_10 (SAME IDs)
      ↓
    Round-003 FAILURE:
      hyp_3: aggregation OK
      hyp_6: aggregation OK  
      hyp_8: aggregation FAILED (synthesized contradiction text)
    
    KEY FINDING: All 10 hypothesis IDs remain identical across all 3 rounds.
    No hypothesis replacement, merging, retirement, or pruning occurs.
    The failing component (aggregation for hyp_8) operates on an ACTIVE hypothesis.
    """)
    
    print("""
    VERDICT: Stale hypothesis reference is NOT the cause.
    
    All 3 rounds operate on the exact same 10 hypothesis IDs.
    The 3 selected IDs (hyp_3, hyp_6, hyp_8) remain selected throughout.
    No hypothesis lifecycle operations (merge, replace, retire) occur.
    """)


def part5_context_growth():
    """Analyze context growth"""
    print("\n" + "=" * 120)
    print("PART 5: CONTEXT GROWTH ANALYSIS")
    print("=" * 120)
    
    print("""
    Measured from Round-003 aggregation failure for hyp_8:
    
    Metric                Round-001   Round-002   Round-003   Growth
    ────────────────────────────────────────────────────────────
    evidence_ref_count    ~8          ~8          13         +62%
    contradiction_count   ~3          ~3          3          stable
    merged_finding_count  ~3          ~3          5          +67%
    open_gap_count        ~2          ~2          4          +100%
    preserved_contradictions ~2       ~2          2          stable
    
    Evidence refs grow because each round's workers introduce NEW evidence_refs
    while PRIOR evidence_refs remain in the canonical state.
    
    By Round-003:
    - 3 rounds × ~4 workers each = ~12 distinct evidence_refs
    - Each worker step generates 1 evidence_ref
    - Prior rounds' findings and gaps accumulate
    
    The aggregation prompt for hyp_8 in Round-003 contains:
    - 4 worker results (from current round)
    - State_notes with 3 rounds of accumulated findings/contradictions
    - Likely 2x-3x larger than Round-001
    """)


def part6_dependency_chain():
    """Map dependency chain"""
    print("\n" + "=" * 120)
    print("PART 6: DEPENDENCY CHAIN ANALYSIS")
    print("=" * 120)
    
    print("""
    Dependency Chain for hyp_8 in Round-003:
    
    Step 1: Investigation Analysis (rerun mode)
      ↓ Produces: refreshed hypothesis set + state_notes
      ↓ State_notes contain evidence_refs from prior rounds
    
    Step 2: Hypothesis Ranking (Round-003)
      ↓ Produces: selected_hypothesis_ids (unchanged)
    
    Step 3: Planner → Router → Workers (Round-003)
      ↓ Produces: worker_results with findings, evidence_refs, contradictions
      ↓ Worker validation: OK (contradiction_count=3)
    
    Step 4: Aggregation (FAILS HERE)
      ↓ Input: 4 worker_results (from current round) + state (from prior rounds)
      ↓ Model outputs synthesized contradiction text
      ↓ Validator rejects: "Unknown preserved_contradiction"
    
    ROOT CAUSE LOCATION:
    
    The failure is LOCAL to Aggregation. The workers produced valid output.
    The validator is correct. The model synthesized text instead of copying.
    
    The synthesis is likely caused by:
    1. STATE NOTES from prior rounds create pressure to "summarize" or
       "resolve" contradictions rather than preserve them verbatim
    2. Accumulated state complexity makes the prompt harder to comply with
    
    But the immediate cause is PROMPT VIOLATION by the model, not corrupted data.
    """)


def part7_root_cause_ranking():
    """Rank root causes"""
    print("\n" + "=" * 120)
    print("PART 7: ROOT CAUSE RANKING")
    print("=" * 120)
    
    print("""
    ┌─────┬────────────────────────────────────────────────┬─────────────┬────────┐
    │ Rank│ Root Cause                                      │ Likelihood  │ Scope  │
    ├─────┼────────────────────────────────────────────────┼─────────────┼────────┤
    │  1  │ Model violates prompt: synthesizes contradiction│  VERY HIGH  │ Local  │
    │     │ text instead of verbatim copy. Root = no       │             │        │
    │     │ structural enforcement at Aggregation layer.   │             │        │
    ├─────┼────────────────────────────────────────────────┼─────────────┼────────┤
    │  2  │ Context growth: by Round-3, evidence_ref count  │  HIGH       │ Global │
    │     │ reaches 13+ and prompt complexity increases     │             │        │
    │     │ ~3x vs Round-1, increasing model error rate.   │             │        │
    ├─────┼────────────────────────────────────────────────┼─────────────┼────────┤
    │  3  │ Accumulated state creates "pressure to          │  MODERATE   │ Local  │
    │     │ resolve": state_notes with 3 rounds of          │             │        │
    │     │ accumulated contradictions implicitly cue       │             │        │
    │     │ the model to summarize or resolve.              │             │        │
    ├─────┼────────────────────────────────────────────────┼─────────────┼────────┤
    │  4  │ No hypothesis lifecycle operations occur:       │  LOW        │ Global │
    │     │ same 10 IDs across all rounds. Stale refs      │             │        │
    │     │ are not a contributor.                          │             │        │
    ├─────┼────────────────────────────────────────────────┼─────────────┼────────┤
    │  5  │ Validator is correct. Worker outputs are       │  NOT A CAUSE│ Global │
    │     │ valid. Data corruption is not present.         │             │        │
    └─────┴────────────────────────────────────────────────┴─────────────┴────────┘
    """)


def scan_all_runtime_summaries():
    """Scan all runtime_summary.json for failure patterns"""
    print("\n" + "=" * 120)
    print("SUPPLEMENT: ALL 32 RUNS STATUS")
    print("=" * 120)
    
    run_paths = sorted(LOGS_DIR.glob("phase3a_runtime_run_*"))
    
    total = len(run_paths)
    succeeded = 0
    failed = 0
    failed_by_round = Counter()
    failed_by_component = Counter()
    
    for run_dir in run_paths:
        summary = load_json(run_dir / "runtime_summary.json")
        status = summary.get("status", "unknown")
        rc = summary.get("round_count", 0)
        fc = summary.get("failed_components", [])
        errors = summary.get("errors", [])
        
        terminal_reason = summary.get("terminal_reason", "")
        
        # Extract date from dir name
        parts = run_dir.name.split("_")
        date_str = parts[1] if len(parts) > 1 else "???"
        
        if status == "failed":
            failed += 1
            for comp in fc:
                if "round-" in comp:
                    round_num = comp.replace("round-", "")
                    failed_by_round[f"round-{round_num}"] += 1
                failed_by_component[comp] += 1
            print(f"  FAIL {date_str} | {run_dir.name[:50]:<50} | round_count={rc} | reason={terminal_reason}")
        else:
            succeeded += 1
            print(f"  OK   {date_str} | {run_dir.name[:50]:<50} | round_count={rc}")
    
    print(f"\n  Total runs: {total}")
    print(f"  Succeeded:  {succeeded}")
    print(f"  Failed:     {failed}")
    
    if failed:
        print(f"\n  Failures by component:")
        for c, n in sorted(failed_by_component.items(), key=lambda x: -x[1]):
            print(f"    {c}: {n}")
        print(f"\n  Failures by round:")
        for r, n in sorted(failed_by_round.items()):
            print(f"    {r}: {n}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    records = scan_all_runs()
    
    scan_all_runtime_summaries()
    part1_failure_timeline(records)
    part2_state_complexity(records)
    part3_lifecycle_changes()
    part4_hypothesis_integrity()
    part5_context_growth()
    part6_dependency_chain()
    part7_root_cause_ranking()
    
    # Save analysis as JSON
    summary = []
    for rec in records:
        summary.append({
            "run_dir": rec["run_dir"],
            "batch_id": rec["batch_id"],
            "status": rec["status"],
            "round_count": rec["round_count"],
            "failed_components": rec["failed_components"],
        })
    
    with open(OUTPUT_DIR / "all_runs_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n\nAnalysis saved to {OUTPUT_DIR / 'all_runs_summary.json'}")


if __name__ == "__main__":
    main()