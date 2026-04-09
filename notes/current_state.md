# Current Project State - Structural Audit Prototype
Date: 20 February 2026

## 1. What Exists Right Now

We have implemented a first structural audit pipeline for NIDS benchmark partitions (CIC-IDS2017).

The script:

- Iterates over dataset partitions (`.csv` files).
- Loads 100k rows per partition (for speed).
- Extracts:
  - Basic metadata (shape, class distribution, duplicates).
  - Top 5 features most correlated with `Label` (binary `BENIGN` vs non-`BENIGN`).
  - Intra-class structural metrics per top feature.
  - Distribution metrics for discrete feature `Destination Port`.
- Stores results in `analysis_summary.json`.

This is NOT smell detection.
This is signal collection.

## 2. What the Pipeline Is Doing Conceptually

The script is trying to quantify structural risks such as:

- Deterministic feature-label dependencies.
- Structural compression within attack classes.
- Low intra-class variability.
- Extreme variance imbalance.
- Shortcut learning risks.

We are NOT deciding yet whether something is a smell.
We are collecting evidence that could later justify a smell.

## 3. Metrics Currently Implemented

### 3.1 Intra-Class Feature Statistics

For top correlated features:

- Mean.
- Standard deviation.
- Variance.
- Unique values (proxy for diversity).
- Coefficient of variation (`std / mean`).
- Variance ratio (`max variance / min variance` between classes).

These allow detection of:

- Structural compression.
- Low diversity in one class.
- Potential artificial patterns.

### 3.2 Distribution Metrics (Destination Port)

For each class:

- `dominant_ratio`: frequency of most common value.
- `entropy`: Shannon entropy.
- `js_divergence`: distribution difference between classes.

Interpretation logic:

- `dominant_ratio` ~= 1.0 + `entropy` ~= 0 -> deterministic pattern.
- High JSD -> strong distribution divergence.

## 4. What We Observed So Far

### 4.1 DDoS Partition

- Destination Port:
  - `dominant_ratio = 1.0` (DDoS).
  - `entropy = 0.0`.
- Extremely deterministic.
- Strong shortcut learning risk.

### 4.2 PortScan Partition

- Structural compression in packet-level features.
- High variance ratios.
- Destination Port not deterministic, but distributions differ.

### 4.3 Bot Partition

- Much less extreme structure.
- More realistic variability.
- Divergence still measurable.

## 5. What This Means

The tool already:

- Detects structural compression.
- Detects deterministic artifacts.
- Quantifies distribution divergence.

It demonstrates that different partitions exhibit very different structural risks.

This validates the usefulness of a structural audit tool.

## 6. What Is Not Done

- No formal smell definitions yet.
- No thresholds.
- No risk scoring.
- No agent.
- No automation of decision-making.

We are still in evidence-gathering mode.

## 7. Next Logical Step (After Returning)

1. Formalize Smell #1: deterministic or near-deterministic feature dependency.
2. Define:
   - Metric criteria.
   - Threshold candidates.
   - Risk interpretation.
3. Only then: design a structured smell detection module.

NOT before.

## 8. Project Overview

This project aims to develop an automated auditing system for Network Intrusion Detection System (NIDS) datasets.

The goal is to identify structural artifacts (dataset design flaws) that may negatively impact machine learning model evaluation.

These issues include:

- Deterministic features (shortcut learning risks).
- Low intra-class diversity.
- Feature redundancy.
- Artificial patterns introduced by dataset generation.
- Class imbalance and structural biases.

The system is inspired by:

- Flood et al. (dataset design smells).
- Jacobs et al. (shortcut learning and underspecification).

## 9. Previous Approach (Deprecated)

Initially, the system followed a pipeline architecture:

`dataset -> statistical analysis -> JSON -> heuristics -> LLM -> report`

This approach treated the LLM as a passive summarization component, which is NOT aligned with the project goals.

## 10. New Approach (Agent-Based System)

The system is now being redesigned as an LLM agent with tool access.

The agent is responsible for:

- Exploring the dataset autonomously.
- Selecting which analyses to run.
- Forming hypotheses about potential issues.
- Refining its reasoning iteratively.

## 11. Core Architecture

`Dataset -> Analytical Tools -> LLM Agent -> Iterative Loop -> Audit Report`

Key idea:

The statistical pipeline is no longer a fixed preprocessing step.
Instead, it becomes a set of tools that the agent can invoke dynamically.

## 12. Available Tools

The following functions (already implemented) must be exposed as tools:

- `get_global_overview(df)`:
  - Class distribution.
  - Dataset size.
  - Duplicates.
- `analyze_feature_by_class(df, feature)`:
  - Mean, std, variance.
  - Coefficient of variation.
  - Intra-class structure.
- `distribution_metrics(df, feature)`:
  - Dominant ratio.
  - Entropy.
  - Jensen-Shannon divergence.
- `detect_feature_redundancy(df)`:
  - Highly correlated feature pairs.

These tools return structured outputs (`dict`s).

## 13. Agent Behaviour

The agent follows an iterative reasoning loop:

1. Observe:
   - Global dataset context.
   - Previous observations (memory).
2. Hypothesis:
   - Identify a potential structural artifact.
3. Action:
   - Select the most relevant tool.
4. Observation:
   - Interpret tool output.
5. Update:
   - Store findings in memory.
6. Repeat (limited steps).

## 14. Memory Design

Memory is a simple list of previous steps:

- Tool used.
- Input parameters.
- Result.
- Interpretation.

This allows multi-step reasoning without complex architectures.

## 15. Constraints

- `max_steps`: 3-5 iterations.
- Always include global context in prompt.
- Agent must justify tool usage.
- Avoid infinite loops.

## 16. Output Requirements

The system should produce a structured audit:

- Detected artifact (or risk).
- Affected features or segments.
- Explanation (why it is suspicious).
- Confidence level (optional).
- Suggested validation steps for the researcher.

## 17. Design Philosophy

This system is NOT meant to fully automate smell detection.

Instead, it acts as:

- An intelligent assistant.
- Highlighting risks.
- Guiding human validation.

## 18. Current Development Status

Already implemented:

- Statistical analysis pipeline.
- Feature-level metrics.
- Distribution metrics.
- Redundancy detection.
- JSON structured output.

## 19. Current Refactor Goal

Transform existing pipeline into:

- A modular tool-based system.
- A system usable by an LLM agent.

## 20. Next Steps

1. Refactor existing code into callable tools.
2. Implement basic agent loop.
3. Integrate LLM (API-based for MVP).
4. Run agent on one dataset partition.
5. Observe behaviour and iterate.

## 21. Important Notes for Implementation

- DO NOT over-engineer the agent.
- DO NOT use heavy frameworks initially.
- Keep the loop simple and interpretable.
- Focus on reasoning + tool usage.

## 22. Long-Term Vision

- Improve agent reasoning.
- Add more specialized tools.
- Evaluate on multiple datasets.
- Compare with known dataset issues (Flood et al.).
- Potentially transition to open-source LLMs.

## 23. Key Insight

The main contribution is NOT the statistical metrics.

The contribution is:

- How an agent uses these tools.
- How it uses them to autonomously audit datasets.

## 24. Development Principle

Start simple:

- Working agent > perfect system.

Iterate based on failures.