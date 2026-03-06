## 16/02/2026

### Environment setup

- Created virtual environment using `python -m venv venv`
- Activated environment in PowerShell
- Verified interpreter path using `sys.executable`
- Installed core dependencies: pandas, numpy, scikit-learn
- Generated requirements.txt

### Current status
Environment correctly isolated and reproducible.

### Dataset selection decision

After reviewing Flood et al. (2024) and considering the project scope (agent-assisted detection of design smells in NIDS benchmarks), the CIC-IDS2017 dataset has been selected as the initial target dataset.

### Rationale

- Widely used in academic literature, including recent papers (2024–2025).
- Explicitly discussed in prior benchmark critique studies.
- Publicly available and well-documented.
- Provides pre-extracted flow-based features (tabular format), which simplifies early-stage analysis.
- Suitable for detecting structural design smells such as:  
  - Class imbalance
  - Duplicate / near-duplicate samples
  - Feature-label correlation artefacts
  - Trivial separability issues

### Strategic reasoning

The goal at this stage is not to identify new datasets, but to:

1. Build a functional inspection pipeline.
2. Quantify at least 1–2 design smells reproducibly.
3. Establish a baseline before potentially expanding to additional datasets.

CIC-IDS2017 offers sufficient complexity and known issues to validate the methodology.

### Next step

- Download dataset.
- Inspect file structure and size.
- Implement initial loading script (explore.py).
- Verify memory feasibility with sample loading.

## 19/02/2026

### Exploratory structural analysis — First multi-partition iteration

Implemented a structured exploratory analysis pipeline for CIC-IDS2017 partitions.

Refactored `explore.py` into a partition-centric analysis framework:

- Encapsulated logic into `analyze_partition(file_path)`
- Enabled automatic iteration over multiple dataset partitions
- Separated analysis phases:
  - Phase 1: Dataset sanity checks (shape, duplicates, constant columns)
  - Phase 2: Feature–label association screening (correlation ranking)
  - Phase 3: Intra-class structural statistics (mean, std, variance, unique values, coefficient of variation, variance ratio)
  - Phase 4: Distribution concentration analysis for discrete features (dominant ratio, entropy, Jensen-Shannon divergence)

The goal at this stage is not smell detection yet, but systematic collection of structural signals.

---

### Partitions analyzed

- Friday-WorkingHours-Afternoon-DDos
- Friday-WorkingHours-Afternoon-PortScan
- Friday-WorkingHours-Morning (Bot)

Each partition was analyzed independently to avoid signal dilution from mixing scenarios.

---

### Observations (Preliminary)

#### 1. DDoS partition
- Destination Port is fully deterministic for the attack class (single unique value).
- Entropy ≈ 0 for the attack class.
- High divergence between benign and attack distributions.
- This suggests potential deterministic contextual dependency.

#### 2. PortScan partition
- No deterministic port behavior.
- Extremely low intra-class diversity in packet-count related features.
- However, this may be consistent with the nature of scanning behavior.

#### 3. Bot partition
- More balanced structural behavior.
- No obvious deterministic contextual feature.
- Less extreme intra-class compression.

---

### Key insight

Low intra-class diversity alone does not automatically imply a design smell.

The only clear structural red flag observed so far is the deterministic port usage in the DDoS partition.

This suggests that structural concentration must be interpreted contextually and validated across multiple partitions before formalizing any smell.

---

### Methodological decision

Before defining any formal smell:

- Generalize result storage into structured dictionary format.
- Enable cross-partition comparison without relying on console output.
- Avoid premature formalization based on limited partitions.

The next milestone is to design a structured result schema that allows:

- Per-partition reporting
- Cross-partition comparison
- Identification of repeated structural patterns

---

## 20 Feb 2026 — Structural Audit MVP Stabilized

### Achievements
- Implemented multi-partition structural analysis pipeline.
- Added:
  - Intra-class statistical metrics.
  - Variance ratio computation.
  - Distribution metrics (dominant_ratio, entropy, JSD).
- Structured results into `analysis_summary.json`.
- Cleaned main execution logic and removed duplicate loops.
- Standardized output summary.

### Observations
- DDoS partition shows deterministic Destination Port (dominant_ratio = 1.0).
- PortScan shows strong structural compression in packet features.
- Bot partition appears structurally more realistic.

### Status
Pipeline stable.
Signals coherent.
Ready for smell formalization phase.

### Posible future change
- Evaluate threshold-based feature selection instead of fixed Top-K (for correlation feature-label)

## 5 March 2026 - Formalization of direction and expected functionality

### Project direction clarification — Dataset Structural Auditor

Re-evaluated the conceptual goal of the project after reviewing Flood et al. methodology and the current exploratory pipeline.

Initial assumption:
The tool should automatically detect design smells in NIDS datasets.

Revised understanding:
A fully automatic smell detector is not reliable because many dataset issues are contextual and depend on the attack scenario.

