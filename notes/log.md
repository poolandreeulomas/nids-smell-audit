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

### Next step

- Implement structured results storage (partition-centric).
- Flatten results into comparable tabular form.
- Analyze remaining CIC-IDS2017 partitions.
- Evaluate whether deterministic contextual dependency appears systematically or remains scenario-specific.