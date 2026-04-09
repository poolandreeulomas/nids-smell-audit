# MVP Agent - Concrete Execution Plan
Date: 2026-04-09
Scope: Minimal ReAct agent with 2 tools only (correlation, wasserstein)

## 1. Objective of this plan
Build, verify, and evaluate a minimal agent that executes a bounded Thought -> Action -> Observation loop over CIC IDS 2017 tabular data, with strong traceability and measurable progress.

This plan is implementation-oriented and includes:
- build order
- acceptance checks per phase
- observability and reproducibility requirements
- evaluation artifacts

## 2. Definition of Done (DoD)
The MVP is considered successful only if all conditions below are met.

1. Functional loop
- Runs end-to-end for fixed max_steps.
- Each step stores Thought, Action, Action Input, Observation, step status.

2. Tool execution reliability
- Both tools run with valid features.
- Invalid feature/action does not crash run.

3. Parse robustness
- Strict model output contract enforced.
- Parse failures become PARSE_ERROR records and loop continues.

4. Traceability
- Every run log stores model/version, prompt hash, temperature, dataset snapshot metadata, feature list, seed, max_steps.

5. Evaluability
- Run-level metrics are computed automatically:
  - valid_action_rate
  - parse_error_rate
  - unique_features_explored
  - repeated_feature_rate
  - action_justification_rate (simple binary heuristic)

6. Repeatability
- At least 3 runs on same config can be compared with a run comparison script/report.

## 3. Directory and module target (MVP)
Create and use these modules in nids-smell-audit:

- main.py: one-run entrypoint and dependency wiring
- agent/
  - loop.py: ReAct controller
  - parser.py: strict response parser
  - executor.py: action validation and tool dispatch
- tools/
  - correlation.py
  - wasserstein.py
  - registry.py
- prompts/
  - react_prompt.txt
  - builder.py
- state/
  - schema.py
  - store.py
- utils/
  - llm_client.py
  - logging.py
  - metrics.py
  - reproducibility.py
- experiments/
  - run_mvp.py
  - compare_runs.py
  - validate_run.py
- logs/runs/
  - run_YYYYMMDD_HHMMSS.json
  - run_YYYYMMDD_HHMMSS_metrics.json

Implementation rule:
- Build in two explicit passes to avoid accidental complexity.
  - Pass A (scaffold): file skeletons, interfaces, schemas, logging format, CLI wiring.
  - Pass B (logic): tool math, parser behavior, guardrails, metrics computation.
- Do not mix scaffold and logic in the same task when possible.

## 4. Step-by-step execution plan

### Phase 0 - Baseline and freeze assumptions
Goal:
- Freeze MVP scope and operational constraints.

Tasks:
- Confirm only 2 tools are allowed.
- Fix max_steps range (recommended 5 for first stable baseline).
- Define one primary partition for initial tests.
- Freeze dataset convention in a single place (config/loader):
  - label column name
  - normal class value(s)
  - attack class value(s)
  - non-numeric feature filtering policy

Deliverables:
- Config values fixed in config.py.
- One loader contract module with explicit dataset assumptions.

Acceptance checks:
- Single source of truth for max_steps, dataset path, model settings exists.
- No label mapping or feature filtering logic duplicated outside config/loader.

---

### Phase 1 - Tool contract first
Goal:
- Make tool behavior deterministic and machine-readable.

Tasks:
- Implement unified input/output schema for both tools.
- Validate feature existence and numeric compatibility.
- Return structured errors with error_code.

Required output schema:
- ok: bool
- tool: str
- feature_name: str
- value: float or null
- error_code: str or null
- error_message: str or null
- meta: dict

Deliverables:
- tools/correlation.py
- tools/wasserstein.py
- tools/registry.py

Acceptance checks:
- Unit test script calls both tools with:
  - valid feature
  - invalid feature
  - unsupported feature type
- No uncaught exceptions in tool layer.

---

### Phase 2 - State model and history
Goal:
- Make state explicit, inspectable, and easy to persist.

Tasks:
- Create AgentState dataclass-like schema.
- Track:
  - run_id
  - objective
  - current_step
  - max_steps
  - analyzed_features
  - history
  - promising_features (optional)
  - errors
  - metadata
- Implement append_history and feature-evidence update helpers.

Deliverables:
- state/schema.py
- state/store.py

Acceptance checks:
- Synthetic loop simulation updates state correctly for 3 fake steps.
- History order and step numbers are consistent.

---

### Phase 3 - Strict prompt and parser
Goal:
- Enforce predictable model output and controlled failure behavior.

Tasks:
- Build prompt template with:
  - objective
  - available tools
  - analyzed features
  - recent history (last 3-5)
  - strict response format
- Implement strict parser for:
  - THOUGHT
  - ACTION
  - ACTION_INPUT (JSON)