### Methodological adjustment

The system will function as a **Dataset Structural Auditor** rather than a strict smell classifier.

The goal is to:

- Detect statistical signals that may indicate potential dataset design issues.
- Highlight suspicious features, partitions, or flow patterns.
- Provide explanations and suggested verification procedures for researchers.

The tool therefore behaves similarly to a **static analysis tool for datasets**, producing risk indicators rather than definitive judgments.

---

### Role of the reasoning agent (LLM)

The LLM is **not responsible for detecting smells directly**.

Instead, the workflow becomes:

dataset → statistical signals → contextual reasoning → audit report

The reasoning layer is used for:

- interpreting statistical signals
- explaining why a signal might indicate a design smell
- suggesting how the researcher can verify the issue

Example output concept:

Potential shortcut feature detected.

Signals:
- high feature–label correlation
- extremely low entropy within attack class
- dominant value ratio close to 1

Suggested verification:
1. Train a model excluding the feature.
2. Measure performance degradation.
3. Evaluate generalization under modified conditions.

This design ensures robustness even if the reasoning layer is imperfect.

---

### Smell detection philosophy

Instead of binary smell classification, the system should estimate **risk levels**.

Example categories:

HIGH RISK  
Strong structural evidence of shortcut learning.

MEDIUM RISK  
Statistical signals suggest potential dependency but require contextual validation.

LOW RISK  
Feature appears informative but not structurally problematic.

This prevents overclaiming and makes the methodology easier to defend scientifically.

---

### Analysis granularity decision

Dataset analysis will operate at **three structural levels**.

#### Partition level (primary)

Most structural artifacts appear at this level.

Examples:
- deterministic attack features
- low intra-class diversity
- simulation artifacts

Partition analysis should occur incrementally as each dataset file is loaded.

#### Feature level

Feature-specific signals include:

- feature–label correlation
- entropy
- dominant value ratio
- intra-class variance

These signals form the basis for smell risk estimation.

#### Dataset level

Global statistics will be estimated incrementally while processing partitions.

This avoids loading the full dataset into memory.

---

### Incremental processing strategy

To reduce memory usage and improve scalability, dataset analysis should be performed incrementally.

Pipeline concept:

partition → structural analysis → update global statistics

This is conceptually similar to online statistics or SGD-style updates.

Advantages:

- low memory usage
- scalable to large datasets
- early detection of suspicious patterns

---

### First target smell — Highly dependent features

The first smell to formalize will be **highly dependent features**.

Definition concept:

A feature is highly dependent if it allows models to predict the attack class without learning the underlying attack behavior.

Example scenario observed in CIC-IDS2017:

Destination Port = single value for all DDoS flows.

This allows trivial classification rules such as:

if port == X → attack

instead of learning network attack dynamics.

---

### Feature redundancy detection (future extension)

Many NIDS datasets include features that encode the same information.

Example observed in CIC-IDS2017:

Avg Bwd Segment Size  
Bwd Packet Length Mean

Such redundancy may inflate model importance scores and distort evaluation.

Future analysis should therefore detect high feature–feature correlation.

---

### Flow-level analysis considerations

Flood et al. rely on PCAP inspection to analyze flows.

Since this project operates primarily on CSV data, direct flow reconstruction is difficult.

Future approximations may include:

- flow signature clustering
- pattern similarity detection
- approximate flow fingerprinting

This may enable detection of smells such as:

- repetitive flows
- traffic collapse
- artificial diversity

---

### Current project status

The structural analysis pipeline is stable and capable of extracting meaningful statistical signals across dataset partitions.

The next milestone is to formalize the first smell detection rule using the existing statistical signals.

## 5 March 2026 - Exploratory pipeline extension — structural signals

Extended the exploratory structural audit pipeline to collect additional dataset diagnostics before smell formalization.

The goal of this step is to ensure that the exploratory stage captures enough structural signals to support later smell definitions.

The following statistical signals were added.

---

### Class imbalance metric

Added computation of a class imbalance ratio per partition:

largest_class_count / smallest_class_count

This allows identifying partitions where attack classes are extremely underrepresented relative to benign traffic.

Example observation:

- Bot partition shows extreme imbalance (~225:1)

This signal can indicate potential evaluation bias and model instability.

---

### Feature redundancy detection

Implemented detection of highly correlated feature pairs using Pearson correlation.

Procedure:

- Compute correlation matrix across numeric features
- Extract pairs where |correlation| > 0.95
- Store redundant feature pairs in `feature_redundancy`

Purpose:

Detect derived or duplicated features that may artificially inflate feature importance or introduce information leakage.

Example findings:

- `Bwd Packet Length Mean` ↔ `Avg Bwd Segment Size` (correlation = 1.0)
- `Total Fwd Packets` ↔ `Subflow Fwd Packets` (correlation = 1.0)
- `Fwd Header Length` ↔ `Fwd Header Length.1` (correlation = 1.0)

