# Operational Artifact Catalog for Phase 3a
## Bounded Scientific Investigation of NIDS Dataset Artifacts

---

# 1. Purpose

This catalog defines the operational artifact families that Phase 3a should investigate.

The goal is not to enumerate every possible dataset flaw discussed in the literature.
The goal is to define the subset of artifact families that:

- are meaningful for NIDS evaluation,
- are observable from TSV-level representations,
- can be investigated through deterministic analytical tooling,
- can support evidence-grounded semantic reasoning,
- and can function as stable planning objects inside the Phase 3a architecture.

This catalog is therefore intentionally operational rather than exhaustive.

---

# 2. Role of the Catalog in the Architecture

The catalog exists to support:

- semantic extraction,
- hypothesis generation,
- investigation prioritization,
- canonical artifact-family state,
- coverage reasoning,
- contradiction handling,
- and bounded scientific investigation.

Artifact families are the core planning units of the system.

The planner does not reason over isolated features.
It reasons over candidate artifact families.

The executor does not try to "understand the dataset."
It investigates bounded hypotheses related to artifact families.

The refiner updates canonical artifact-family state based on evidence gathered during investigation.

---

# 3. Important Scope Boundary

This catalog only includes artifact families that are at least partially observable through:

- TSV feature representations,
- metadata,
- feature statistics,
- distributional structure,
- dependency analysis,
- neighborhood structure,
- and flow-level analytical tooling.

Artifacts that require:

- raw PCAP inspection,
- external infrastructure knowledge,
- packet payload semantics,
- unavailable labeling procedures,
- or inaccessible capture protocols

are intentionally excluded from the active Phase 3a ontology.

The system should not reason strongly about artifact families it cannot realistically observe.

---

# 4. Core Ontology Structure

Each artifact family should conceptually contain:

```yaml
artifact_family:
  type:
  description:
  mechanisms:
  observable_signatures:
  supporting_evidence:
  weakening_evidence:
  contradiction_signals:
  verification_methods:
  typical_failure_modes:
  confidence_behavior:
  saturation_behavior:
```

The exact schema is intentionally deferred.
This section defines the conceptual structure only.

---

# 5. Core Artifact Families

The following artifact families are considered operationally valid for Phase 3a.

---

# 5.1 Shortcut / Highly Dependent Feature Families

## Description

A subset of features acts as an unintended shortcut for classification.

The model may learn highly predictive correlations that do not represent the underlying attack semantics.

These shortcuts often emerge from:
- metadata leakage,
- protocol artifacts,
- flow construction bias,
- timing structure,
- IP-related structure,
- or dataset generation procedures.

This is one of the most important artifact families in NIDS datasets.

---

## Typical Mechanisms

- feature leakage
- deterministic protocol correlation
- metadata identity leakage
- attack-generation artifacts
- timing shortcuts
- flow ID dependence
- source/destination bias

---

## Observable Signatures

- extremely high feature-label dependency
- highly concentrated predictive neighborhoods
- near-deterministic relations
- strong dependency clusters
- isolated dominant features
- low redundancy requirement for prediction
- suspiciously separable feature regions

---

## Supporting Evidence

Examples:

- unusually strong pairwise dependencies
- dominant mutual-information relationships
- near-perfect feature-label separability
- collapse of predictive uncertainty
- strong shortcut validation results

---

## Weakening Evidence

Examples:

- predictive signal distributed across many unrelated features
- strong robustness under feature removal
- no dominant dependency structure

---

## Contradiction Signals

Examples:

- dependency disappears after local segmentation
- shortcut only exists inside one subcluster
- prediction remains stable after removing suspected shortcut anchors

---

## Verification Methods

- feature_relation
- shortcut_analysis
- dependency concentration analysis
- local neighborhood comparison
- feature ablation analysis

---

## Typical Failure Modes

- learning dataset identity instead of attack semantics
- inflated benchmark performance
- poor cross-dataset generalization
- fragile deployment behavior

---

# 5.2 Artificial Dependency Structures

## Description

The dataset contains dependency structures that emerge from generation artifacts rather than genuine behavioral relationships.

These structures are often produced by:
- scripted attack execution,
- repeated attack templates,
- synthetic generation,
- deterministic traffic replay,
- or limited scenario diversity.

This family is closely related to shortcut learning but focuses on structural dependency topology rather than predictive dominance alone.

