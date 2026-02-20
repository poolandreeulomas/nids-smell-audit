# Current Project State — Structural Audit Prototype
Date: 20 February 2026

## 1. What exists right now

We have implemented a first structural audit pipeline for NIDS benchmark partitions (CIC-IDS2017).

The script:

- Iterates over dataset partitions (.csv files).
- Loads 100k rows per partition (for speed).
- Extracts:
  - Basic metadata (shape, class distribution, duplicates)
  - Top 5 features most correlated with Label (binary BENIGN vs non-BENIGN)
  - Intra-class structural metrics per top feature
  - Distribution metrics for discrete feature: Destination Port
- Stores results in `analysis_summary.json`

This is NOT smell detection.
This is signal collection.

---

## 2. What the pipeline is doing conceptually

The script is trying to quantify structural risks such as:

- Deterministic feature-label dependencies
- Structural compression within attack classes
- Low intra-class variability
- Extreme variance imbalance
- Shortcut learning risks

We are NOT deciding yet whether something is a smell.
We are collecting evidence that could later justify a smell.

---

## 3. Metrics currently implemented

### A) Intra-class feature statistics

For top correlated features:
- Mean
- Standard deviation
- Variance
- Unique values (proxy for diversity)
- Coefficient of variation (std / mean)
- Variance ratio (max variance / min variance between classes)

These allow detection of:
- Structural compression
- Low diversity in one class
- Potential artificial patterns

---

### B) Distribution metrics (Destination Port)

For each class:
- dominant_ratio → frequency of most common value
- entropy → Shannon entropy
- js_divergence → distribution difference between classes

Interpretation logic:
- dominant_ratio ≈ 1.0 + entropy ≈ 0 → deterministic pattern
- High JSD → strong distribution divergence

---

## 4. What we observed so far

### DDoS partition
- Destination Port:
  - dominant_ratio = 1.0 (DDoS)
  - entropy = 0.0
- Extremely deterministic
- Strong shortcut learning risk

### PortScan partition
- Structural compression in packet-level features
- High variance ratios
- Destination Port not deterministic, but distributions differ

### Bot partition
- Much less extreme structure
- More realistic variability
- Divergence still measurable

---

## 5. What this means

The tool already:

- Detects structural compression
- Detects deterministic artifacts
- Quantifies distribution divergence

It demonstrates that:
Different partitions exhibit very different structural risks.

This validates the usefulness of a structural audit tool.

---

## 6. What is NOT done

- No formal smell definitions yet
- No thresholds
- No risk scoring
- No agent
- No automation of decision-making

We are still in evidence-gathering mode.

---

## 7. Next logical step (after returning)

1. Formalize Smell #1:
   Deterministic or near-deterministic feature dependency.

2. Define:
   - Metric criteria
   - Threshold candidates
   - Risk interpretation

3. Only then:
   Design structured smell detection module.

NOT before.

---

## 8. Mental reminder

Do not:
- Add random new metrics.
- Refactor for elegance.
- Inflate complexity.

The pipeline works.
The next step is formalization, not expansion.