- On parse error:
  - store raw output
  - emit PARSE_ERROR observation

Deliverables:
- prompts/react_prompt.txt
- prompts/builder.py
- agent/parser.py

Acceptance checks:
- Parser test cases:
  - valid output
  - missing ACTION
  - invalid JSON in ACTION_INPUT
  - extra lines noise
- Each invalid case produces PARSE_ERROR object, not crash.

---

### Phase 4 - Agent execution core
Goal:
- Implement bounded ReAct loop with guardrails.

Tasks:
- In each step:
  1) build prompt
  2) call model
  3) parse
  4) validate action
  5) execute tool
  6) update state
- Add minimal guardrails:
  - invalid action handling
  - max_steps hard stop
  - repeat policy (feature sufficiently analyzed after both tools)
  - exploration policy (prefer unseen features next)

Deliverables:
- agent/loop.py
- agent/executor.py
- main.py

Acceptance checks:
- Dry run with mocked LLM reaches max_steps and saves state.
- Invalid action does not stop run.
- Repetition policy is enforced and logged.

---

### Phase 5 - Logging and reproducibility metadata
Goal:
- Ensure full run trace and comparability from day one.

Tasks:
- Persist full run log JSON.
- Persist summary metrics JSON.
- Attach reproducibility block:
  - model_name
  - model_version
  - prompt_hash
  - temperature
  - top_p
  - seed (if used)
  - dataset_path
  - dataset_snapshot (mtime/hash)
  - available_features_hash
  - max_steps
  - code_version (git commit if available)

Deliverables:
- utils/logging.py
- utils/reproducibility.py
- logs/runs/*.json

Acceptance checks:
- Any run can be reloaded and inspected without code execution.
- Two runs can be compared field-by-field in metadata.

---

### Phase 6 - Evaluation tooling
Goal:
- Measure progress objectively, not by impression.

Tasks:
- Implement metrics calculator over run logs:
  - valid_action_rate
  - parse_error_rate
  - tool_error_rate
  - unique_features_explored
  - repeated_feature_rate
  - action_justification_rate (simple binary heuristic)
- Implement run comparison script for stability:
  - overlap of top-k final features
  - rank similarity (simple overlap score for MVP)

Simple heuristic definition for `action_justification_rate` (MVP v1):
- Mark step as justified = 1 only if both conditions are true:
  - selected feature was not already fully explored
  - THOUGHT introduces a new reason not present in recent history window
- Otherwise justified = 0.
- Keep this intentionally coarse for baseline comparability.

Deliverables:
- utils/metrics.py
- experiments/validate_run.py
- experiments/compare_runs.py

Acceptance checks:
- validate_run.py prints pass/fail against minimum thresholds.
- compare_runs.py reports consistency over 3+ runs.

---

### Phase 7 - End-to-end MVP validation (we will need to add the API first)
Goal:
- Prove the full system works in realistic conditions.

Tasks:
- Run at least 5 executions with same config.
- Run at least 2 executions with small prompt variation (version bump).
- Collect metrics and compare.

Minimum MVP thresholds (initial suggestion):
- valid_action_rate >= 0.80
- parse_error_rate <= 0.20
- unique_features_explored >= 3 (for max_steps=5)
- repeated_feature_rate <= 0.30

Deliverables:
- validation report in notes/
- set of run logs in logs/runs/

Acceptance checks:
- Thresholds met or clear diagnosis documented with next fixes.

## 5. Error traceability design
Each history step should include:
- step_id
- prompt_snapshot_id
- raw_model_output
- parsed_output
- execution_status: OK | PARSE_ERROR | INVALID_ACTION | TOOL_ERROR
- observation_payload
- state_delta
- timestamp

This allows exact localization of failures in parser, policy, tool layer, or model output quality.

## 6. Progress evaluation strategy
Use two levels:

1. Intra-run progress
- Does each step reduce uncertainty?
- Proxy for MVP:
  - new feature explored
  - second-tool confirmation completed
  - ranking confidence improved

2. Inter-run stability
- Compare final top-k features across runs.
- Track drift after prompt/model/temperature changes.

## 7. Immediate implementation order (practical)
1. Tool schemas and error handling
2. State schema and history append
3. Prompt builder and parser
4. Loop and executor with guardrails
5. Logging + reproducibility block
6. Metrics + validators
7. Multi-run validation report

## 8. What to avoid during MVP build
- Adding more tools before the two-tool loop is stable.
- Adding dynamic stopping logic before baseline metrics exist.
- Optimizing prompts before parser and logs are robust.
- Expanding to multi-partition runs before single-partition reliability is proven.

## 9. Exit criteria for moving beyond MVP
Move to the next stage only when:
- DoD criteria are met.
- Metrics are stable across repeated runs.
- Failure points are diagnosable from logs without manual guesswork.