---

## Typical Mechanisms

- scripted generation
- repeated attack sessions
- deterministic replay
- synthetic feature coupling
- constrained scenario diversity

---

## Observable Signatures

- large dependency clusters
- repeated relational motifs
- unusually stable feature neighborhoods
- strong correlated subspaces
- structurally repetitive flow groups

---

## Supporting Evidence

Examples:

- high redundancy concentration
- repeated dependency motifs
- dense correlated subgraphs
- repeated cluster topology
- low relational entropy

---

## Weakening Evidence

Examples:

- dependency structure varies across regions
- no stable relational clusters
- diverse local topology

---

## Contradiction Signals

Examples:

- dependency disappears under segmentation
- correlated regions map to unrelated behaviors
- dependency strength unstable across subsets

---

## Verification Methods

- feature_relation
- neighborhood_consistency_analysis
- embedding_structure_analysis
- cluster-density analysis
- graph-based dependency analysis

---

## Typical Failure Modes

- memorization of generation process
- unrealistic generalization assumptions
- benchmark inflation through structural repetition

---

# 5.3 Distribution Collapse / Low Diversity

## Description

The dataset contains insufficient behavioral diversity.

Large portions of the data collapse into a small number of dominant structures, reducing variability and encouraging overfitting to narrow behavioral patterns.

This family is highly associated with:
- traffic collapse,
- repetitive attack execution,
- low scenario diversity,
- and synthetic simplification.

---

## Typical Mechanisms

- repeated attack traces
- limited capture environments
- narrow attack variation
- replayed sessions
- deterministic traffic timing

---

## Observable Signatures

- dominant clusters
- low entropy regions
- repetitive neighborhoods
- low variance subspaces
- sparse behavioral diversity
- repeated local structures

---

## Supporting Evidence

Examples:

- low entropy measurements
- concentrated cluster distributions
- low neighborhood diversity
- repeated structural motifs
- low coverage across feature space

---

## Weakening Evidence

Examples:

- multiple heterogeneous substructures
- strong behavioral variation
- stable diversity across labels and regions

---

## Contradiction Signals

Examples:

- diversity increases after temporal segmentation
- apparent collapse caused only by one subgroup
- dominant cluster explained by legitimate protocol behavior

---

## Verification Methods

- distribution_analysis
- embedding_structure_analysis
- neighborhood_consistency_analysis
- entropy analysis
- cluster coverage analysis

---

## Typical Failure Modes

- unrealistic benchmark performance
- brittle generalization
- poor robustness to real-world variability
- oversimplified attack representation

---

# 5.4 Duplicate / Near-Duplicate Structures

## Description

The dataset contains duplicated or near-duplicated flows, sessions, neighborhoods, or structural patterns.

These artifacts may inflate evaluation performance and distort dependency structure.

This family includes both:
- exact duplication,
- and structural near-duplication.

---

## Typical Mechanisms

- replayed attacks
- repeated sessions
- duplicated preprocessing outputs
- synthetic augmentation artifacts
- deterministic traffic generation

---

## Observable Signatures

- repeated rows
- repeated neighborhoods
- identical feature subspaces
- high local density duplication
- near-identical cluster repetitions

---

## Supporting Evidence

Examples:

- high duplicate ratios
- repeated embedding neighborhoods
- low-distance repeated structures
- repeated flow signatures

---

## Weakening Evidence

Examples:

- duplication isolated to small regions
- duplication explained by legitimate periodic traffic
- strong diversity after local segmentation

---

## Contradiction Signals

Examples:

- duplicates disappear after normalization correction
- repeated structures arise from encoding artifacts only

---

## Verification Methods

- duplication_analysis
- neighborhood_consistency_analysis
- embedding_structure_analysis
- density-based duplicate analysis

---

## Typical Failure Modes

- train/test contamination
- inflated generalization estimates
- distorted neighborhood topology
- memorization instead of learning

---

# 5.5 Label Inconsistency / Suspicious Label Structures

## Description

The labeling structure appears inconsistent, noisy, ambiguous, or structurally suspicious.

The goal is not to prove incorrect labels directly.
The goal is to identify statistically suspicious label behavior.

This family is especially important because labeling flaws can propagate through all downstream evaluation.

---

## Typical Mechanisms

- automated labeling errors
- weak labeling heuristics
- ambiguous attack boundaries
- inconsistent labeling pipelines
- contamination between attack families

