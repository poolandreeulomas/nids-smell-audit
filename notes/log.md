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

## 24 March 2026

### Architectural pivot — From static pipeline to agent-based auditing system

After reviewing the project direction and receiving supervisor feedback, the methodology has been fundamentally revised.

The previous approach treated the system as a static pipeline, where statistical signals were computed first and later interpreted through heuristics and an LLM used mainly for summarization.

However, this architecture does not fully exploit the capabilities of LLMs and does not align with the intended research contribution.

The project is therefore redefined as an agent-based system, where the LLM is no longer a passive component but an active decision-maker.

---

### Key conceptual change

The statistical analysis pipeline is no longer a fixed sequence of steps.

Instead, it is reinterpreted as a set of analytical tools that the agent can invoke dynamically.

This shifts the system from:

- pipeline-driven analysis  
→ to  
- agent-driven exploration  

The agent is now responsible for:

- deciding what to analyze  
- selecting which tools to use  
- forming and refining hypotheses  
- interpreting intermediate results  

---

### Role of the existing implementation

The previously developed exploratory pipeline is not discarded.

Instead, it becomes the core toolset of the agent.

All implemented components are reused as tools:

- segment-level statistical analysis  
- distribution metrics  
- feature redundancy detection  
- hierarchical aggregation (segment / cross-segment / global)  

This ensures that prior work directly contributes to the new architecture.

---

### Agent-based auditing process

The system is now structured around an iterative reasoning loop:

1. Observe global dataset context and current memory  
2. Form a hypothesis about a potential structural issue  
3. Select and invoke an analytical tool  
4. Interpret the result  
5. Store the observation  
6. Repeat for a limited number of steps  

This process allows the agent to progressively refine its understanding of the dataset.

---

### Memory and context design

A lightweight memory structure is introduced to store:

- previously used tools  
- obtained results  
- partial interpretations  

The global dataset overview is always included in the agent context to prevent loss of orientation.

This avoids the need for complex memory architectures while enabling multi-step reasoning.

---

### Design constraints

To ensure stability and interpretability:

- the number of iterations is limited (3–5 steps)  
- the agent must justify tool usage  
- the system prioritizes simplicity over completeness in early stages  

The goal is to build a controlled and analyzable agent, not a fully autonomous system.

---

### Updated system objective

The objective is no longer to statically compute risk signals, but to:

→ study how an LLM agent can autonomously investigate dataset structure  
→ using statistical tools  
→ and identify potential structural artifacts  

This reframes the contribution of the project towards:

- agent reasoning over structured data  
- tool-based exploration strategies  
- semi-automated dataset auditing  

---

### Implementation plan (next phase)

1. Refactor exploratory code into callable tools  
2. Implement a minimal agent loop (no external frameworks)  
3. Integrate an LLM via API (for initial stability)  
4. Execute the agent on a single dataset segment  
5. Analyze behaviour and identify failure modes  

---

### Expected challenges

- agent selecting irrelevant tools  
- shallow or incorrect interpretations  
- lack of exploration diversity  
- over-reliance on obvious signals  

These challenges are expected and will guide iterative improvements.

---

### Strategic insight

The value of the system does not lie in the statistical metrics themselves, but in:

→ how the agent uses them  
→ how it prioritizes analysis  
→ and how it constructs explanations  

---

### Next milestone

Develop a working agent-based MVP capable of:

- invoking tools  
- performing basic reasoning  
- identifying at least one known structural artifact  

This will serve as the foundation for further refinement and evaluation.

---

### Note

This pivot aligns the project more closely with the original research vision and significantly increases its potential contribution compared to the previous pipeline-based approach.

---

## 8 April 2026

### MVP agent audit and stabilization

Performed a full technical audit of the first ReAct-style MVP agent for tabular NIDS inspection.

The purpose of this phase was to verify that the agent was not only executable, but also methodologically defensible for later experimentation.

The audit focused on:

- prompt completeness
- parser and action reliability
- tool dispatch safety
- reproducibility metadata
- metric correctness
- packaging and execution hygiene

---

### Main issues identified and corrected

#### Prompt visibility and state exposure

The prompt was not exposing the search space and state clearly enough.

This was corrected so the agent now receives explicit access to:

- available tools
- available features
- analyzed features
- recent history

This made the reasoning loop more grounded and easier to debug.

#### Metric semantics review

The first behavioral metrics were audited because some definitions did not match real run behavior cleanly.

In particular:

- `valid_action_rate` was aligned with successful executions
- `attempted_action_rate` was separated conceptually from valid actions
- later groundwork was established for correcting `action_justification_rate`

#### Experiment execution cleanup

The experiment entrypoints and package structure were normalized so module-style execution became stable.

This reduced fragile import-order behavior and made the repository easier to run consistently.

---

### Environment and dependency stabilization

