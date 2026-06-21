# Evaluation Metric Extraction Pipeline

This directory contains the metric extraction pipeline used to compute all evaluation metrics for the multi-agent forensic dataset auditing framework thesis.

## Directory Structure

```
evaluation/
├── scripts/
│   ├── validate_corpus.py      # Step 1: Validate artifact completeness
│   ├── extract_metrics.py      # Step 2: Compute per-run evaluation metrics
│   └── aggregate_metrics.py    # Step 3: Aggregate across datasets
├── outputs/
│   ├── corpus_validation.json  # Validation results
│   ├── run_metrics.json        # Per-run metrics (JSON)
│   ├── run_metrics.csv         # Per-run metrics (CSV)
│   ├── aggregated_metrics.json # Aggregated statistics (JSON)
│   ├── aggregated_metrics.csv  # Aggregated statistics (CSV)
│   └── evaluation_summary.md   # Human-readable summary
└── README.md
```

## Usage

Run all three scripts in order from the `scripts/` directory:

```bash
cd evaluation/scripts

# Step 1: Validate that all 14 approved runs have required artifacts
python validate_corpus.py

# Step 2: Extract all metrics for each run
python extract_metrics.py

# Step 3: Aggregate metrics across datasets
python aggregate_metrics.py
```

Or from the repository root:

```bash
python evaluation/scripts/validate_corpus.py
python evaluation/scripts/extract_metrics.py
python evaluation/scripts/aggregate_metrics.py
```

## Evaluation Corpus

The pipeline processes exactly **14 runs** from the frozen evaluation corpus:

### CICIDS2017 (12 runs)

| Run ID | Date | Partition |
|--------|------|-----------|
| 050 | 11-06 | Friday-Morning |
| 053 | 11-06 | Friday-DDoS |
| 064 | 11-06 | Friday-Morning |
| 067 | 12-06 | Friday-Morning |
| 070 | 12-06 | Friday-DDoS |
| 071 | 12-06 | Tuesday |
| 072 | 12-06 | Wednesday |
| 073 | 12-06 | Friday-PortScan |
| 074 | 12-06 | Friday-Morning |
| 075 | 12-06 | Monday |
| 076 | 12-06 | Thursday-Infiltration |
| 077 | 12-06 | Thursday-WebAttacks |

### UNSW-NB15 (2 runs)

| Run ID | Date | Partition |
|--------|------|-----------|
| 080 | 14-06 | Training |
| 081 | 14-06 | Testing |

## Metrics Computed

### Exploration Behaviour
- **Tool Diversity Index**: Shannon entropy of tool action classes
- **Feature Revisit Rate**: Proportion of features analyzed more than once

### Investigation Convergence
- **Hypothesis Stability**: Average Jaccard similarity between consecutive round hypothesis sets
- **Hypothesis Revision Rate**: Hypothesis revisions per worker step
- **State Version Churn**: State revisions per round

### Evidence Production
- **Total Evidence Blocks**: Total tool events with evidence
- **Evidence per Feature**: Average evidence blocks per unique feature
- **Artifact Family Count**: Distinct artifact families detected

### Traceability and Reproducibility
- **History Completeness**: Proportion of steps with recorded artifacts
- **Provenance Completeness**: Proportion of evidence with provenance information
- **State Version History**: Final canonical state version

### Cross-Run Consistency
- **Finding Consistency**: Evidence production agreement across repeated runs
- **Recommendation Consistency**: State version agreement across repeated runs

## Artifact Dependencies

Each script reads from the Phase 3 runtime logs under `nids-smell-audit/Phase3/logs/`. No modifications are made to the runtime artifacts. All scripts operate with read-only access.

### Batch-Level Artifacts
- `runtime_metrics.json`
- `batch_ledger.json`
- `round_manifests/*_snapshot.json`

### Worker-Level Artifacts
- `parsed_steps.json`
- `tool_events.json`
- `runtime_metrics.json`
- `worker_result.json`

### Report-Level Artifacts
- `docs/batch_reports/*.md`
- `final_dataset/final_dataset_report.json`

## Output Formats

- **JSON**: Machine-readable, preserves all detail
- **CSV**: Compatible with pandas, Excel, and statistical tools
- **Markdown**: Human-readable summary for thesis documentation

## Requirements

- Python 3.10+
- Standard library only (no external dependencies)