These patterns suggest that several features in CIC-IDS2017 are deterministic transformations of others.

---

### Feature cardinality analysis

Added per-feature cardinality metrics:

- number of unique values
- cardinality ratio (unique_values / dataset_size)

Purpose:

Identify:

- quasi-constant features
- very low variability signals
- potentially useless or degenerate attributes.

Example observations:

Several flag-based features show extremely low cardinality (binary or constant).

---

### Integration with existing signals

The exploratory pipeline now collects the following structural signals per partition:

- dataset metadata
- duplicate samples
- class imbalance ratio
- top feature–label correlations
- intra-class statistical dispersion
- feature redundancy
- feature cardinality
- discrete feature distribution metrics (entropy, dominant ratio, JSD)

All signals are exported to:

`analysis_summary.json`

---

### Interpretation status

The exploratory phase remains **signal collection only**.

No automatic smell classification is performed yet.

The objective is to build a sufficiently rich structural description of the dataset before defining detection heuristics.

---

### Next step

Begin formalization of the **first dataset design smell**.

Candidate smell:

**Deterministic contextual feature**

Motivation:

In the DDoS partition, the attack class uses a single destination port value:

- dominant_ratio = 1.0
- entropy = 0

This indicates that the attack label may be trivially recoverable from a contextual configuration parameter rather than behavioral traffic characteristics.

The next step is to:

1. Define the smell formally.
2. Design detection heuristics using the collected metrics.
3. Integrate smell detection into the analysis pipeline.

## 6 March 2026

### Architectural extension — Layered structural audit

After stabilizing the exploratory structural pipeline, the project methodology was extended to support a **multi-layer structural audit of NIDS datasets**.

The objective is to move beyond isolated partition inspection and provide a **hierarchical analysis of structural signals** across different levels of the dataset.

Instead of producing a single global risk score, the system surfaces **risk signals at different analysis layers**, allowing researchers to inspect potential issues depending on how they intend to use the dataset.

This avoids arbitrary aggregation while maintaining interpretability.

---

### Generalization of dataset units

Although CIC-IDS2017 is organized into partitions corresponding to capture scenarios, not all NIDS datasets follow this structure.

To ensure methodological generalization, the system refers to these units as **dataset segments**.

A segment may represent:

- a capture scenario or file (e.g., CIC datasets)
- an attack class
- a temporal subset
- any user-defined dataset split

This abstraction allows the auditing methodology to remain applicable across multiple NIDS benchmarks.

---

### Layered structural analysis

The auditing framework now operates across three structural layers.

#### Layer 1 — Segment-level analysis

Each dataset segment is analyzed independently.

This layer identifies structural signals including:

- feature–label correlations
- intra-class variability
- deterministic distributions
- feature redundancy
- class imbalance
- feature cardinality anomalies

Additional statistical indicators computed at this level include:

- mean, standard deviation and variance per class
- coefficient of variation
- variance ratio across classes
- entropy and dominant value ratios for discrete features
- Jensen–Shannon divergence between class distributions

Output: **segment-level structural signals**

---

#### Layer 2 — Cross-segment structural relations

Signals are compared across segments to identify **recurring structural patterns** across the dataset.

The system tracks:

- recurrence of features appearing among the most label-correlated features across segments
- recurrence of highly correlated feature pairs (feature redundancy patterns)

These signals help identify dataset artefacts that appear systematically rather than being isolated to a single scenario.

Output: **cross-segment observations**

---

#### Layer 3 — Dataset-level structure

A global dataset summary is maintained during execution.

This layer aggregates structural observations to describe the dataset as a whole.

Examples include:

- total number of analyzed samples
- aggregated class distribution across segments
- number of segments analyzed

This provides a **global structural overview of the dataset** while preserving interpretability of lower-level signals.

Output: **dataset-level structural signals**

---

### Risk communication philosophy

The system does **not attempt to compute a single numeric risk score**.

Instead, it exposes **interpretable structural signals** that help researchers locate potential dataset design issues.

Signals can be characterized using two dimensions:

- **Coverage** — how many dataset segments exhibit the signal
- **Intensity** — how strong the statistical indicator is

This allows prioritization of structural concerns without relying on arbitrary weighting schemes.

---

### Implementation details

The exploratory analysis script has been extended to maintain **incrementally updated statistics during segment iteration**.

During execution, three internal structures are maintained:

- `segment_results`
- `cross_segment_stats`
- `global_dataset_stats`

The workflow is therefore:

dataset → segment analysis → update cross-segment statistics → update global statistics → generate dataset summary

The final results are exported into a hierarchical JSON structure:

- `analysis_summary.json`

This structure enables flexible downstream analysis and will later support **automated detection of candidate datset design smells**

---

### Next step

With the hierarchical structural audit infrastructure implemented, the next milestone is the **formal definition of the first dataset design smell heuristic**