The local execution environment was normalized around a single repository-local virtual environment:

- `venv/`

Actions performed:

- installed and normalized dependencies in the repo-local environment
- added `openai==1.75.0` to `requirements.txt`
- resolved confusion between `.venv` and `venv`
- verified the correct interpreter path inside the project

API-key handling was also stabilized for local development so real runs against the model could be executed safely without changing repository behavior.

---

### Dataset organization cleanup

The CIC-IDS2017 partition files used by the MVP were reorganized into a clearer data layout:

- `data/cic_ids_2017/`

This separated dataset files from Python data-layer code and simplified configuration.

---

### Logging and transparency improvements

Runtime transparency was improved so failed runs became easier to inspect.

Changes included:

- clearer artifact output from `run_mvp.py`
- recent error summaries in console output
- cleaner persisted run logs for later analysis

---

### Status at end of day

The MVP agent was no longer just a scaffold.

By the end of the day, it was:

- executable end-to-end
- reproducible enough for controlled experiments
- instrumented for debugging
- ready for first real API-backed runs

The next step was to execute real runs and validate actual behavior from logs rather than architecture alone.

## 9 April 2026

### Real-run analysis and evidence-based behavior review

Executed multiple real runs of the MVP agent and shifted evaluation from architecture review to log-based behavioral analysis.

The objective of this phase was to answer:

- what the agent actually does during execution
- whether it truly reasons across steps
- whether tools influence decisions
- whether resulting metrics match reality

---

### Confirmed behavior from runs

The agent was observed to:

- complete bounded 5-step runs end-to-end
- produce valid `THOUGHT / ACTION / ACTION_INPUT` outputs reliably
- adapt after tool errors
- reuse prior observations in subsequent steps
- use both `correlation` and `wasserstein`
- confirm promising features with a second tool in several runs

This was an important milestone because it showed the agent was no longer behaving like a shallow single-tool loop.

---

### Critical metric fix

The run audit revealed a real bug:

- `action_justification_rate` could exceed 1.0 due to inconsistent numerator / denominator definitions

This was corrected by making the rate consistent with attempted actions and clamping it to the valid range.

Additional clarification was also introduced for feature-count metrics:

- successful exploration was separated from attempted exploration

This made the behavioral metrics much more trustworthy for later comparison across runs.

---

### Prompt and tool-awareness improvements

To improve decision quality without changing the core architecture, the prompt/state layer was made more informative.

The agent now sees analyzed features in a more interpretable form, including:

- which tools were already used per feature
- key numerical evidence already observed

The prompt was also minimally adjusted to encourage:

- confirming promising features with a different tool before moving on

This directly improved multi-tool behavior in later runs.

---

### Tool error diagnostics improved

The `correlation` tool was extended so `INSUFFICIENT_VARIANCE` errors now expose more interpretable metadata, including:

- feature variance
- label variance
- number of unique feature values

This made failure cases much more useful for audit and thesis reporting.

---

### ReAct trace visibility in terminal

Added live terminal tracing for the ReAct loop so each run now prints:

- model decision
- thought
- action
- action input
- tool result
- execution status

This gave direct visibility into the reasoning process during execution instead of only after reading JSON logs.

---

### Deterministic interpretation layer added

Built a deterministic post-run analysis layer on top of existing logs.

New analysis modules were added to:

- interpret run logs into structured insights
- summarize them into readable sections for humans
- do so without any LLM calls

This produced a reproducible explanation layer suitable for debugging, evaluation, and thesis writing.

---

### Multi-run evaluation and scoring

Added a deterministic evaluation workflow for comparing multiple runs.

This layer now supports:

- scoring runs over 100 using a transparent heuristic
- ranking recent runs
- aggregate consistency analysis
- strengths and risks per run
- executive summaries for end users
- optional saving of evaluation artifacts under `reports/evaluations/`

This made it possible to compare runs operationally without relying on subjective manual reading every time.

---

### Main empirical observations from the day

Across repeated runs, the agent began to show a partially stable exploration pattern.

Recurring findings included:

- `Total Length of Fwd Packets` frequently appearing as the strongest confirmed feature
- `Fwd Packet Length Mean` repeatedly emerging as a strong candidate
- `Flow Duration` often used as a weak baseline feature
- recurrent failure of `correlation` on `Flow Bytes/s` due to `INSUFFICIENT_VARIANCE`

This suggests the agent is already extracting some real structural signal, but still has a narrow exploration bias.

---

### Status at end of day

By the end of the day, the MVP had progressed from a runnable prototype to a controlled experimental agent with:

- real execution traces
- reproducible run artifacts
- interpretable summaries
- deterministic multi-run evaluation
- a first operational scoring framework

The system is still an MVP, but it is now substantially more useful for:

- debugging agent behavior
- comparing runs
- identifying recurring strong features
- documenting progress rigorously for the thesis