---

## Observable Signatures

- overlapping label neighborhoods
- contradictory local structures
- inconsistent dependency behavior
- unexpected label mixing
- unstable class boundaries

---

## Supporting Evidence

Examples:

- local label contradiction
- high overlap between supposedly distinct classes
- inconsistent cluster-label alignment
- anomalous neighborhood transitions

---

## Weakening Evidence

Examples:

- clear local separation
- stable label neighborhoods
- consistent multi-region structure

---

## Contradiction Signals

Examples:

- apparent overlap explained by protocol similarity
- local ambiguity limited to transition regions
- class mixing disappears after segmentation

---

## Verification Methods

- neighborhood_consistency_analysis
- feature_relation
- local cluster analysis
- label-neighborhood comparison

---

## Typical Failure Modes

- noisy evaluation
- unstable model behavior
- misleading benchmark comparisons
- false assumptions about attack separability

---

# 5.6 Representation Artifacts

## Description

The feature representation itself introduces misleading structure unrelated to genuine network behavior.

These artifacts emerge from:
- feature extraction choices,
- encoding procedures,
- preprocessing pipelines,
- flow-construction logic,
- or representation simplifications.

This family is especially important because many NIDS benchmarks rely on derived flow-level representations.

---

## Typical Mechanisms

- flawed feature extraction
- flow-construction bias
- preprocessing artifacts
- encoding shortcuts
- timestamp artifacts
- aggregation artifacts

---

## Observable Signatures

- suspicious clustering by metadata-like structure
- abrupt representation discontinuities
- unstable neighborhood geometry
- representation collapse
- artificial separability

---

## Supporting Evidence

Examples:

- embedding instability
- representation-dependent clustering
- feature-space discontinuities
- topology dominated by preprocessing artifacts

---

## Weakening Evidence

Examples:

- stable behavior across representations
- robust neighborhood consistency
- no preprocessing-sensitive topology

---

## Contradiction Signals

Examples:

- structure disappears after normalization correction
- topology explained by legitimate protocol hierarchy
- instability isolated to one encoding stage

---

## Verification Methods

- embedding_structure_analysis
- neighborhood_consistency_analysis
- representation topology analysis
- preprocessing sensitivity analysis

---

## Typical Failure Modes

- models learn representation artifacts instead of traffic behavior
- inflated benchmark separability
- hidden preprocessing leakage
- unstable transfer performance

---

# 6. Relationship Between Artifact Families

Artifact families are not mutually exclusive.

Many artifacts interact.

Examples:

```text
Distribution Collapse
    ->
Artificial Dependency Structures
    ->
Shortcut Learning
```

or:

```text
Representation Artifact
    ->
Artificial Separability
    ->
Shortcut Formation
```

or:

```text
Duplicate Structures
    ->
Neighborhood Distortion
    ->
Label Instability
```

The architecture should therefore reason about:
- interactions,
- overlaps,
- supporting relationships,
- and contradictions between artifact families.

---

# 7. Operational Philosophy

The catalog exists to guide bounded investigation, not to force deterministic conclusions.

The system should:
- investigate,
- gather evidence,
- maintain uncertainty,
- revise hypotheses,
- and preserve contradiction.

The system should not:
- assume artifact existence from weak signals,
- force all observations into predefined categories,
- or hallucinate hidden dataset generation processes.

Artifact families are investigation hypotheses, not guaranteed truths.

---

# 8. Coverage Philosophy

Coverage should operate over:
- artifact families,
- mechanisms,
- verification depth,
- and unresolved uncertainty.

Coverage is not:
- percentage of features visited,
- percentage of rows explored,
- or exhaustive dataset understanding.

Coverage exists to:
- reduce fixation,
- preserve investigation diversity,
- and maintain awareness of unresolved artifact hypotheses.

---

# 9. Final Scope Boundary

This catalog is intentionally constrained to:
- TSV-observable artifacts,
- statistically investigable structures,
- evidence-grounded hypotheses,
- and bounded semantic reasoning.

The architecture should avoid:
- unsupported causal claims,
- inaccessible dataset-generation assumptions,
- and artifact families requiring unavailable information.

The purpose of Phase 3a is not to solve all dataset pathology.

The purpose is to establish a grounded scientific investigation architecture capable of reasoning meaningfully about observable structural artifacts in NIDS datasets.