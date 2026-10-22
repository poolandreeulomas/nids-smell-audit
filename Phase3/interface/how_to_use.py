"""Interactive How to Use Learning and Exploration Guide for ATLAS.

Grounded in:
- Thesis documentation: methodology.tex, appendices.tex, acronyms.tex
- Live codebase: Phase3 runtime, active tool registry, component CLIs, validators, schemas

Organized according to the Progressive Disclosure principle:
Level 1 -- Orientation (plain language, problem motivation, research purpose)
Level 2 -- Operational Understanding (inputs, outputs, prompts, validation, UI routes)
Level 3 -- Implementation References (source paths, symbols, tests, artifacts, limitations)
"""

from __future__ import annotations

from pathlib import Path
from textwrap import fill
from typing import Any

from interface.welcome import is_color_supported, style

WIDTH = 68


# ---------------------------------------------------------------------------
# Formatting and UI Helpers (consistent with terminal_ui.py and welcome.py)
# ---------------------------------------------------------------------------


def _rule(char: str = "=", color_key: str = "ochre") -> str:
    line = char * WIDTH
    if is_color_supported():
        return style(line, color_key)
    return line


def _subtle_rule(char: str = "-", color_key: str = "brown") -> str:
    line = char * WIDTH
    if is_color_supported():
        return style(line, color_key, dim=True)
    return line


def _block(title: str, lines: list[str] | None = None, char: str = "=") -> str:
    color_key = "amber" if char == "!" else ("brown" if char == "-" else "ochre")
    title_color = "amber" if char in ("=", "!") else "gold"
    wrapped_title = fill(
        title,
        width=WIDTH - 4,
        initial_indent="  ",
        subsequent_indent="  ",
    ).splitlines()
    output = [_rule(char, color_key=color_key)]
    for t_line in wrapped_title:
        output.append(style(t_line, title_color, bold=True) if is_color_supported() else t_line)
    output.append(_rule(char, color_key=color_key))
    if lines:
        cleaned_lines = list(lines)
        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()
        output.extend(cleaned_lines)
    output.append(_rule(char, color_key=color_key))
    return "\n".join(output)


def _meta_lines(path_label: str, hint: str | None = None) -> list[str]:
    lines: list[str] = []
    prefix = "  Path: "
    subsequent = "        "
    wrapped_path = fill(
        f"{prefix}{path_label}",
        width=WIDTH,
        initial_indent="",
        subsequent_indent=subsequent,
    ).splitlines()
    for idx, line in enumerate(wrapped_path):
        if idx == 0:
            if is_color_supported():
                lines.append(f"  {style('Path:', 'muted')} {style(line[len(prefix):], 'light_grey')}")
            else:
                lines.append(line)
        else:
            if is_color_supported():
                lines.append(style(line, "light_grey"))
            else:
                lines.append(line)

    if hint:
        h_prefix = "  Hint: "
        wrapped_hint = fill(
            f"{h_prefix}{hint}",
            width=WIDTH,
            initial_indent="",
            subsequent_indent=subsequent,
        ).splitlines()
        for idx, line in enumerate(wrapped_hint):
            if idx == 0:
                if is_color_supported():
                    lines.append(f"  {style('Hint:', 'muted')} {style(line[len(h_prefix):], 'light_grey')}")
                else:
                    lines.append(line)
            else:
                if is_color_supported():
                    lines.append(style(line, "light_grey"))
                else:
                    lines.append(line)
    lines.append("")
    return lines


def _section_header(title: str) -> list[str]:
    wrapped = fill(title, width=WIDTH - 4, initial_indent="  ", subsequent_indent="  ").splitlines()
    lines: list[str] = []
    for line in wrapped:
        if is_color_supported():
            lines.append(style(line, "gold", bold=True))
        else:
            lines.append(line)
    underline_len = min(WIDTH - 4, max((len(l) - 2 for l in wrapped), default=len(title)))
    underline = "  " + "-" * underline_len
    if is_color_supported():
        lines.append(style(underline, "brown", dim=True))
    else:
        lines.append(underline)
    return lines


def _wrap_body(text: str, indent: str = "  ") -> list[str]:
    if not text.strip():
        return [""]
    wrapped = fill(
        text.strip(),
        width=WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )
    if is_color_supported():
        return [style(line, "light_grey") for line in wrapped.splitlines()]
    return wrapped.splitlines()


def _wrap_bullet(text: str, label: str = "-", indent: str = "  ") -> list[str]:
    subsequent = indent + " " * (len(label) + 1)
    prefix = f"{indent}{label} "
    wrapped = fill(
        text.strip(),
        width=WIDTH,
        initial_indent=prefix,
        subsequent_indent=subsequent,
    )
    lines = wrapped.splitlines()
    if not is_color_supported() or not lines:
        return lines
    styled_lines: list[str] = []
    first = lines[0]
    styled_lines.append(
        f"{indent}{style(label, 'gold')} {style(first[len(prefix):], 'light_grey')}"
    )
    for line in lines[1:]:
        styled_lines.append(style(line, "light_grey"))
    return styled_lines


def _wrap_key_value(key: str, val: str, indent: str = "  ") -> list[str]:
    key_prefix = f"{indent}{key} :"
    sub_indent = indent + "    "
    full_str = f"{key_prefix} {val}"
    wrapped = fill(
        full_str,
        width=WIDTH,
        initial_indent="",
        subsequent_indent=sub_indent,
    ).splitlines()
    res: list[str] = []
    for idx, line in enumerate(wrapped):
        if idx == 0:
            if is_color_supported() and " :" in line:
                k_part, rest = line.split(" :", 1)
                res.append(f"{style(k_part, 'gold')} {style(':', 'muted')}{style(rest, 'light_grey')}")
            elif is_color_supported():
                res.append(style(line, "light_grey"))
            else:
                res.append(line)
        else:
            if is_color_supported():
                res.append(style(line, "light_grey"))
            else:
                res.append(line)
    return res


def _menu_line(key: str, label: str, desc: str | None = None, indent: str = "  ") -> list[str]:
    key_badge = f"[{key}]"
    prefix = f"{indent}{key_badge} "
    subsequent = " " * len(prefix)
    wrapped_label = fill(
        label,
        width=WIDTH,
        initial_indent=prefix,
        subsequent_indent=subsequent,
    ).splitlines()
    res: list[str] = []
    for idx, line in enumerate(wrapped_label):
        if idx == 0:
            if is_color_supported():
                res.append(f"{indent}{style(key_badge, 'gold', bold=True)} {style(line[len(prefix):], 'amber', bold=True)}")
            else:
                res.append(line)
        else:
            if is_color_supported():
                res.append(style(line, "amber", bold=True))
            else:
                res.append(line)
    if desc:
        sub_indent = indent + "    "
        wrapped_desc = fill(desc, width=WIDTH, initial_indent=sub_indent, subsequent_indent=sub_indent)
        if is_color_supported():
            res.extend(style(line, "muted") for line in wrapped_desc.splitlines())
        else:
            res.extend(wrapped_desc.splitlines())
    return res


# ---------------------------------------------------------------------------
# Categories Definition
# ---------------------------------------------------------------------------

CATEGORIES: list[dict[str, str]] = [
    {
        "id": "getting_started",
        "key": "1",
        "title": "Getting Started with ATLAS",
        "subtitle": "Research problem, auditing objectives & mental model",
        "description": "Introduction to NIDS benchmark dataset flaws, what an audit does, and the epistemic distinction between hypotheses and verified findings.",
    },
    {
        "id": "ways_to_run",
        "key": "2",
        "title": "Ways to Run ATLAS",
        "subtitle": "Execution scopes, comparison & navigation paths",
        "description": "Explains all execution modes exposed by ATLAS: isolated component runs, single-round pipelines, full batches, dataset tools, and zero-execution inspection.",
    },
    {
        "id": "investigation_flow",
        "key": "3",
        "title": "General Investigation Flow",
        "subtitle": "The 7-stage pipeline from raw partition to audit report",
        "description": "Visual ASCII flowchart and detailed stage-by-stage walk through dataset comprehension, hypothesis ranking, worker execution, aggregation, state, and reporting.",
    },
    {
        "id": "components",
        "key": "4",
        "title": "Components: What Each One Does",
        "subtitle": "Catalogue of all 12 active Phase 3A/3B components",
        "description": "Detailed multi-level catalogue covering Semantic Extraction, Analysis, Ranking, Planner, Router, Worker, Aggregation, State Manager, Critic, Auditor, and Reports.",
    },
    {
        "id": "tools",
        "key": "5",
        "title": "Tools: What the Agents Can Actually Use",
        "subtitle": "Catalogue of all 9 active analytical tools",
        "description": "Full reference for the tool registry: feature summary, distribution, cardinality, relations, shortcuts, neighborhood consistency, concentration, duplication, and Wasserstein.",
    },
    {
        "id": "debugging",
        "key": "6",
        "title": "Debugging and Observability",
        "subtitle": "Systematic inspection, 12 diagnostic stages & 14 failure guides",
        "description": "How to inspect runs, step through component diagnostics, identify observability limits, troubleshoot 14 failure types, and trace execution end-to-end.",
    },
    {
        "id": "reports",
        "key": "7",
        "title": "Reports and Persisted Outputs",
        "subtitle": "Round reports, final reports, state history & evaluation",
        "description": "Distinguishes single-round Round Reports, full-batch Final Reports, technical auditor contracts, manifests, canonical state revisions, and formal thesis evaluation.",
    },
]

CATEGORY_MAP: dict[str, dict[str, str]] = {c["id"]: c for c in CATEGORIES}
CATEGORY_KEYS: list[str] = [c["id"] for c in CATEGORIES]


# ---------------------------------------------------------------------------
# Section 1: Getting Started with ATLAS
# Grounded in Thesis methodology.tex (lines 15-92, 145-246)
# ---------------------------------------------------------------------------

GETTING_STARTED_TOPICS: list[dict[str, Any]] = [
    {
        "id": "nids_problem",
        "title": "The NIDS Benchmark Problem & What ATLAS Does",
        "subtitle": "Why benchmark intrusion datasets contain subtle flaws",
        "level1_orientation": [
            "Modern Network Intrusion Detection Systems (NIDS) rely on benchmark datasets like CIC-IDS2017 or UNSW-NB15 to evaluate machine learning detection models. Researchers expect these benchmarks to reflect realistic network traffic conditions.",
            "",
            "However, creating large-scale labeled network datasets is notoriously difficult. During testbed recording, traffic generation, label assignment, and feature extraction, subtle unintentional design flaws are frequently introduced. These include artificial feature separability, label leakage, identical record duplication, and unvarying testbed parameters.",
            "",
            "Machine learning models exploit these flaws as predictive shortcuts. A model can achieve 99.8% test accuracy by memorizing an incidental source port or an unvarying timestamp counter rather than learning genuine attack behavior. When deployed in live enterprise networks, these models suffer catastrophic failure.",
            "",
            "ATLAS (Agent-Based Dataset Auditing Framework) was created to solve this problem. It acts as an autonomous empirical cartographer: exploring network benchmark datasets to discover, verify, and document structural flaws before models are trained on them.",
        ],
        "level2_operational": [
            "ATLAS approaches a dataset without relying on a rigid, hardcoded checklist of flaws, because the exact nature, combination, and location of dataset bugs are unknown in advance.",
            "",
            "Instead, ATLAS adopts an empirical scientific investigation loop: it surveys dataset metadata, formulates competing investigative hypotheses, plans targeted analyses, collects evidence using specialized statistical tools, and aggregates the results into structured audit reports.",
            "",
            "Where it appears in the interface:",
            "- Welcome screen -> [1] Enter ATLAS launches the research console.",
            "- Welcome screen -> [2] The Concept presents the explorer analogy.",
            "- Welcome screen -> [3] How to Use opens this interactive guide.",
        ],
        "level3_technical": [
            "Theoretical grounding: Thesis methodology.tex (Section 3.1 'Research Methodology' and Section 3.2 'Framework Overview').",
            "Key research questions addressed:",
            "- RQ1: Literature artefact identification through agent-based auditing.",
            "- RQ2: Autonomous hypothesis generation, tool selection, and evidence evaluation.",
            "- RQ3: Cross-dataset generalization across different network traffic benchmarks.",
            "Active architecture: Phase 3A/3B multi-agent architecture. Phase 2 single-agent loop and Judge/JIF subsystems have been decommissioned and archived in Phase3/archive/.",
        ],
    },
    {
        "id": "auditing_objectives",
        "title": "Auditing Objectives & What ATLAS Establishes",
        "subtitle": "Boundaries, evidential standards, and what an audit proves",
        "level1_orientation": [
            "An audit in ATLAS is an empirical investigation into the statistical and structural integrity of a dataset partition. Its objective is to uncover flaws that compromise the validity of downstream machine learning models.",
            "",
            "What ATLAS establishes:",
            "- Identifies specific features exhibiting shortcut opportunities (e.g., single-feature thresholds achieving near-perfect class separation).",
            "- Measures exact record duplication rates and cross-label leakage.",
            "- Characterizes unnatural distributional separability and rigid bounds.",
            "- Documents pairwise dependencies and feature correlation cliques.",
            "- Provides structured confidence ratings and empirical evidence blocks.",
            "",
            "What ATLAS does NOT establish:",
            "- It does NOT claim mathematical proof that an entire dataset is invalid.",
            "- It does NOT alter, re-label, or mutate raw dataset CSV files.",
            "- It does NOT simulate live cyberattacks or penetrate networks.",
            "- It does NOT replace human domain expertise; it delivers an evidence-grounded dossier for researchers to make informed decisions.",
        ],
        "level2_operational": [
            "Every claim in an ATLAS report must be supported by measurable observations generated by analytical tools. Language models in ATLAS are strictly forbidden from fabricating dataset properties out of ungrounded reasoning.",
            "",
            "When an audit runs:",
            "1. Workers execute bounded deterministic tools on the dataset.",
            "2. Tool results are strictly validated against typed schema contracts in Phase3/tools/contracts.py.",
            "3. Contradictions between workers or evidence sources are preserved rather than suppressed.",
            "4. A Critic reviews the exploration trajectory to ensure balanced scrutiny.",
            "5. A Final Batch Auditor checks evidence provenance before report generation.",
        ],
        "level3_technical": [
            "Core principle: Evidence-Based Reasoning (Thesis methodology.tex lines 58-72).",
            "Tool execution contract: tools.contracts.build_tool_result() in Phase3/tools/contracts.py.",
            "Output validation engine: validation_repair_engine in Phase3/validation_repair_engine/engine.py.",
            "Artifact integrity: Every observation stores tool_name, target_feature, sample parameters, and execution timestamp.",
        ],
    },
    {
        "id": "epistemic_hierarchy",
        "title": "The Epistemic Hierarchy: Hypotheses to Conclusions",
        "subtitle": "Distinguishing hypotheses, evidence, findings, and conclusions",
        "level1_orientation": [
            "A critical failure mode in AI-assisted research is confusing an initial guess with a proven fact. ATLAS enforces a strict epistemic hierarchy throughout its architecture to maintain scientific discipline.",
            "",
            "1. Hypothesis: A candidate explanation or exploratory lead formulated to investigate an observed structural pattern. A hypothesis is NEVER a fact. Competing and mutually contradictory hypotheses are deliberately allowed to coexist.",
            "",
            "2. Tool Observation / Evidence: An objective, reproducible numerical measurement produced by a specialized analytical tool on the raw data (e.g., a Gini concentration of 0.82 or a duplication rate of 14.3%).",
            "",
            "3. Finding: A contextual interpretation of evidence evaluated against a specific hypothesis by a worker agent, explicitly documenting whether the evidence supports, weakens, or contradicts the hypothesis.",
            "",
            "4. Audit Conclusion: A synthesized, multi-round consensus committed to canonical state after cross-worker aggregation, state manager review, and critic evaluation.",
        ],
        "level2_operational": [
            "How information transitions through the hierarchy:",
            "- Semantic Extraction produces Substrate Regions & Weak Signals.",
            "- Investigation Analysis turns Substrate into Candidate Hypotheses.",
            "- Hypothesis Ranking selects Top Leads for the current round.",
            "- Planner and Router turn selected Hypotheses into Worker Tasks.",
            "- Worker executes Tools to produce Objective Evidence blocks.",
            "- Aggregation synthesizes Task Evidence into Hypothesis Findings.",
            "- State Manager updates Canonical State with versioned Revisions.",
            "- Final Batch Auditor consolidates State into Audit Conclusions.",
        ],
        "level3_technical": [
            "Schema representations:",
            "- Hypothesis: contracts.py in Phase3/investigation_analysis/contracts.py.",
            "- Tool Result: contracts.py in Phase3/tools/contracts.py.",
            "- Worker Finding: contracts.py in Phase3/worker/contracts.py.",
            "- Canonical State: contracts.py in Phase3/state_manager/contracts.py.",
            "- Audit Report: contracts.py in Phase3/final_batch_report/contracts.py.",
        ],
    },
    {
        "id": "mental_model",
        "title": "Core Concepts & Architecture Mental Model",
        "subtitle": "Partitions, substrates, ReAct loops, canonical state & critic",
        "level1_orientation": [
            "To understand ATLAS without reading tens of thousands of lines of code, keep this 5-concept mental model in mind:",
            "",
            "1. The Partition: Real NIDS datasets have tens of millions of rows. Auditing a monolithic dataset would exhaust LLM context windows and memory. ATLAS divides datasets into independent, auditable partitions (e.g., Friday-WorkingHours-DDoS.csv).",
            "",
            "2. The Semantic Substrate: Before launching expensive agents, ATLAS compresses the partition's metadata into a compact observational substrate, identifying feature groups, class ratios, and initial weak signals.",
            "",
            "3. The ReAct Worker Loop: Worker agents operate under a controlled Reasoning-and-Action cycle with strict step limits. Workers reason, request a tool, observe the measurement, and iteratively build findings.",
            "",
            "4. The Canonical State: The system's persistent, version-controlled memory across rounds. Discoveries from Round 1 persist into Round 2 to prevent redundant exploration and enable iterative hypothesis refinement.",
            "",
            "5. The Critic: An independent meta-agent that monitors the exploration process, warning if workers are over-focusing on familiar features or terminating prematurely.",
        ],
        "level2_operational": [
            "Where these concepts live in the CLI:",
            "- Partition selection: CLI main menu -> [3] Session Config -> Select Dataset.",
            "- Substrate inspection: Components menu -> [1] Semantic Extraction -> [1] Inspect Inputs.",
            "- Worker traces: Batch runtime review -> [5] Browse Worker Tree -> Step Timeline.",
            "- Canonical state: Batch runtime review -> [12] Inspect State Evolution.",
            "- Critic reports: Batch runtime review -> [7] Review Critic Tree.",
        ],
        "level3_technical": [
            "Source implementation roots:",
            "- Partition handling: Phase3/data/loader.py and Phase3/data/dataset_config.py.",
            "- Substrate generation: Phase3/semantic_extraction/runner.py.",
            "- Worker ReAct engine: Phase3/worker/runner.py.",
            "- State versioning: Phase3/state_manager/runner.py (state_v1.json .. state_vN.json).",
            "- Critic evaluation: Phase3/critic/runner.py.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Section 2: Ways to Run ATLAS
# Grounded in Phase3/interface/cli.py and phase3_runtime/
# ---------------------------------------------------------------------------

WAYS_TO_RUN_TOPICS: list[dict[str, Any]] = [
    {
        "id": "scope_comparison",
        "title": "Overview & Comparison of Execution Scopes",
        "subtitle": "Which workflow to choose depending on your research goal",
        "level1_orientation": [
            "ATLAS exposes several distinct execution scopes through its interface. A researcher can run a single isolated component, execute one complete round, run a multi-round batch, or inspect past executions without running any code.",
            "",
            "Execution Scope Comparison Matrix:",
            "",
            "1. Component Run : Isolated execution of 1 agent. Fast unit debugging.",
            "2. Cognitive Chain: Runs Extraction -> Analysis -> Ranking -> Planner.",
            "3. Hypothesis Exec: Runs Router -> Worker -> Aggregation -> State -> Critic.",
            "4. Full Round     : 1 complete end-to-end cycle. Produces Round Report.",
            "5. Full Batch     : Multi-round iterative loop. Produces Final Report.",
            "6. Dataset Infra  : Cross-partition memory extraction & dataset merger.",
            "7. Review / Browse: Zero-execution browsing of historical disk runs.",
        ],
        "level2_operational": [
            "Decision Guide: Which mode should you select?",
            "",
            "- 'I want to audit a partition thoroughly': Choose [4] Run Full Batch.",
            "- 'I want to quickly test the pipeline on a partition': Choose [3] Run Full Round.",
            "- 'I want to test a prompt change on Semantic Extraction': Choose Components -> [1].",
            "- 'I want to see what hypotheses the LLM generates without running tools': Choose [1] Run Cognitive Chain.",
            "- 'I want to merge audits from multiple partition CSVs': Choose Components -> [16] Dataset Merger.",
            "- 'I want to review yesterday's run safely without spending API credits': Choose Batch Runtime -> [L] Review Latest or [V] View Saved Runs.",
        ],
        "level3_technical": [
            "Primary CLI entry points in Phase3/interface/cli.py:",
            "- Batch Runtime Menu: cli._phase3a_runtime_menu() (lines 862-917).",
            "- Components Menu: cli._phase3a_components_menu() (lines 814-861).",
            "- Batch Orchestrator: phase3_runtime.orchestrator.run_phase3a_batch().",
            "- Non-interactive CLI: python -m phase3_runtime.orchestrator --mode full_batch.",
        ],
    },
    {
        "id": "isolated_components",
        "title": "Isolated Component Execution",
        "subtitle": "Granular execution, unit testing & prompt debugging",
        "level1_orientation": [
            "In ATLAS, every major agent and module can be invoked independently from the command line or terminal UI. You do not need to execute the entire batch pipeline just to test or debug one component.",
            "",
            "What executes: Exactly one isolated component (e.g., Planner, Worker, Critic).",
            "What it does NOT execute: Any upstream or downstream pipeline stages.",
            "Main outputs: A component-specific run directory in logs/<component>_runs/ containing input payloads, prompts, raw responses, validated outputs, and runtime metrics.",
        ],
        "level2_operational": [
            "Navigation path through ATLAS terminal:",
            "  Welcome Screen -> [1] Enter ATLAS -> [2] ATLAS Components -> [1..17]",
            "",
            "Workflow when selected:",
            "1. ATLAS checks for required input sources (e.g. an existing Substrate or Hypothesis set).",
            "2. If no prior artifact is selected, it prompts you to run the prerequisite or choose a saved run from disk.",
            "3. The component executes with progress logging.",
            "4. A dedicated Review Screen opens immediately, allowing you to inspect inputs, outputs, validation reports, rendered prompts, raw model responses, and technical execution metrics.",
        ],
        "level3_technical": [
            "Terminal UI handler: cli._phase3a_components_menu() in Phase3/interface/cli.py.",
            "Component review menus: cli._render_<component>_run_review() (lines 4990-5380).",
            "Command-line direct entry points:",
            "- python -m semantic_extraction.cli --dataset <file.csv>",
            "- python -m investigation_analysis.cli --metadata <metadata.json>",
            "- python -m hypothesis_ranking.cli --hypotheses <hypotheses.json>",
            "- python -m planner.cli --hypothesis '<lead summary>'",
            "- python -m router.cli --task-list <tasks.json>",
            "- python -m worker.cli --task <task.json> --context <context.json>",
            "- python -m aggregation.cli --findings <findings_dir/>",
            "- python -m critic.cli --findings <aggregated.json>",
            "- python -m final_batch_auditor.cli --round-results <rounds_dir/>",
        ],
    },
    {
        "id": "full_round",
        "title": "Single-Round Execution ('Run Full Round')",
        "subtitle": "Complete single iteration with immediate Round Report",
        "level1_orientation": [
            "The Single-Round execution runs exactly one complete investigation cycle through all 10 stages: from initial dataset loading down to state management, critic evaluation, and Round Report generation.",
            "",
            "What executes: 1 complete round of the pipeline on the active partition.",
            "Intended for: Fast verification that the entire pipeline works, rapid exploratory scouting of a new dataset, or testing worker tool integration.",
            "What it does NOT execute: Subsequent iterative rounds (rounds 2, 3, etc.).",
            "Main outputs: Round artifacts in logs/phase3a_runtime_runs/, state revision v1->v2, worker traces, and an immediate Round Report in logs/round_report_runs/ rendered directly in the terminal.",
        ],
        "level2_operational": [
            "Navigation path through ATLAS terminal:",
            "  Welcome Screen -> [1] Enter ATLAS -> [1] ATLAS Batch Runtime -> [3] Run Full Round",
            "",
            "Post-run experience:",
            "Upon completion, the Post-Round screen offers:",
            "- [1] See round report: Opens the full 9-section Markdown round report in an in-terminal scrollable text viewer.",
            "- [2] View run summary: Opens the runtime review menu to inspect individual component traces, worker steps, and state changes.",
            "- [B] Back to runtime menu.",
        ],
        "level3_technical": [
            "CLI implementation: cli._full_round_post_run_flow() in Phase3/interface/cli.py (lines 3356-3450).",
            "Report runner: final_batch_report.round_runner.run_round_report() in Phase3/final_batch_report/round_runner.py.",
            "Report output file: logs/round_report_runs/<round_report_run_name>/report.md (and referenced in round_manifest.json).",
            "Round contracts: round_contracts.ROUND_REPORT_SECTIONS in Phase3/final_batch_report/round_contracts.py.",
        ],
    },
    {
        "id": "cognitive_vs_hypothesis",
        "title": "Cognitive Chain vs Hypothesis Execution",
        "subtitle": "Decoupling strategic formulation from operational tool execution",
        "level1_orientation": [
            "ATLAS deliberately decouples the strategic reasoning phase from operational execution. You can run either half of the round independently.",
            "",
            "Run Cognitive Chain:",
            "- Executes: Semantic Extraction -> Investigation Analysis -> Hypothesis Ranking -> Planner.",
            "- Intended for: Inspecting the formulated hypotheses, prioritized leads, and investigation strategies before committing API credits or execution time to tools.",
            "",
            "Run Hypothesis Execution:",
            "- Executes: Router -> Worker Tasks -> Tool Calls -> Aggregation -> State Manager -> Critic.",
            "- Intended for: Taking an established plan and testing different worker configurations, tool budgets, or model backends.",
        ],
        "level2_operational": [
            "Navigation path through ATLAS terminal:",
            "  Welcome Screen -> [1] Enter ATLAS -> [1] ATLAS Batch Runtime ->",
            "    [1] Run Cognitive Chain  (Reasoning only)",
            "    [2] Run Hypothesis Execution  (Execution only)",
            "",
            "What happens:",
            "- Cognitive Chain produces planner_strategies.json and stops.",
            "- Hypothesis Execution consumes the strategy bundle, invokes worker agents, executes tools, updates canonical state, and invokes the critic.",
        ],
        "level3_technical": [
            "Orchestrator methods: Phase3/phase3_runtime/orchestrator.py.",
            "- execute_round() -> executes cognitive formulation and worker tasks.",
            "Persisted artifacts: logs/planner_runs/<run>/ and logs/router_runs/<run>/ (or within batch round manifests).",
        ],
    },
    {
        "id": "full_batch",
        "title": "Multi-Round Batch ('Run Full Batch')",
        "subtitle": "Iterative multi-round convergence & Final Partition Report",
        "level1_orientation": [
            "The Multi-Round Batch is the standard, authoritative research execution mode of ATLAS. It runs an iterative loop over multiple investigation rounds (typically 3 to 5 rounds) until convergence or the round limit is reached.",
            "",
            "Why multi-round matters: A single round can only explore initial leads. In a multi-round batch, findings from Round 1 update the canonical state. Round 2 then formulates deeper hypotheses that test contradictions, explore unvisited features, and follow up on anomalies discovered in Round 1.",
            "",
            "What executes: Multi-round pipeline + Final Batch Auditor + Final Batch Report.",
            "Main outputs: Consolidated Final Partition Report (.md and .json), full batch ledger, state history (v1..vN), round manifests, and critic feedback traces.",
        ],
        "level2_operational": [
            "Navigation path through ATLAS terminal:",
            "  Welcome Screen -> [1] Enter ATLAS -> [1] ATLAS Batch Runtime -> [4] Run Full Batch",
            "",
            "Termination conditions:",
            "- Max rounds reached (configured in Session Config or .env).",
            "- Critic saturation: Critic signals diminishing investigative returns.",
            "- No new hypotheses: All high-priority candidate leads have been audited.",
            "",
            "Post-run experience:",
            "- [1] See full report: View consolidated partition audit report.",
            "- [2] View run summary: Drill down into individual rounds, hypotheses, and worker traces.",
        ],
        "level3_technical": [
            "Orchestrator: Phase3/phase3_runtime/orchestrator.py -> run_phase3a_batch().",
            "CLI post-run flow: cli._full_batch_post_run_flow() in Phase3/interface/cli.py.",
            "Output locations: logs/final_batch_report_runs/<run_name>/report.md and logs/phase3a_runtime_runs/<run_name>/batch_ledger.json.",
            "Batch Auditor: final_batch_auditor.runner.run_final_batch_auditor() in Phase3/final_batch_auditor/runner.py.",
        ],
    },
    {
        "id": "dataset_infra",
        "title": "Multi-Partition & Dataset Infrastructure",
        "subtitle": "Cross-partition synthesis & dataset-level auditing",
        "level1_orientation": [
            "A complete benchmark dataset (like CIC-IDS2017) comprises multiple traffic partitions (e.g., Monday-Benign, Tuesday-BruteForce, Wednesday-DoS, Friday-PortScan).",
            "",
            "While each partition is audited independently to maintain manageable reasoning contexts, research conclusions require a dataset-level synthesis. ATLAS provides Phase 3B dataset infrastructure components to merge partition findings into a unified dataset report.",
        ],
        "level2_operational": [
            "Navigation path through ATLAS terminal:",
            "  Welcome Screen -> [1] Enter ATLAS -> [2] ATLAS Components ->",
            "    [14] Partition Memory Extractor: Compresses partition reports into memories.",
            "    [15] Coverage Builder: Computes cross-partition feature & finding coverage.",
            "    [16] Dataset Merger: Synthesizes partition memories into a dataset report.",
            "    [17] Final Dataset Report: Formats and reviews the dataset-wide audit.",
            "",
            "Automated multi-partition execution:",
            "  python -m dataset_runtime.cli --dataset-path data/CICIDS2017/",
            "This automatically orchestrates sequential partition audits, handles retries, and merges findings into a final dataset report.",
        ],
        "level3_technical": [
            "Dataset runtime orchestrator: Phase3/dataset_runtime/orchestrator.py -> run_full_dataset().",
            "Partition memory extractor: Phase3/partition_memory_extractor/runner.py.",
            "Coverage builder: Phase3/coverage_builder/runner.py.",
            "Dataset merger: Phase3/final_batch_report/runner.py -> run_dataset_merger().",
            "Unit tests: tests/test_dataset_runtime.py and tests/test_final_batch_report.py.",
        ],
    },
    {
        "id": "safe_browsing",
        "title": "Safe Browsing & Historical Run Inspection",
        "subtitle": "100% safe inspection of previous runs with zero mutations",
        "level1_orientation": [
            "You do not need to execute new runs to explore ATLAS. The interface provides comprehensive historical inspection capabilities that load saved runs from disk.",
            "",
            "Browsing historical runs is 100% safe:",
            "- It never executes tools or modifies dataset files.",
            "- It never makes LLM API calls or incurs API charges.",
            "- It never alters configuration or deletes runs.",
            "- You can inspect past reasoning traces, worker steps, and reports at any time.",
        ],
        "level2_operational": [
            "Navigation paths for safe browsing:",
            "- Review latest batch run: Batch Runtime -> [L] Review Latest ATLAS Batch Run.",
            "- Browse all saved batch runs: Batch Runtime -> [V] View Saved ATLAS Batch Runs.",
            "- Browse component runs: Components Menu -> Select Component -> [V] View Saved Runs.",
            "",
            "In the run browser:",
            "- Use [1..N] to select a saved run by timestamp and batch ID.",
            "- Use [C] to change view limit (e.g. view 10, 20 runs).",
            "- Use [B] to return to previous menu.",
        ],
        "level3_technical": [
            "Disk persistence roots:",
            "- Batch runs: Phase3/logs/phase3a_runtime_runs/<run>/ (contains batch_ledger.json, event_stream.jsonl, component_run.json, round_manifests/).",
            "- Component runs: Phase3/logs/<component>_runs/ (e.g., logs/worker_runs/).",
            "Run loader implementation: cli._load_phase3a_runtime_run_context() in Phase3/interface/cli.py.",
            "Run limit controls: cli._generic_change_view_limit() and cli._generic_view_runs_menu().",
        ],
    },
]


# ---------------------------------------------------------------------------
# Section 3: General Investigation Flow
# Grounded in Thesis methodology.tex (Section 3.2, 3.3, 3.4)
# ---------------------------------------------------------------------------

INVESTIGATION_FLOW_TOPICS: list[dict[str, Any]] = [
    {
        "id": "flowchart",
        "title": "End-to-End Investigation Architecture Flowchart",
        "subtitle": "Visual diagram of the 7-stage ATLAS auditing pipeline",
        "level1_orientation": [
            "The ATLAS investigation process follows a disciplined 7-stage pipeline. The diagram below illustrates how raw dataset flows are progressively transformed into structured audit conclusions:",
            "",
            "  +-------------------------------------------------------------+",
            "  |                   Dataset Partition (CSV)                  |",
            "  +-------------------------------------------------------------+",
            "                                 |",
            "                                 v",
            "  +-------------------------------------------------------------+",
            "  | 1. UNDERSTAND: Semantic Extraction (Substrate & Signals)   |",
            "  +-------------------------------------------------------------+",
            "                                 |",
            "                                 v",
            "  +-------------------------------------------------------------+",
            "  | 2. FORMULATE: Investigation Analysis & Hypothesis Ranking  |",
            "  +-------------------------------------------------------------+",
            "                                 |",
            "                                 v",
            "  +-------------------------------------------------------------+",
            "  | 3. PLAN & ROUTE: Planner Strategies & Bounded Worker Tasks  |",
            "  +-------------------------------------------------------------+",
            "                                 |",
            "                                 v",
            "  +-------------------------------------------------------------+",
            "  | 4. EXECUTE & OBSERVE: Worker ReAct Loop & Analytical Tools  |",
            "  +-------------------------------------------------------------+",
            "                                 |",
            "                                 v",
            "  +-------------------------------------------------------------+",
            "  | 5. AGGREGATE & EVOLVE: Hypothesis Aggregation & State Mgr   |",
            "  +-------------------------------------------------------------+",
            "                                 |",
            "                                 v",
            "  +-------------------------------------------------------------+",
            "  | 6. CRITIQUE & CONVERGE: Critic Feedback & Convergence Loop  |",
            "  +-------------------------------------------------------------+",
            "                                 |",
            "                     [Next Round or Converged]",
            "                                 |",
            "                                 v",
            "  +-------------------------------------------------------------+",
            "  | 7. AUDIT & REPORT: Final Batch Auditor & Report Generator   |",
            "  +-------------------------------------------------------------+",
        ],
        "level2_operational": [
            "Key architectural handoffs:",
            "- Stage 1 to 2: Semantic Substrate JSON is passed to Investigation Analysis.",
            "- Stage 2 to 3: Ranked Hypothesis Set is handed to Top Hypothesis Planner.",
            "- Stage 3 to 4: Planner Strategies are decomposed by Router into Worker Tasks.",
            "- Stage 4 to 5: Worker Results with Tool Observations are sent to Aggregation.",
            "- Stage 5 to 6: Aggregated Handoff updates Canonical State v(N) -> v(N+1).",
            "- Stage 6 loop: Critic emits advisory feedback for Round N+1.",
            "- Final Stage: Final Batch Auditor verifies state provenance and generates reports.",
        ],
        "level3_technical": [
            "Pipeline coordinator: Phase3/phase3_runtime/orchestrator.py -> execute_round().",
            "Handoff contracts: Every stage communicates using strict, immutable JSON-serializable dataclasses and schema contracts located in each component's contracts.py.",
            "Event tracking: Every handoff emits an event to logs/phase3a_runtime_runs/<run_name>/event_stream.jsonl.",
        ],
    },
    {
        "id": "stage1_understand",
        "title": "Stage 1: Understand the Dataset (Semantic Extraction)",
        "subtitle": "Compressing millions of raw flows into an observational substrate",
        "level1_orientation": [
            "Why this stage exists: Directly feeding millions of raw network flows into language models would instantly exhaust context windows, cost thousands of dollars, and produce superficial reasoning.",
            "",
            "What it does: Transforms the raw partition CSV into a structured, compressed semantic substrate. It extracts deterministic metadata (column types, row count, null rates, cardinality, class balance) and uses an LLM to identify high-level structural regions and preserved weak signals.",
            "",
            "What would be missing without it: Agents would have no map of the territory and would be forced to guess blindly which features exist.",
        ],
        "level2_operational": [
            "Inputs: Partition CSV file path + optional dataset metadata profile.",
            "Processing: Deterministic pandas metadata extraction + LLM semantic compression.",
            "Outputs: semantic_substrate.json containing compressed regions, feature classifications (numeric, identifier, categorical), and preserved weak signals.",
            "Downstream consumer: Stage 2 (Investigation Analysis).",
            "Prompt design: Semantic extraction prompt instructs the model to act as a data cartographer, highlighting unusual distributions, potential identifier leakage, and zero-variance regions.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/semantic_extraction/runner.py -> run_semantic_extraction().",
            "Prompt builder: Phase3/semantic_extraction/prompt_builder.py.",
            "Validator: Phase3/semantic_extraction/validator.py -> validate_semantic_extraction_output().",
            "Schema: contracts.SCHEMA_VERSION = 'phase3a.semantic_extraction.v1'.",
            "CLI Route: ATLAS Components -> [1] Semantic Extraction.",
        ],
    },
    {
        "id": "stage2_formulate",
        "title": "Stage 2: Form & Rank Hypotheses (Analysis & Prioritization)",
        "subtitle": "Turning structural patterns into prioritized investigative leads",
        "level1_orientation": [
            "Why this stage exists: Observing an anomaly (e.g. 'Feature X has identical values in 80% of rows') is not yet a hypothesis. An audit needs explanatory theories: does this indicate unvarying testbed setup, label leakage, or flow timeout artifacts?",
            "",
            "What it does:",
            "- Investigation Analysis generates competing, testable hypotheses explaining observed substrate patterns. It preserves uncertainty and intentionally creates rival theories.",
            "- Hypothesis Ranking scores and prioritizes candidate leads based on expected impact, novelty, and unexplored coverage to determine which leads get the current round's budget.",
        ],
        "level2_operational": [
            "Inputs: semantic_substrate.json + previous round state (if in Round > 1).",
            "Outputs:",
            "- investigation_hypotheses.json: full pool of candidate hypotheses.",
            "- ranking_decision.json: selected hypothesis IDs + deferred IDs with rationale.",
            "Downstream consumer: Stage 3 (Planner).",
            "LLM reasoning: Prompt asks the model to evaluate investigative value, not to declare truth. Hypotheses with high potential security impact are ranked higher.",
        ],
        "level3_technical": [
            "Analysis source: Phase3/investigation_analysis/runner.py -> run_investigation_analysis().",
            "Ranking source: Phase3/hypothesis_ranking/runner.py -> run_hypothesis_ranking().",
            "Ranking schema: contracts.SCHEMA_VERSION = 'phase3a.hypothesis_ranking.v1'.",
            "CLI Routes: ATLAS Components -> [2] Investigation Analysis and [3] Hypothesis Ranking.",
        ],
    },
    {
        "id": "stage3_plan_route",
        "title": "Stage 3: Plan & Route Investigations (Planner & Router)",
        "subtitle": "Decomposing strategic goals into bounded, disciplined tasks",
        "level1_orientation": [
            "Why this stage exists: High-level hypotheses (e.g. 'Feature Y provides an artificial shortcut for PortScan detection') are too broad for a single worker to execute without wandering off-topic.",
            "",
            "What it does:",
            "- Planner defines the strategic objective: what questions must be answered, and what evidence would strengthen or weaken confidence in the hypothesis.",
            "- Router decomposes the strategy into small, bounded Worker Tasks. It enforces scope discipline by assigning explicit allowed action classes and local context references.",
        ],
        "level2_operational": [
            "Inputs: Selected hypothesis record from Ranking.",
            "Outputs:",
            "- planner_strategies.json: strategic goals, confirmation criteria, falsification criteria.",
            "- router_tasks.json: list of bounded worker task specifications.",
            "Downstream consumer: Stage 4 (Worker Agents).",
            "Scope enforcement: The Router strictly limits each worker to 1-3 allowed action classes (e.g. shortcut_verification, distribution_verification) to prevent context drift.",
        ],
        "level3_technical": [
            "Planner source: Phase3/planner/runner.py -> run_planner().",
            "Router source: Phase3/router/runner.py -> run_router().",
            "Router schema: contracts.SCHEMA_VERSION = 'phase3a.router.v1'.",
            "CLI Routes: ATLAS Components -> [4] Planner and [5] Router.",
        ],
    },
    {
        "id": "stage4_execute",
        "title": "Stage 4: Worker ReAct Execution & Tool Evidence",
        "subtitle": "Controlled ReAct reasoning-action loops with analytical tools",
        "level1_orientation": [
            "Why this stage exists: This is where empirical rubber meets the road. Workers do not guess or rely on language model intuition; they perform concrete statistical calculations on the dataset partition.",
            "",
            "What it does: Each worker executes its assigned task using a staged ReAct protocol. The worker reasons about the question, selects an allowed action class, the execution adapter maps it to a registered analytical tool, the tool executes deterministically on the data, and the worker observes the empirical result.",
        ],
        "level2_operational": [
            "Inputs: worker_task.json + local_context_bundle.json + partition dataset path.",
            "Processing: Interleaved reasoning and action steps (bootstrap -> strategy -> tool acquisition -> interpretation -> review -> synthesis).",
            "Outputs: worker_result.json containing concrete findings, empirical evidence references, contradictions, and stated limitations.",
            "Downstream consumer: Stage 5 (Aggregation).",
            "Tool mapping: The worker outputs an action class (e.g. shortcut_verification); execution_adapter.py maps this to the tool shortcut_analysis.",
        ],
        "level3_technical": [
            "Worker engine: Phase3/worker/runner.py -> run_worker().",
            "Execution adapter: Phase3/worker/execution_adapter.py -> build_action_tool_map().",
            "Tool execution: Phase3/tools/execution.py -> execute_tool_call().",
            "Tests: tests/test_worker_prompt_redesign.py.",
            "CLI Route: ATLAS Components -> [6] Worker.",
        ],
    },
    {
        "id": "stage5_aggregate",
        "title": "Stage 5: Evidence Aggregation & State Evolution",
        "subtitle": "Synthesizing worker findings and evolving canonical state",
        "level1_orientation": [
            "Why this stage exists: Individual workers produce localized task results. A single task finding is not yet a comprehensive assessment of the hypothesis. Furthermore, discoveries must persist across rounds.",
            "",
            "What it does:",
            "- Aggregation consolidates findings across all workers assigned to a hypothesis. It detects evidence convergence and explicitly preserves contradictions.",
            "- State Manager evaluates the aggregated handoff against existing canonical state and performs a conservative, append-oriented state update (v1 -> v2).",
        ],
        "level2_operational": [
            "Inputs: List of worker_result.json files + previous canonical state.",
            "Outputs:",
            "- aggregation_handoff.json: consolidated hypothesis assessment.",
            "- updated_state.json: new canonical state revision (state_v(N).json).",
            "Downstream consumers: Stage 6 (Critic) and subsequent round planners.",
            "Conservation rule: State Manager never discards prior findings unless explicit contradiction resolution is provided. History is append-oriented.",
        ],
        "level3_technical": [
            "Aggregation source: Phase3/aggregation/runner.py -> run_aggregation().",
            "State manager source: Phase3/state_manager/runner.py -> run_state_manager().",
            "State persistence: Phase3/logs/state_manager_runs/<run>/updated_batch_state.json and phase3a_runtime_runs/<run>/round_manifests/.",
            "Tests: tests/test_state_manager_status_transitions.py.",
            "CLI Routes: ATLAS Components -> [7] Aggregation and [8] State Manager.",
        ],
    },
    {
        "id": "stage6_critique",
        "title": "Stage 6: Critic Review & Convergence Monitoring",
        "subtitle": "Process-level meta-evaluation and premature convergence checks",
        "level1_orientation": [
            "Why this stage exists: Agentic systems can easily fall into rut behavior -- repeatedly auditing the same prominent features while leaving large areas of the dataset unexplored, or declaring an audit finished too early.",
            "",
            "What it does: The Critic evaluates the investigation process itself. It examines exploration diversity, feature coverage, whether worker findings are diminishing in informational return, and whether unresolved contradictions remain. It issues guidance notes for the next round.",
        ],
        "level2_operational": [
            "Inputs: Complete round execution history + canonical state + previous critic notes.",
            "Outputs: critic_evaluation.json containing trajectory assessment, warnings, and recommendations.",
            "Downstream consumer: Round N+1 Hypothesis Ranking and Planning.",
            "Architectural safeguard: The Critic is strictly an advisory meta-agent. It CANNOT modify canonical state, delete findings, or forge evidence. During the final round, the Critic is disabled.",
        ],
        "level3_technical": [
            "Critic source: Phase3/critic/runner.py -> run_critic().",
            "Critic prompt: Phase3/critic/prompt_builder.py.",
            "Validator: Phase3/critic/validator.py.",
            "Schema: contracts.SCHEMA_VERSION = 'phase3a.critic.v1'.",
            "CLI Route: ATLAS Components -> [9] Critic.",
        ],
    },
    {
        "id": "stage7_reporting",
        "title": "Stage 7: Synthesis & Audit Reporting",
        "subtitle": "Final Batch Auditor verification and human-readable audit reports",
        "level1_orientation": [
            "Why this stage exists: The raw canonical state and batch ledgers are complex JSON files. Human researchers and security practitioners need authoritative, readable audit dossiers explaining the findings, risks, and recommendations.",
            "",
            "What it does:",
            "- Final Batch Auditor performs a technical audit of the batch: verifies evidence provenance, strips internal IDs, and constructs the authoritative Finding Inventory.",
            "- Report Generator converts verified audit state into structured Markdown reports (single-round Round Report or full-batch Final Partition Report).",
        ],
        "level2_operational": [
            "Inputs: Final canonical batch state + round manifests + partition context.",
            "Outputs:",
            "- debugging_audit_report.json: Technical audit contract with validated finding inventory.",
            "- logs/final_batch_report_runs/<run>/report.md: Complete human-readable partition audit dossier.",
            "- logs/round_report_runs/<run>/report.md: Scoped single-round executive report.",
            "Regeneration: Reports can be regenerated at any time from saved state without rerunning analytical tools.",
        ],
        "level3_technical": [
            "Auditor source: Phase3/final_batch_auditor/runner.py -> run_final_batch_auditor().",
            "Batch report runner: Phase3/final_batch_report/runner.py -> run_final_batch_report().",
            "Round report runner: Phase3/final_batch_report/round_runner.py -> run_round_report().",
            "Tests: tests/test_final_batch_report.py.",
            "CLI Routes: ATLAS Components -> [10] Final Batch Auditor and [13] Final Batch Report.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Section 4: Components: What Each One Does
# Grounded in Phase3 component implementations and Thesis methodology.tex
# ---------------------------------------------------------------------------

COMPONENTS_CATALOGUE: list[dict[str, Any]] = [
    {
        "id": "semantic_extraction",
        "name": "Semantic Extraction",
        "role": "Perception & Dataset Cartography",
        "subsystem": "Analysis & Hypothesis Generation",
        "level1_orientation": [
            "What it does: Acts as the perception layer of ATLAS. It transforms raw network flow CSV data into a compact, structured semantic substrate. It extracts deterministic distribution statistics, identifies identifier columns, characterizes class balance, and highlights initial weak signals.",
            "",
            "Why the architecture needs it: Directly presenting millions of raw tabular records to language models causes severe context window bloat, extreme latency, and unfocused reasoning. Semantic Extraction creates a high-level topographical map of the partition.",
            "",
            "Where it sits: Stage 1. It is the very first component executed when a partition is loaded.",
            "",
            "What would be missing without it: Later agents would have no structured understanding of available features, ranges, missing value rates, or potential label leakage points.",
        ],
        "level2_operational": [
            "Inputs: Raw dataset partition CSV file and optional DatasetConfig profile.",
            "Processing: Deterministic Pandas summary statistics + LLM-based semantic compression.",
            "Outputs: semantic_substrate.json containing compressed regions, preserved weak signals, and feature schema definitions.",
            "Downstream consumer: Investigation Analysis consumes the substrate to generate hypotheses.",
            "Prompt & Execution Design:",
            "- LLM-powered: Yes, using prompt assembled via build_semantic_extraction_prompt().",
            "- Context injected: Column summary dictionary, shape, class label distributions.",
            "- Output format: Strict JSON object containing 'compressed_regions' and 'preserved_weak_signals'.",
            "- Validation: Strict validator in validator.py checks region structures, signal schemas, and rejects hallucinations.",
            "- Fallback: If JSON is malformed, the validation repair engine attempts targeted syntax repairs.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/semantic_extraction/runner.py -> run_semantic_extraction()",
            "Prompt builder: Phase3/semantic_extraction/prompt_builder.py -> build_semantic_extraction_prompt()",
            "Validator: Phase3/semantic_extraction/validator.py -> validate_semantic_extraction_output()",
            "Schema version: 'phase3a.semantic_extraction.v1'",
            "Unit tests: tests/test_semantic_extraction_prompt_contract.py",
            "Persisted artifacts: logs/semantic_extraction_runs/<run>/semantic_substrate.json, component_run.json",
            "CLI Review route: ATLAS Components -> [1] Semantic Extraction -> [1..5] to inspect inputs, substrate, validation, prompt/response, or technical details.",
            "Observability limitation: The static prompt template is stored in Python code; the CLI shows the fully rendered prompt with inserted data.",
        ],
    },
    {
        "id": "investigation_analysis",
        "name": "Investigation Analysis",
        "role": "Exploratory Hypothesis Generation",
        "subsystem": "Analysis & Hypothesis Generation",
        "level1_orientation": [
            "What it does: Translates observable statistical patterns and weak signals from the substrate into a pool of investigable hypotheses. It generates candidate explanations for why specific features behave anomalously.",
            "",
            "Why the architecture needs it: The auditing system must not jump from an observation directly to an assumption of flaw. It must generate competing, testable hypotheses that preserve uncertainty and define specific questions to investigate.",
            "",
            "Where it sits: Stage 2. Follows Semantic Extraction and precedes Hypothesis Ranking.",
            "",
            "What would be missing without it: The system would have no explicit theories to test and could only run blind, brute-force statistical checks without research direction.",
        ],
        "level2_operational": [
            "Inputs: semantic_substrate.json + partition metadata + optional prior round state.",
            "Processing: LLM-based abductive reasoning over structural regions and anomalies.",
            "Outputs: investigation_hypotheses.json containing a list of structured hypothesis objects.",
            "Downstream consumer: Hypothesis Ranking evaluates and prioritizes this pool.",
            "Prompt & Execution Design:",
            "- LLM-powered: Yes, using prompt assembled via build_investigation_analysis_prompt().",
            "- Prompt context: Substrate regions, weak signals, attack scenario context.",
            "- Model task: Generate 3-8 distinct hypotheses spanning different potential flaw types.",
            "- Validation: Checks that each hypothesis has an ID, description, target features, rationale, and open questions.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/investigation_analysis/runner.py -> run_investigation_analysis()",
            "Prompt builder: Phase3/investigation_analysis/prompt_builder.py -> build_investigation_analysis_prompt()",
            "Validator: Phase3/investigation_analysis/validator.py -> validate_investigation_analysis_output()",
            "Schema version: 'phase3a.investigation_analysis.v1'",
            "Persisted artifacts: logs/investigation_analysis_runs/<run>/investigation_hypotheses.json",
            "CLI Review route: ATLAS Components -> [2] Investigation Analysis -> Review Screen.",
            "Observability limitation: Hypothesis clustering logic is deterministic in runner.py; intermediate reasoning before JSON emission is captured only in raw_response_text.",
        ],
    },
    {
        "id": "hypothesis_ranking",
        "name": "Hypothesis Ranking",
        "role": "Resource Allocation & Prioritization",
        "subsystem": "Analysis & Hypothesis Generation",
        "level1_orientation": [
            "What it does: Evaluates the candidate hypothesis pool and selects the highest-priority leads for investigation in the current round. It balances the pursuit of high-impact risks with exploration of unvisited features.",
            "",
            "Why the architecture needs it: Investigating every hypothesis simultaneously would be computationally expensive and dilute investigative effort. Ranking allocates the limited investigation budget to leads with the highest informational value.",
            "",
            "Where it sits: Stage 3. Sits between Hypothesis Generation and Planning.",
            "",
            "What would be missing without it: Workers would waste resources investigating trivial statistical quirks while critical shortcut-learning vulnerabilities were neglected.",
        ],
        "level2_operational": [
            "Inputs: investigation_hypotheses.json + round budget limit + historical coverage matrix.",
            "Processing: Multi-factor scoring (impact, uncertainty, novelty, coverage gaps).",
            "Outputs: ranking_decision.json containing selected_hypothesis_ids and deferred_hypothesis_ids with rationale.",
            "Downstream consumer: Planner generates investigation strategies for the selected hypotheses.",
            "Prompt & Execution Design:",
            "- LLM-powered: Yes, using prompt assembled via build_hypothesis_ranking_prompt().",
            "- Validation: Confirms all selected IDs exist in the input set and respect the round budget.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/hypothesis_ranking/runner.py -> run_hypothesis_ranking()",
            "Prompt builder: Phase3/hypothesis_ranking/prompt_builder.py -> build_hypothesis_ranking_prompt()",
            "Validator: Phase3/hypothesis_ranking/validator.py -> validate_hypothesis_ranking_output()",
            "Schema version: 'phase3a.hypothesis_ranking.v1'",
            "Persisted artifacts: logs/hypothesis_ranking_runs/<run>/ranking_decision.json",
            "CLI Review route: ATLAS Components -> [3] Hypothesis Ranking -> Review Screen.",
        ],
    },
    {
        "id": "planner",
        "name": "Planner",
        "role": "Strategic Investigation Design",
        "subsystem": "Planning & Execution",
        "level1_orientation": [
            "What it does: Translates each selected hypothesis into a structured, bounded investigation strategy. It defines what questions must be answered and what evidence would confirm or challenge the hypothesis.",
            "",
            "Why the architecture needs it: A hypothesis states what might be true; a plan states how to test it. The Planner prevents confirmation bias by explicitly demanding both strengthening and weakening evidence criteria.",
            "",
            "Where it sits: Stage 4. Bridges high-level hypothesis selection with low-level worker routing.",
            "",
            "What would be missing without it: Workers would have no clear testing criteria and would be prone to confirmation bias, seeking only data that agrees with the hypothesis.",
        ],
        "level2_operational": [
            "Inputs: Selected hypothesis object + partition context + available tool capabilities.",
            "Processing: Strategic decomposition into verification objectives and falsification criteria.",
            "Outputs: planner_strategies.json containing structured strategy bundles.",
            "Downstream consumer: Router decomposes strategies into concrete worker tasks.",
            "Prompt & Execution Design:",
            "- LLM-powered: Yes, using prompt assembled via build_planner_prompt().",
            "- Prompt instructions: Require explicit falsification criteria alongside confirmation goals.",
            "- Validation: Ensures strategy maintains strict boundary constraints and references valid features.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/planner/runner.py -> run_planner()",
            "Prompt builder: Phase3/planner/prompt_builder.py -> build_planner_prompt()",
            "Validator: Phase3/planner/validator.py -> validate_planner_output()",
            "Schema version: 'phase3a.planner.v1'",
            "Persisted artifacts: logs/planner_runs/<run>/planner_strategies.json",
            "CLI Review route: ATLAS Components -> [4] Planner -> Review Screen.",
        ],
    },
    {
        "id": "router",
        "name": "Router",
        "role": "Task Decomposition & Governance",
        "subsystem": "Planning & Execution",
        "level1_orientation": [
            "What it does: Breaks down a broad investigation strategy into 1 to 4 localized, bounded Worker Tasks. It acts as the governance layer of the investigation.",
            "",
            "Why the architecture needs it: Worker agents must operate within strict boundaries. The Router enforces investigation discipline by assigning each task a localized scope, explicit allowed action classes, and termination criteria.",
            "",
            "Where it sits: Stage 5. Sits between the Planner and Worker execution.",
            "",
            "What would be missing without it: Unbounded workers would wander across arbitrary features, execute expensive tools indiscriminately, and create incoherent finding logs.",
        ],
        "level2_operational": [
            "Inputs: planner_strategies.json + tool capability records.",
            "Processing: Task decomposition, scope isolation, and action class binding.",
            "Outputs: router_tasks.json containing an array of bounded worker task specifications.",
            "Downstream consumer: Worker agents execute each task independently.",
            "Action Class Mapping:",
            "- The Router assigns abstract action classes (e.g. 'shortcut_verification', 'distribution_verification').",
            "- Workers do NOT select arbitrary Python functions; they request actions authorized by the Router.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/router/runner.py -> run_router()",
            "Prompt builder: Phase3/router/prompt_builder.py -> build_router_prompt()",
            "Validator: Phase3/router/validator.py -> validate_router_output()",
            "Schema version: 'phase3a.router.v1'",
            "Persisted artifacts: logs/router_runs/<run>/router_tasks.json",
            "CLI Review route: ATLAS Components -> [5] Router -> Review Screen.",
        ],
    },
    {
        "id": "worker",
        "name": "Worker Agent",
        "role": "Empirical ReAct Execution",
        "subsystem": "Planning & Execution",
        "level1_orientation": [
            "What it does: The primary investigative engine of ATLAS. The Worker executes a bounded task using a staged ReAct (Reasoning + Acting) loop: it reasons about the objective, invokes analytical tools on the data, evaluates observations, and synthesizes findings.",
            "",
            "Why the architecture needs it: The Worker grounds all auditing in empirical reality. It does not fabricate claims; every finding it reports is tied directly to a tool execution on the raw CSV data.",
            "",
            "Where it sits: Stage 6. The core execution phase of every round.",
            "",
            "What would be missing without it: ATLAS would be a pure hallucination engine generating ungrounded commentary without statistical backing.",
        ],
        "level2_operational": [
            "Inputs: worker_task.json + local_context_bundle.json + partition dataset path.",
            "Processing: Controlled ReAct loop with up to 8-10 steps. Stages: bootstrap -> strategy refinement -> tool execution -> interpretation -> review -> final verification -> synthesis.",
            "Outputs: worker_result.json (findings, evidence blocks, contradictions, limitations) + tool_events.jsonl.",
            "Downstream consumer: Aggregation consolidates findings across workers.",
            "Execution Adapter:",
            "- Worker requests an allowed action class (e.g. 'cardinality_verification').",
            "- execution_adapter.py maps this to tools.cardinality_analysis.cardinality_analysis.",
            "- Tool executes deterministically and returns structured numerical observations.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/worker/runner.py -> run_worker()",
            "Prompt builder: Phase3/worker/prompt_builder.py -> build_worker_prompt()",
            "Execution adapter: Phase3/worker/execution_adapter.py -> build_action_tool_map()",
            "Validator: Phase3/worker/validator.py -> validate_worker_output()",
            "Schema version: 'phase3a.worker.v1'",
            "Unit tests: tests/test_worker_prompt_redesign.py",
            "Persisted artifacts: logs/worker_runs/<run>/worker_result.json, tool_events.jsonl, step_*.json",
            "CLI Review route: ATLAS Components -> [6] Worker -> Inspect Task, Step Timeline, Tool Events, Prompts.",
        ],
    },
    {
        "id": "aggregation",
        "name": "Aggregation",
        "role": "Evidence Synthesis & Contradiction Detection",
        "subsystem": "State & Reasoning",
        "level1_orientation": [
            "What it does: Synthesizes the results produced by multiple worker agents investigating the same hypothesis. It detects evidence convergence, combines complementary observations, and identifies unresolved contradictions.",
            "",
            "Why the architecture needs it: Individual workers only see their assigned subtasks. Aggregation provides the hypothesis-level synthesis, ensuring that contradictory evidence is explicitly preserved rather than ignored.",
            "",
            "Where it sits: Stage 7. Follows worker execution and precedes State Management.",
            "",
            "What would be missing without it: Multiple worker findings would remain disjointed, and conflicting evidence between workers would never be detected or resolved.",
        ],
        "level2_operational": [
            "Inputs: List of worker_result.json files for a given hypothesis.",
            "Processing: Cross-worker evidence synthesis, convergence evaluation, contradiction extraction.",
            "Outputs: aggregation_handoff.json containing consolidated findings and open gaps.",
            "Downstream consumer: State Manager evaluates the handoff to update canonical state.",
            "Prompt & Execution Design:",
            "- LLM-powered: Yes, using prompt assembled via build_aggregation_prompt().",
            "- Key rule: Must never average away contradictions. If Worker A finds low cardinality and Worker B finds strong separation, both must be preserved.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/aggregation/runner.py -> run_aggregation()",
            "Prompt builder: Phase3/aggregation/prompt_builder.py -> build_aggregation_prompt()",
            "Validator: Phase3/aggregation/validator.py -> validate_aggregation_output()",
            "Schema version: 'phase3a.aggregation.v1'",
            "Persisted artifacts: logs/aggregation_runs/<run>/aggregation_handoff.json",
            "CLI Review route: ATLAS Components -> [7] Aggregation -> Review Screen.",
        ],
    },
    {
        "id": "state_manager",
        "name": "State Manager",
        "role": "Canonical Memory & State Evolution",
        "subsystem": "State & Reasoning",
        "level1_orientation": [
            "What it does: Maintains the persistent, versioned interpretive memory of the audit. It receives aggregation handoffs and performs a conservative, append-oriented update of canonical state (e.g. v1 -> v2).",
            "",
            "Why the architecture needs it: An iterative audit must remember what it has already discovered. The State Manager ensures that knowledge accumulates across rounds without erasing prior evidence or losing traceability.",
            "",
            "Where it sits: Stage 8. The persistence anchor between successive investigation rounds.",
            "",
            "What would be missing without it: Every round would start from scratch with amnesia, repeatedly rediscovering the same initial anomalies.",
        ],
        "level2_operational": [
            "Inputs: aggregation_handoff.json + prior canonical state (state_v(N).json).",
            "Processing: Deterministic state transition rules + status evolution (e.g. unverified -> investigated -> confirmed/refuted).",
            "Outputs: updated_state.json committed as state_v(N+1).json.",
            "Downstream consumers: Critic reviews state evolution; next round's Planner reads current state.",
            "Conservation principle: Prior findings cannot be silently dropped. Any status transition must reference concrete evidence.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/state_manager/runner.py -> run_state_manager()",
            "Validator: Phase3/state_manager/validator.py -> validate_state_manager_output()",
            "State transitions: Phase3/state/state_manager.py",
            "Schema version: 'phase3a.state_manager.v1'",
            "Unit tests: tests/test_state_manager_status_transitions.py",
            "Persisted artifacts: logs/state_manager_runs/<run>/updated_batch_state.json, logs/phase3a_runtime_runs/<run>/round_manifests/",
            "CLI Review route: ATLAS Components -> [8] State Manager -> Prior State, State Delta, Updated State.",
        ],
    },
    {
        "id": "critic",
        "name": "Critic",
        "role": "Process Meta-Evaluation & Guidance",
        "subsystem": "State & Reasoning",
        "level1_orientation": [
            "What it does: Evaluates the investigation process itself. It looks across the entire round's history to assess whether workers are over-concentrating on familiar features, whether returns are diminishing, and whether unexplored areas remain.",
            "",
            "Why the architecture needs it: Autonomous agents easily develop tunnel vision. The Critic acts as an external meta-reviewer, providing advisory recommendations to broaden exploration in subsequent rounds.",
            "",
            "Where it sits: Stage 9. Evaluates the end of each round (except the final round).",
            "",
            "What would be missing without it: The system would risk premature convergence, declaring an audit finished after only checking the easiest superficial anomalies.",
        ],
        "level2_operational": [
            "Inputs: Complete round execution history, canonical state, and previous critic evaluations.",
            "Processing: Trajectory evaluation, search diversity assessment, saturation detection.",
            "Outputs: critic_evaluation.json containing recommendations for the next round's Planner.",
            "Downstream consumer: Round N+1 Hypothesis Ranking and Planning.",
            "Safety guard: The Critic cannot modify canonical state or delete findings. It only emits advisory feedback.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/critic/runner.py -> run_critic()",
            "Prompt builder: Phase3/critic/prompt_builder.py -> build_critic_prompt()",
            "Validator: Phase3/critic/validator.py -> validate_critic_output()",
            "Schema version: 'phase3a.critic.v1'",
            "Persisted artifacts: logs/critic_runs/<run>/critic_evaluation.json",
            "CLI Review route: ATLAS Components -> [9] Critic -> Trajectory Evaluation, Recommendations.",
        ],
    },
    {
        "id": "final_batch_auditor",
        "name": "Final Batch Auditor",
        "role": "Technical Audit & Finding Inventory",
        "subsystem": "Auditing & Reporting",
        "level1_orientation": [
            "What it does: Performs a rigorous technical audit of the entire multi-round execution. It verifies evidence provenance, validates that every finding is grounded in actual tool executions, strips internal IDs, and constructs the authoritative Finding Inventory.",
            "",
            "Why the architecture needs it: Reports presented to security analysts must not contain internal debugging identifiers (like 'hyp_004' or 'task_step_2'). The Auditor normalizes findings into public, reproducible audit records.",
            "",
            "Where it sits: Stage 10. The bridge between raw execution logs and final report generation.",
            "",
            "What would be missing without it: Reports would leak internal execution artifacts, unverified assertions could slip through, and findings would lack standardized reproducibility metadata.",
        ],
        "level2_operational": [
            "Inputs: All round manifests + final canonical state + batch ledger.",
            "Processing: Provenance verification, finding classification (investigated vs uninvestigated), ID sanitization.",
            "Outputs: debugging_audit_report.json containing the authoritative Finding Inventory.",
            "Downstream consumer: Final Batch Report generator.",
        ],
        "level3_technical": [
            "Source implementation: Phase3/final_batch_auditor/runner.py -> run_final_batch_auditor()",
            "Prompt builder: Phase3/final_batch_auditor/prompt_builder.py",
            "Validator: Phase3/final_batch_auditor/validator.py -> validate_final_batch_auditor_output()",
            "Schema version: 'phase3a.final_batch_auditor.v1'",
            "Persisted artifacts: logs/final_batch_auditor_runs/<run>/debugging_audit_report.json (alongside final_audit_input.json, final_state_summary.json, process_signal_summary.json)",
            "CLI Review route: ATLAS Components -> [10] Final Batch Auditor -> Review Screen.",
        ],
    },
    {
        "id": "final_batch_report",
        "name": "Final Batch Report & Round Report",
        "role": "Authoritative Audit Dossier Generation",
        "subsystem": "Auditing & Reporting",
        "level1_orientation": [
            "What it does: Generates the authoritative, human-readable audit dossiers in structured Markdown. It produces both the comprehensive multi-round Final Batch Report and the single-round Round Report.",
            "",
            "Why the architecture needs it: Researchers and practitioners need clear, structured prose explaining what flaws were discovered, what downstream risks they pose, what evidence supports them, and what recommendations apply.",
            "",
            "Where it sits: Stage 11 (Final Stage). The terminal deliverable of an ATLAS investigation.",
            "",
            "What would be missing without it: Users would have to manually parse thousands of lines of JSON logs to understand the results of an audit.",
        ],
        "level2_operational": [
            "Inputs: final_audit.json + partition context profile + canonical state.",
            "Outputs:",
            "- logs/final_batch_report_runs/<run>/report.md (multi-round partition audit dossier).",
            "- logs/round_report_runs/<run>/report.md (single-round audit dossier).",
            "- docs/batch_reports/<partition_name>.md (benchmark partition reference reports).",
            "- final_dataset/final_dataset_report.md (Phase 3B cross-partition merged report).",
            "Regeneration: Reports can be re-synthesized at any time from saved state without re-executing tools.",
            "Section structures: Adheres to strict 8-9 section guidelines including Executive Summary, Evidence, Findings, and Limitations.",
        ],
        "level3_technical": [
            "Batch report runner: Phase3/final_batch_report/runner.py -> run_final_batch_report()",
            "Round report runner: Phase3/final_batch_report/round_runner.py -> run_round_report()",
            "Round report contracts: Phase3/final_batch_report/round_contracts.py (ROUND_REPORT_SECTIONS)",
            "Unit tests: tests/test_final_batch_report.py",
            "CLI Review routes: Post-run menu [1] 'See full report' / 'See round report' or Components -> [13] Final Batch Report.",
        ],
    },
    {
        "id": "dataset_infra",
        "name": "Dataset Infrastructure & Runtime",
        "role": "Multi-Partition Synthesis & Orchestration",
        "subsystem": "Dataset Infrastructure",
        "level1_orientation": [
            "What it does: Manages multi-partition datasets. It orchestrates sequential partition audits, extracts partition memories, computes cross-partition coverage matrices, and merges all partition audits into a unified dataset report.",
            "",
            "Why the architecture needs it: Complete benchmarks (like CIC-IDS2017) consist of multiple partition files. Individual partition reports must be consolidated to determine whether an artefact is an isolated quirk or a dataset-wide flaw.",
            "",
            "Where it sits: Phase 3B cross-partition layer, operating above individual partition batches.",
        ],
        "level2_operational": [
            "Components involved:",
            "- Partition Memory Extractor: Compresses partition reports into structured memories.",
            "- Coverage Builder: Calculates feature and artefact frequency across partitions.",
            "- Dataset Merger: Synthesizes memories into a complete dataset-wide audit report.",
            "- Dataset Runtime: Manages stateful batch execution across all partitions in a directory.",
            "CLI usage: python -m dataset_runtime.cli --dataset-path data/CICIDS2017/",
        ],
        "level3_technical": [
            "Runtime orchestrator: Phase3/dataset_runtime/orchestrator.py -> run_full_dataset()",
            "Partition memory: Phase3/partition_memory_extractor/runner.py",
            "Coverage builder: Phase3/coverage_builder/runner.py",
            "Dataset merger: Phase3/final_batch_report/runner.py -> run_dataset_merger()",
            "Unit tests: tests/test_dataset_runtime.py",
            "CLI Routes: ATLAS Components -> [14] Partition Memory, [15] Coverage Builder, [16] Dataset Merger, [17] Final Dataset Report.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Section 5: Tools: What the Agents Can Actually Use
# Grounded in Phase3/tools/registry.py, contracts.py and Thesis methodology.tex
# ---------------------------------------------------------------------------

TOOLS_CATALOGUE: list[dict[str, Any]] = [
    {
        "tool_name": "feature_summary",
        "display_name": "Feature Summary",
        "epistemic_role": "structural_summary",
        "supported_scopes": ["feature"],
        "level1_orientation": [
            "What it does: Calculates class-conditioned summary statistics for a single numeric feature. It computes mean, standard deviation, min, 25%, median, 75%, max, missing value rate, and zero rate across benign vs attack traffic classes.",
            "",
            "Example question it answers: 'Does this feature exhibit radically different scale, variance, or zero-inflation between benign and malicious flows?'",
            "",
            "When it is useful: Excellent for initial reconnaissance. When a worker is assigned a lead on a feature, feature_summary provides the baseline parameters before launching more specialized tests.",
        ],
        "level2_operational": [
            "Input requirements: feature_name (must exist in partition numeric features).",
            "What it returns: A dictionary of class-conditioned statistical profiles, value ranges, missing counts, and zero percentages.",
            "How to interpret: Shows basic statistical shifts. For instance, if attack traffic has 100% zero values while benign traffic has varied positive integers, that signals strong separability.",
            "Limitations / What it CANNOT prove: Cannot prove shortcut learning on its own. A natural attack signature (e.g. huge packet count in DDoS) will naturally shift mean and variance.",
            "Relationship with Workers: Router assigns action class 'structural_summary'. execution_adapter.py maps this to feature_summary.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/feature_summary.py -> feature_summary()",
            "Registry entry: 'feature_summary' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='structural_summary', supported_scopes=['feature']",
            "Result shape: 'feature_observation' under tools.contracts.build_tool_result()",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'feature_summary'",
        ],
    },
    {
        "tool_name": "distribution_analysis",
        "display_name": "Distribution Analysis",
        "epistemic_role": "distribution_verification",
        "supported_scopes": ["feature"],
        "level1_orientation": [
            "What it does: Analyzes class-conditioned distribution shapes, histogram profiles, skewness, kurtosis, and distributional separability patterns for a numeric feature.",
            "",
            "Example question it answers: 'Do benign and attack classes occupy completely non-overlapping, artificially separated distribution intervals?'",
            "",
            "When it is useful: Essential when evaluating hypotheses of artificial separability, unnatural synthetic generation bounds, or clipped counters.",
        ],
        "level2_operational": [
            "Input requirements: feature_name (single numeric feature).",
            "What it returns: Percentile profiles, skewness, kurtosis, and overlap metrics between classes.",
            "How to interpret: High distributional divergence or zero histogram overlap between classes indicates that the feature completely separates the classes. If the feature represents a testbed parameter (e.g., flow duration artificially capped in simulation), this separation is an artefact.",
            "Limitations: Does not establish whether the separability is legitimate (a real attack behavior) or artificial (a testbed setup flaw). Must be interpreted in domain context.",
            "Relationship with Workers: Router assigns action class 'distribution_verification'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/distribution_analysis.py -> distribution_analysis()",
            "Registry entry: 'distribution_analysis' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='distribution_verification'",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'distribution_analysis'",
        ],
    },
    {
        "tool_name": "cardinality_analysis",
        "display_name": "Cardinality Analysis",
        "epistemic_role": "cardinality_verification",
        "supported_scopes": ["feature"],
        "level1_orientation": [
            "What it does: Evaluates the uniqueness and diversity of values in a feature. It measures distinct value counts, ratio of unique values to row count, near-constant behavior, and discrete value clustering.",
            "",
            "Example question it answers: 'Is this supposedly continuous network counter actually frozen at 1 or 2 discrete constants throughout the entire recording?'",
            "",
            "When it is useful: Key for spotting unvarying testbed parameters, frozen flags, or disabled sensors that offer zero predictive value in live deployments.",
        ],
        "level2_operational": [
            "Input requirements: feature_name (single numeric or categorical feature).",
            "What it returns: distinct_count, cardinality_ratio, top_value_frequency, and near_constant boolean flag.",
            "How to interpret: A feature with cardinality_ratio < 0.0001 or top_value_frequency > 0.99 is effectively constant. If attack flows only exhibit 1 distinct value while benign has 2, a classifier will latch onto this trivial binary flag.",
            "Limitations: Low cardinality is normal for certain legitimate protocol fields (e.g. TCP flags, IP protocol numbers). Domain context must distinguish valid flags from frozen counters.",
            "Relationship with Workers: Router assigns action class 'cardinality_verification'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/cardinality_analysis.py -> cardinality_analysis()",
            "Registry entry: 'cardinality_analysis' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='cardinality_verification'",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'cardinality_analysis'",
        ],
    },
    {
        "tool_name": "feature_relation",
        "display_name": "Feature Relation",
        "epistemic_role": "relation_verification",
        "supported_scopes": ["feature", "feature_pair"],
        "level1_orientation": [
            "What it does: Measures bounded pairwise linear and monotonic relationships (Pearson and Spearman correlation) between two features, without unbounded cross-expansion.",
            "",
            "Example question it answers: 'Is Feature A mathematically identical to or fully redundant with Feature B (correlation > 0.999)?'",
            "",
            "When it is useful: Identifying redundant flow metrics, derived counters that leak information, or synchronized testbed clocks.",
        ],
        "level2_operational": [
            "Input requirements: feature_name + related_feature_name (must both be numeric).",
            "What it returns: pearson_correlation, spearman_correlation, mutual_information_proxy, sample_size.",
            "How to interpret: A Pearson correlation of 1.0 or -1.0 proves exact redundancy (one feature is a linear transformation of the other). High mutual information signals shared information leakage.",
            "Limitations: Only evaluates pairwise relations between two specified features. It never expands beyond two features to prevent combinatorial explosion.",
            "Relationship with Workers: Router assigns action class 'relation_verification'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/feature_relation.py -> feature_relation()",
            "Registry entry: 'feature_relation' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='relation_verification', supported_scopes=['feature', 'feature_pair']",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'feature_relation'",
        ],
    },
    {
        "tool_name": "shortcut_analysis",
        "display_name": "Shortcut Analysis",
        "epistemic_role": "shortcut_verification",
        "supported_scopes": ["feature"],
        "level1_orientation": [
            "What it does: Fits a deterministic single-feature decision stump (optimal single threshold) to measure whether one feature alone can predict the attack label with near-perfect accuracy.",
            "",
            "Example question it answers: 'Can a classifier achieve 99% accuracy by simply checking whether Feature X is greater than 42?'",
            "",
            "When it is useful: The core test for shortcut learning vulnerabilities. Proves whether a single feature provides an unintended back-door for models to bypass learning real attack patterns.",
        ],
        "level2_operational": [
            "Input requirements: feature_name (single numeric feature).",
            "What it returns: optimal_threshold, train_accuracy, validation_accuracy, f1_score, and shortcut_risk_level.",
            "How to interpret: If a decision stump achieves F1 > 0.95 on a feature that has no intrinsic security reason to separate attacks (e.g. flow duration, destination port, inter-arrival time), this constitutes high-confidence evidence of a shortcut learning vulnerability.",
            "Limitations: High decision stump accuracy on an intrinsic attack property (e.g. number of packets in a volumetric flood) may be legitimate rather than an artefact. Context determines severity.",
            "Relationship with Workers: Router assigns action class 'shortcut_verification'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/shortcut_analysis.py -> shortcut_analysis()",
            "Registry entry: 'shortcut_analysis' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='shortcut_verification'",
            "Boundedness note: Uses a deterministic decision stump with strict depth=1 and cross-validation.",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'shortcut_analysis'",
        ],
    },
    {
        "tool_name": "neighborhood_consistency_analysis",
        "display_name": "Neighborhood Consistency",
        "epistemic_role": "local_consistency_verification",
        "supported_scopes": ["feature"],
        "level1_orientation": [
            "What it does: Measures local label topology consistency around a feature's neighborhood using bounded nearest neighbors. It checks whether data points are surrounded exclusively by points with the exact same label.",
            "",
            "Example question it answers: 'Are attack flows artificially clustered into isolated, pure islands with zero natural boundary overlap with normal traffic?'",
            "",
            "When it is useful: Identifying synthetic traffic generation artifacts where attack flows lack realistic protocol variation and boundary noise.",
        ],
        "level2_operational": [
            "Input requirements: feature_name (single numeric feature).",
            "What it returns: mean_neighborhood_purity, boundary_point_ratio, label_clustering_score.",
            "How to interpret: Purity of 1.0 means every attack flow's nearest neighbors are also attack flows, indicating completely artificial clustering with zero boundary ambiguity.",
            "Limitations: Real high-volume attacks (like volumetric UDP floods) can produce legitimate clustering. Requires comparison against baseline benign variability.",
            "Relationship with Workers: Router assigns action class 'local_consistency_verification'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/neighborhood_consistency_analysis.py -> neighborhood_consistency_analysis()",
            "Registry entry: 'neighborhood_consistency_analysis' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='local_consistency_verification'",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'neighborhood_consistency_analysis'",
        ],
    },
    {
        "tool_name": "dependency_concentration_analysis",
        "display_name": "Dependency Concentration",
        "epistemic_role": "dependency_contextualization",
        "supported_scopes": ["feature"],
        "level1_orientation": [
            "What it does: Evaluates whether a feature's correlation profile is heavily concentrated into a narrow cluster of tightly coupled variables using inequality metrics (Gini coefficient and Herfindahl index).",
            "",
            "Example question it answers: 'Is this feature part of a redundant, tightly correlated clique of features created by a specific flow extractor tool?'",
            "",
            "When it is useful: Characterizing feature extraction cliques, multicollinearity, and redundant sub-graphs in network flow representations.",
        ],
        "level2_operational": [
            "Input requirements: feature_name (single numeric feature).",
            "What it returns: gini_coefficient, herfindahl_index, top_correlated_features, concentration_level.",
            "How to interpret: Gini > 0.8 indicates extreme dependency concentration: the feature only correlates with 1 or 2 specific partners and is orthogonal to everything else in the network.",
            "Limitations: Does not measure direct label correlation; measures structural dependency across the feature space.",
            "Relationship with Workers: Router assigns action class 'dependency_contextualization'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/dependency_concentration_analysis.py -> dependency_concentration_analysis()",
            "Registry entry: 'dependency_concentration_analysis' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='dependency_contextualization'",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'dependency_concentration_analysis'",
        ],
    },
    {
        "tool_name": "duplication_analysis",
        "display_name": "Duplication Analysis",
        "epistemic_role": "duplication_verification",
        "supported_scopes": ["dataset"],
        "level1_orientation": [
            "What it does: Detects exact identical duplicate records across all features at dataset scope. It computes the duplication percentage, count of unique rows, and duplication breakdown across class labels.",
            "",
            "Example question it answers: 'Are there thousands of duplicate flows repeated verbatim in this partition?'",
            "",
            "When it is useful: Investigating data leakage and inflated evaluation scores. When identical duplicate rows fall into both train and test sets, ML models simply memorize repeated flows.",
        ],
        "level2_operational": [
            "Input requirements: None (operates at dataset scope; feature_name=None).",
            "What it returns: total_rows, unique_rows, duplicate_rows, duplication_rate, duplicates_per_class.",
            "How to interpret: A duplication rate > 5-10% is a severe integrity flaw in NIDS benchmarks. If duplicate flows occur with conflicting labels (e.g. same flow labeled both Benign and Attack), that indicates label noise.",
            "Limitations: Only checks exact record equality across all columns. It does not measure near-duplicates (which requires locality-sensitive hashing).",
            "Relationship with Workers: Router assigns action class 'duplication_verification'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/duplication_analysis.py -> duplication_analysis()",
            "Registry entry: 'duplication_analysis' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='duplication_verification', supported_scopes=['dataset']",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'duplication_analysis'",
        ],
    },
    {
        "tool_name": "wasserstein",
        "display_name": "Wasserstein Distance",
        "epistemic_role": "distribution_distance_verification",
        "supported_scopes": ["feature"],
        "level1_orientation": [
            "What it does: Computes the normalized 1D Wasserstein metric (also known as Earth Mover's Distance) between the benign distribution and the attack distribution for a feature.",
            "",
            "Example question it answers: 'What is the minimum mathematical work required to transform the benign distribution into the attack distribution?'",
            "",
            "When it is useful: Quantifying the exact degree of class divergence without making Gaussian distribution assumptions.",
        ],
        "level2_operational": [
            "Input requirements: feature_name (single numeric feature).",
            "What it returns: wasserstein_distance, normalized_distance, sample_sizes.",
            "How to interpret: Normalized distance near 1.0 indicates virtually disjoint, non-overlapping distributions. Normalized distance near 0.0 indicates identical distributions.",
            "Limitations: Measures 1D distance along a single feature axis; does not capture multi-dimensional joint distribution distances.",
            "Relationship with Workers: Router assigns action class 'distribution_distance_verification'.",
        ],
        "level3_technical": [
            "Tool file: Phase3/tools/wasserstein.py -> wasserstein()",
            "Registry entry: 'wasserstein' in Phase3/tools/registry.py",
            "Capability record: epistemic_role='distribution_distance_verification'",
            "Methodological context: Registered runtime tool. Table 3.1 in Thesis methodology.tex documents the 8 core analytical tools; wasserstein serves as an active continuous distance capability within the extensible architecture.",
            "Direct CLI run: ATLAS Components -> [11] Tools -> Enter 'wasserstein'",
            "Test suite: Phase3/tests/test_tools_phase3a_runtime.py",
        ],
    },
]


# ---------------------------------------------------------------------------
# Section 6: Debugging and Observability
# Grounded in Phase3 runtime logging, terminal_ui review menus & Thesis
# ---------------------------------------------------------------------------

DEBUGGING_TOPICS: list[dict[str, Any]] = [
    {
        "id": "systematic_inspection",
        "title": "Systematic Execution Inspection",
        "subtitle": "Navigating saved runs, run statuses, rounds & worker traces",
        "level1_orientation": [
            "When investigating what happened during an ATLAS execution, you should follow a systematic debugging path rather than guessing or searching blindly across log folders.",
            "",
            "The golden rule of ATLAS debugging: Follow the execution hierarchy downward:",
            "  Batch Summary -> Round Manifest -> Hypothesis Run -> Worker Task -> Tool Call",
            "",
            "Distinguishing Run Outcomes:",
            "- Completed: Execution finished normally; canonical state updated and reports written.",
            "- Partial: Some tasks or components encountered errors, but the round produced usable state.",
            "- Failed: A fatal exception occurred (e.g. OpenAI rate limit, missing file); execution halted.",
            "- Reporting Error: The entire investigation completed successfully, but the Markdown report synthesis failed (e.g. LLM timeout). The audit data is intact on disk!",
        ],
        "level2_operational": [
            "Step-by-step navigation in the terminal UI:",
            "",
            "1. Locate the run:",
            "   Batch Runtime -> [V] View Saved ATLAS Batch Runs -> Select your run by timestamp.",
            "",
            "2. Inspect the Batch Summary Table:",
            "   Review batch_id, status, round_count, warnings, and error messages.",
            "",
            "3. Inspect Rounds and Manifests:",
            "   Select [3], [4], or [5] to drill into specific rounds.",
            "   Check start_state_version -> end_state_version and selected hypotheses.",
            "",
            "4. Drill into Worker Traces:",
            "   Select [5] Browse Router / Worker / Aggregation Tree -> Choose Hypothesis ->",
            "   Select Worker Task -> Select [2] Browse Step Timeline to see every ReAct step.",
        ],
        "level3_technical": [
            "Disk directory structure:",
            "- Master batch directory: Phase3/logs/phase3a_runtime_runs/<run_name>/",
            "- Batch ledger: logs/phase3a_runtime_runs/<run_name>/batch_ledger.json",
            "- Event stream: logs/phase3a_runtime_runs/<run_name>/event_stream.jsonl",
            "- Execution log: logs/phase3a_runtime_runs/<run_name>/runtime_terminal.log",
            "- Round snapshots: logs/phase3a_runtime_runs/<run_name>/round_manifests/",
            "- Component runs: Phase3/logs/<component>_runs/<run_name>/ (e.g. worker_runs, state_manager_runs)",
        ],
    },
    {
        "id": "component_diagnostics",
        "title": "12-Stage Component Diagnostics & Observability Limits",
        "subtitle": "How to inspect every execution stage & what is not in the CLI",
        "level1_orientation": [
            "Every component in ATLAS passes through a 12-stage execution lifecycle. Understanding these stages allows you to pinpoint the exact moment an error or unexpected behavior occurred.",
            "",
            "A critical distinction to keep in mind:",
            "- The prompt template is NOT the rendered prompt (it is the static code template).",
            "- The raw model response is NOT the validated output (it is the raw LLM string).",
            "- The validated output is NOT the canonical state (it must still be aggregated).",
        ],
        "level2_operational": [
            "The 12 Diagnostic Stages and where to inspect them in ATLAS:",
            "",
            "1. Component Identity & Run ID: In review summary header table.",
            "2. Original Task / Objective: In Option [1] 'Inspect Inputs'.",
            "3. Input Payload & Context: In Option [1] 'Inspect Inputs'.",
            "4. Static Prompt Template: *** Observability Limitation ***",
            "   The unrendered Jinja/f-string template is NOT rendered in the CLI. Inspect the component's prompt_builder.py source file.",
            "5. Rendered Prompt: In Option [4] 'Inspect Prompt / Response' -> === PROMPT ===.",
            "6. Raw Model Response: In Option [4] 'Inspect Prompt / Response' -> === RAW RESPONSE ===.",
            "7. JSON Parsing Outcome: In Option [3] 'Inspect Validation'.",
            "8. Schema Validation & Repair: In Option [3] 'Inspect Validation' (shows validation_report.json and repair attempts).",
            "9. Validated Structured Output: In Option [2] 'Inspect Parsed Output'.",
            "10. Canonical State Deltas: In State Manager Review Option [2] 'Inspect State Delta', or Batch Review [12] 'State Evolution'.",
            "11. Persisted Disk Artifacts: In Option [5] 'Inspect Technical Details' (shows full paths).",
            "12. Downstream Consumption: Documented in pipeline flow; not a dynamic CLI link.",
        ],
        "level3_technical": [
            "Observability Implementation References:",
            "- Review renderer: Phase3/interface/terminal_ui.py -> render_<component>_run_review()",
            "- Review handler: Phase3/interface/cli.py -> _handle_<component>_review_choice()",
            "- Validation report format: Phase3/validation_repair_engine/engine.py",
            "- When an artifact is missing from the CLI, open the raw JSON file directly in your code editor from Phase3/logs/phase3a_runtime_runs/<run_name>/ or Phase3/logs/<component>_runs/.",
        ],
    },
    {
        "id": "failure_troubleshooting",
        "title": "Troubleshooting by Failure Type (14 Scenarios)",
        "subtitle": "Diagnostic recipes for the most common pipeline issues",
        "level1_orientation": [
            "When something goes wrong, do not guess. Consult these 14 diagnostic recipes to trace the symptom directly to the responsible module.",
        ],
        "level2_operational": [
            "1. Component did not execute:",
            "   Observe: Batch summary shows failed component count or missing round manifest.",
            "   First inspect: Batch Review -> [8] View Runtime Execution Log.",
            "   Next layer: logs/phase3a_runtime_runs/<run_name>/event_stream.jsonl for the last event before halt.",
            "   Responsible module: Phase3/phase3_runtime/orchestrator.py.",
            "",
            "2. Component executed but produced empty findings:",
            "   Observe: Parsed output has findings: [].",
            "   First inspect: Component Review -> [4] Prompt / Response (check if model reasoned that no evidence met criteria).",
            "   Responsible module: Phase3/<component>/prompt_builder.py.",
            "",
            "3. LLM returned malformed JSON:",
            "   Observe: Validation report indicates JSONDecodeError.",
            "   First inspect: Component Review -> [3] Validation Report and [4] Raw Response.",
            "   Responsible module: Phase3/validation_repair_engine/engine.py (check if repair failed).",
            "",
            "4. Schema or contract validator rejected output:",
            "   Observe: validation_ok: False in summary table.",
            "   First inspect: Component Review -> [3] Validation Report (check missing_fields / type_errors).",
            "   Responsible module: Phase3/<component>/validator.py.",
            "",
            "5. Validation repair changed or dropped a field:",
            "   Observe: Output has fewer keys than raw LLM response.",
            "   First inspect: logs/<component>_runs/<run>/validation_report.json -> repair_attempts.",
            "   Responsible module: Phase3/validation_repair_engine/engine.py.",
            "",
            "6. Worker selected unexpected action or tool:",
            "   Observe: Tool events show unanticipated analytical function.",
            "   First inspect: Worker Review -> [1] Inspect Task (check allowed_actions list).",
            "   Responsible module: Phase3/router/runner.py (Router assigns allowed actions).",
            "",
            "7. Tool returned error or insufficient evidence:",
            "   Observe: Worker step trace shows ok: False or error_message: 'INVALID_ACTION'.",
            "   First inspect: Worker Review -> [2] Step Timeline -> Expand tool event.",
            "   Responsible module: Phase3/tools/<tool_name>.py or Phase3/tools/execution.py.",
            "",
            "8. Evidence did not reach aggregation or state:",
            "   Observe: Worker reported a finding, but canonical state v(N+1) does not show it.",
            "   First inspect: Aggregation Review -> [1] Source Worker Results vs [2] Merge Output.",
            "   Responsible module: Phase3/aggregation/runner.py or Phase3/state_manager/runner.py.",
            "",
            "9. Critic rejected or flagged proposed state change:",
            "   Observe: Critic evaluation contains warnings regarding search concentration.",
            "   First inspect: Batch Review -> [7] Review Critic Tree.",
            "   Responsible module: Phase3/critic/runner.py.",
            "",
            "10. Round stopped early (terminal reason triggered):",
            "    Observe: Batch finished in 1 or 2 rounds instead of max rounds.",
            "    First inspect: Batch Review -> summary pair 'terminal_reason'.",
            "    Responsible module: Phase3/phase3_runtime/orchestrator.py.",
            "",
            "11. Full batch completed but Final Report failed:",
            "    Observe: Batch status is 'completed' but 'See full report' option is absent.",
            "    First inspect: Batch summary warnings for component: 'final_batch_report'.",
            "    Remedy: Run report generator independently via Components -> [13] Final Batch Report.",
            "    Responsible module: Phase3/final_batch_report/runner.py.",
            "",
            "12. Round Report could not be generated:",
            "    Observe: Post-round screen displays error message under report_error.",
            "    First inspect: logs/round_report_runs/<run>/round_report_manifest.json and component_run.json.",
            "    Responsible module: Phase3/final_batch_report/round_runner.py.",
            "",
            "13. CLI appears frozen or slow:",
            "    Observe: Terminal hangs during execution.",
            "    Explanation: LLM inference in progress (calls typically take 5-25 seconds). If hanging > 2 minutes, check network connection or OpenAI API status.",
            "",
            "14. Artifact exists on disk but is not visible in CLI:",
            "    Observe: Run folder exists in logs/phase3a_runtime_runs/, but CLI view menu does not show it.",
            "    First inspect: View limit! Press [C] in View Runs menu to increase display limit.",
            "    Responsible module: Phase3/interface/cli.py -> _generic_view_runs_menu().",
        ],
        "level3_technical": [
            "Source implementation for validation repairs: Phase3/validation_repair_engine/engine.py",
            "Unit tests for repair behaviors: tests/test_validation_repair_engine.py",
            "Observability limitation: When an execution error occurs, the full traceback is captured in logs/phase3a_runtime_runs/<run>/runtime_terminal.log, while the CLI displays a truncated one-line error summary.",
        ],
    },
    {
        "id": "tracing_walkthrough",
        "title": "End-to-End Debugging Walkthrough",
        "subtitle": "Tracing a real component execution through all 12 stages",
        "level1_orientation": [
            "To solidify your debugging skills, here is an illustrative walkthrough following an actual worker execution investigating a shortcut hypothesis on feature 'Fwd Packet Length Min'.",
        ],
        "level2_operational": [
            "Walkthrough Trace:",
            "",
            "Stage 1 -- Input Task:",
            "Router emits Task task_001 with task_scope='Fwd Packet Length Min' and allowed_actions=['shortcut_verification'].",
            "Persisted: logs/router_runs/<run>/router_tasks.json.",
            "",
            "Stage 2 -- Prompt Construction:",
            "Worker prompt builder combines task_001, local context for 'Fwd Packet Length Min', and step stage 'evidence_acquisition'.",
            "Code reference: Phase3/worker/prompt_builder.py.",
            "",
            "Stage 3 -- Model Execution:",
            "Worker LLM outputs action: {'action_class': 'shortcut_verification', 'feature_name': 'Fwd Packet Length Min'}.",
            "Inspect in CLI: Worker Review -> [4] Prompt / Response.",
            "",
            "Stage 4 -- Execution Adapter & Tool Execution:",
            "execution_adapter.py maps 'shortcut_verification' to tools.shortcut_analysis.shortcut_analysis.",
            "Tool runs decision stump on Friday-WorkingHours-DDoS.csv. Result: threshold=0.0, accuracy=0.9997.",
            "Persisted: logs/worker_runs/<run>/tool_events.jsonl.",
            "",
            "Stage 5 -- Parse & Validate:",
            "Worker parses tool observation into finding: 'Fwd Packet Length Min threshold=0.0 achieves 99.97% separability'.",
            "Strict contract validator in Phase3/worker/validator.py confirms finding structure. validation_ok=True.",
            "",
            "Stage 6 -- Aggregation & State:",
            "Aggregation verifies finding against other tasks. State Manager updates state_v1 -> state_v2, marking hypothesis as 'confirmed'.",
            "Persisted: logs/state_manager_runs/<run>/updated_batch_state.json.",
            "",
            "Stage 7 -- Report Dossier:",
            "Final Batch Report incorporates the finding into Section 5 'Evidence and Statistical Results'.",
        ],
        "level3_technical": [
            "Verification command in terminal: .venv/Scripts/pytest tests/test_worker_prompt_redesign.py",
            "Relevant test fixtures: tests/fixtures/ (sample substrates and task specifications).",
            "Artifact inspection: python -c \"import json; print(json.load(open('logs/worker_runs/<run>/worker_result.json')))\"",
        ],
    },
]


# ---------------------------------------------------------------------------
# Section 7: Reports and Persisted Outputs
# Grounded in Phase3/final_batch_report/, final_batch_auditor/ & evaluation/
# ---------------------------------------------------------------------------

REPORTS_TOPICS: list[dict[str, Any]] = [
    {
        "id": "reporting_ecosystem",
        "title": "Reporting & Artifact Ecosystem Overview",
        "subtitle": "How audit dossiers, state files, and evaluation scripts connect",
        "level1_orientation": [
            "ATLAS produces several distinct types of reports and artifacts. Understanding what each document answers, when it is generated, and where it lives on disk is essential for interpreting results.",
            "",
            "Primary categories of outputs:",
            "1. Round Reports: 1-round executive audit dossiers.",
            "2. Final Batch Reports: Multi-round consolidated partition audits.",
            "3. Final Batch Auditor JSON: Technical finding inventories and contracts.",
            "4. Canonical State Revisions: Versioned history of investigation state (v1..vN).",
            "5. Worker Traces & Ledgers: Granular ReAct logs and batch index ledgers.",
            "6. Formal Thesis Evaluation: Independent research benchmark scripts.",
            "7. Legacy & Archived Outputs: Deprecated Phase 2 single-agent artifacts.",
        ],
        "level2_operational": [
            "Where to find reports in the interface:",
            "- Immediately after a Full Round run: Post-round menu -> [1] See round report.",
            "- Immediately after a Full Batch run: Post-run menu -> [1] See full report.",
            "- From the Components Menu: Components -> [13] Final Batch Report.",
            "- On disk: logs/final_batch_report_runs/, logs/round_report_runs/, docs/batch_reports/, and final_dataset/.",
        ],
        "level3_technical": [
            "Primary storage directories:",
            "- Final partition reports: Phase3/logs/final_batch_report_runs/<run>/report.md",
            "- Round reports: Phase3/logs/round_report_runs/<run>/report.md",
            "- Batch ledgers: Phase3/logs/phase3a_runtime_runs/<run>/batch_ledger.json",
            "- Canonical state: Phase3/logs/state_manager_runs/<run>/updated_batch_state.json and phase3a_runtime_runs/<run>/round_manifests/",
            "- Benchmark reference partition reports: docs/batch_reports/<partition_name>.md",
            "- Cross-partition merged dataset: final_dataset/final_dataset_report.md",
            "- Evaluation scripts: Phase3/../evaluation/scripts/ (formal thesis evaluation)",
        ],
    },
    {
        "id": "round_report",
        "title": "The Single-Round Round Report",
        "subtitle": "Scoped 1-round audit dossier with 9 authoritative sections",
        "level1_orientation": [
            "What question it answers: 'What was investigated during this single round, what empirical tool observations were made, and what state transitions occurred?'",
            "",
            "Scope: Strictly scoped to the events and findings of 1 investigation round. It does NOT assert premature dataset-wide conclusions.",
            "",
            "When it is generated: Generated automatically at the end of a 'Run Full Round' workflow or during each round of a multi-round batch.",
        ],
        "level2_operational": [
            "The 9 Authoritative Sections:",
            "1. Execution Identity and Status",
            "2. Executive Summary",
            "3. Investigation Objectives and Hypotheses",
            "4. Investigation Process and Tools Used",
            "5. Evidence and Statistical Results",
            "6. Findings and Their Interpretation",
            "7. State Changes and Critic Assessment",
            "8. Unresolved Questions and Contradictions",
            "9. Limitations and Evidence Provenance",
            "",
            "How to view: Post-round screen -> [1] See round report opens the full markdown text in the terminal viewer.",
            "Regeneration: Can be regenerated without rerunning tools using final_batch_report.round_runner.run_round_report().",
        ],
        "level3_technical": [
            "Runner source: Phase3/final_batch_report/round_runner.py -> run_round_report()",
            "Contracts: Phase3/final_batch_report/round_contracts.py -> ROUND_REPORT_SECTIONS",
            "Input resolver: Phase3/final_batch_report/round_input_resolver.py",
            "Prompt builder: Phase3/final_batch_report/round_prompt_builder.py",
            "Output location: logs/round_report_runs/<round_report_run_name>/report.md",
        ],
    },
    {
        "id": "final_batch_report",
        "title": "The Full-Batch Final Partition Report",
        "subtitle": "Consolidated multi-round audit dossier for researchers",
        "level1_orientation": [
            "What question it answers: 'What is the comprehensive audit assessment of this dataset partition across all investigation rounds?'",
            "",
            "Scope: Covers the full multi-round batch execution. Synthesizes findings, traces hypothesis evolution from initial leads to confirmed flaws, and provides modeling recommendations.",
            "",
            "When it is generated: At the conclusion of a 'Run Full Batch' execution, or manually via Components -> [13] Final Batch Report.",
        ],
        "level2_operational": [
            "Key sections included:",
            "- Partition Audit Context (e.g., DDoS, PortScan, or Web scenario characteristics).",
            "- Executive Summary of Verified Flaws (shortcut risks, leakage, duplication).",
            "- Finding Inventory (sorted by severity and evidential confidence).",
            "- Cross-Hypothesis Synthesis and Structural Relationships.",
            "- Methodological Limitations and Downstream Modeling Recommendations.",
            "",
            "Where to find it:",
            "- Post-run menu: [1] See full report.",
            "- Disk location: Phase3/logs/final_batch_report_runs/<run>/report.md.",
            "- Companion metadata: Phase3/logs/final_batch_report_runs/<run>/component_run.json.",
            "- Reference benchmark partition reports: docs/batch_reports/<partition_name>.md.",
            "- Cross-partition merged dataset report: final_dataset/final_dataset_report.md.",
        ],
        "level3_technical": [
            "Runner source: Phase3/final_batch_report/runner.py -> run_final_batch_report()",
            "Input resolver: Phase3/final_batch_report/input_resolver.py",
            "Prompt builder: Phase3/final_batch_report/prompt_builder.py",
            "Schema version: 'phase3.final_batch_report.v1'",
            "Unit tests: tests/test_final_batch_report.py",
        ],
    },
    {
        "id": "auditor_output",
        "title": "Technical Final Batch Auditor Output",
        "subtitle": "Structured JSON contract & verified Finding Inventory",
        "level1_orientation": [
            "What question it answers: 'Which findings have verified empirical provenance, and what is the machine-readable audit contract?'",
            "",
            "Why it exists: The Markdown reports are designed for human reading. The Final Batch Auditor output is a strict, machine-readable JSON artifact designed for programmatic consumption, automated evaluation, and dataset-level merging.",
        ],
        "level2_operational": [
            "Key properties of the Auditor output:",
            "- Finding Inventory: Classifies all hypotheses into 'investigated' vs 'uninvestigated'.",
            "- Evidence Matrix: Links every finding to exact tool observations.",
            "- Internal ID Stripping: Replaces internal IDs (e.g. e12, hyp_5, region_8) with descriptive domain titles.",
            "- Reproducibility Metadata: Preserves batch_id, model names, execution timestamps, and random seeds.",
        ],
        "level3_technical": [
            "Runner source: Phase3/final_batch_auditor/runner.py -> run_final_batch_auditor()",
            "Schema: contracts.SCHEMA_VERSION = 'phase3a.final_batch_auditor.v1'",
            "Disk location: logs/final_batch_auditor_runs/<run>/debugging_audit_report.json",
            "Unit tests: tests/test_final_batch_report.py (test_finding_inventory_classifies_correctly).",
        ],
    },
    {
        "id": "state_history",
        "title": "Canonical State History & Snapshots",
        "subtitle": "Versioned memory progression from state_v1 to state_vN",
        "level1_orientation": [
            "What question it answers: 'How did the system's understanding of the dataset evolve between Round 1, Round 2, and Round N?'",
            "",
            "Why it matters: State versioning enables full audit reproducibility. If a researcher asks why a conclusion was reached, they can inspect state_v1 (the initial state), state_v2 (after first tool evidence), and observe the exact evidentiary transition.",
        ],
        "level2_operational": [
            "State Files on Disk:",
            "- logs/phase3a_runtime_runs/<run>/initial_state.json: Initial state after Semantic Extraction.",
            "- logs/phase3a_runtime_runs/<run>/round_manifests/round-001_snapshot.json: Frozen round 1 snapshot.",
            "- logs/phase3a_runtime_runs/<run>/round_manifests/round-002_snapshot.json: Frozen round 2 snapshot.",
            "- logs/state_manager_runs/<run>/updated_batch_state.json: State update per round.",
            "",
            "How to inspect in CLI:",
            "Batch Runtime Review -> Option [12] 'Inspect State Evolution'.",
        ],
        "level3_technical": [
            "State implementation: Phase3/state/state_manager.py and Phase3/state_manager/runner.py",
            "State schema: contracts.SCHEMA_VERSION = 'phase3a.state_manager.v1'",
            "Unit tests: tests/test_state_manager_status_transitions.py",
        ],
    },
    {
        "id": "traces_and_ledgers",
        "title": "Worker Traces, Event Streams & Batch Ledgers",
        "subtitle": "Granular ReAct logs, tool events, and chronological ledgers",
        "level1_orientation": [
            "For deep technical debugging, ATLAS logs every low-level event in granular, structured trace files.",
            "",
            "Artifacts explained:",
            "- Worker Traces (logs/worker_runs/): Step-by-step ReAct logs containing the exact reasoning string, action requested, observation returned, and step duration.",
            "- Event Stream (event_stream.jsonl): Chronological JSON Lines file capturing every lifecycle event across all components in a batch.",
            "- Batch Ledger (batch_ledger.json): Master manifest indexing all round manifests, component execution paths, and terminal statuses.",
        ],
        "level2_operational": [
            "How to inspect in CLI:",
            "- Event stream: Batch Runtime Review -> Option [9] 'View Structured Runtime Event Stream'.",
            "- Batch ledger: Batch Runtime Review -> Option [11] 'Inspect Batch Ledger'.",
            "- Execution log: Batch Runtime Review -> Option [8] 'View Runtime Execution Log'.",
        ],
        "level3_technical": [
            "Event stream format: Chronological JSONL with event_type, timestamp, component, and payload.",
            "Batch ledger format: JSON document structured under Phase3/phase3_runtime/contracts.py.",
        ],
    },
    {
        "id": "formal_evaluation_pipeline",
        "title": "Formal Thesis Evaluation vs Live In-CLI Reports",
        "subtitle": "Separating live research auditing from benchmark evaluation",
        "level1_orientation": [
            "It is important to distinguish the live in-CLI auditing features of ATLAS from the separate formal thesis evaluation pipeline.",
            "",
            "Live In-CLI Reports (Phase 3A/3B):",
            "- Generated during live user sessions to audit a specific dataset partition.",
            "- Produces Round Reports, Final Partition Reports, and Dataset Reports for security researchers.",
            "",
            "Formal Thesis Evaluation Pipeline (evaluation/):",
            "- A separate, offline suite of evaluation scripts developed to empirically validate the ATLAS framework itself for the Bachelor's Thesis.",
            "- Compares ATLAS findings against published literature (CIC-IDS2017 & UNSW-NB15 flaw corpus).",
            "- Computes formal thesis metrics: Tool Diversity Index, Feature Revisit Rate, Hypothesis Stability, and Finding Reproducibility.",
        ],
        "level2_operational": [
            "Where to find evaluation scripts:",
            "- evaluation/scripts/: Python scripts for metric aggregation, literature corpus validation, and LaTeX figure generation.",
            "- evaluation/findings/: Pre-computed literature validation matrices.",
            "- evaluation/outputs/: Rendered evaluation figures and tables included in the thesis.",
            "",
            "Running thesis evaluation reproduction:",
            "  python evaluation/scripts/validate_literature_corpus.py",
            "  python evaluation/scripts/generate_evaluation_figures.py",
        ],
        "level3_technical": [
            "Thesis documentation: Thesis methodology.tex (Section 3.6 'Evaluation') and appendices.tex (Section B 'Evaluation Metrics').",
            "Reproducibility guide: Thesis appendices.tex (Section A.4 'Evaluation Reproduction').",
        ],
    },
    {
        "id": "legacy_archives",
        "title": "Legacy Historical Reports & Deprecated Code",
        "subtitle": "Archived Phase 2 single-agent loop and decommissioned Judge/JIF",
        "level1_orientation": [
            "During development, ATLAS evolved from an initial single-agent Phase 2 MVP into the modern multi-agent Phase 3A/3B architecture.",
            "",
            "The obsolete Phase 2 single-agent loop and its Judge/JIF subsystem have been decommissioned and archived under Phase3/archive/. They are NOT active.",
            "",
            "If you encounter legacy test fixtures or archived reports in Phase3/archive/, they represent historical research milestones and should not be used for active auditing.",
        ],
        "level2_operational": [
            "Active Architecture: Phase 3A (Multi-agent Partition Audit) and Phase 3B (Dataset Merger & Runtime).",
            "Archived Code: Located in Phase3/archive/ for historical reference only.",
        ],
        "level3_technical": [
            "Archive location: Phase3/archive/",
            "Git history milestone: Commit 975869c 'Elimination of legacy code'.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Query & Data Retrieval Helpers
# ---------------------------------------------------------------------------


def get_category_items(category_id: str) -> list[dict[str, Any]]:
    """Return the items list corresponding to the category."""
    if category_id == "getting_started":
        return GETTING_STARTED_TOPICS
    elif category_id == "ways_to_run":
        return WAYS_TO_RUN_TOPICS
    elif category_id == "investigation_flow":
        return INVESTIGATION_FLOW_TOPICS
    elif category_id == "components":
        return COMPONENTS_CATALOGUE
    elif category_id == "tools":
        return TOOLS_CATALOGUE
    elif category_id == "debugging":
        return DEBUGGING_TOPICS
    elif category_id == "reports":
        return REPORTS_TOPICS
    return []


def get_category_item_count(category_id: str) -> int:
    """Return total number of topics/items in a category."""
    return len(get_category_items(category_id))


def get_category_item_title(category_id: str, item_idx: int) -> str:
    """Return the display title of a specific category item."""
    items = get_category_items(category_id)
    if 0 <= item_idx < len(items):
        item = items[item_idx]
        return str(item.get("display_name") or item.get("name") or item.get("title") or "Item")
    return "Topic"


def get_category_by_key(key: str) -> dict[str, str] | None:
    """Find a category dict by numerical key ('1'..'7') or id."""
    for cat in CATEGORIES:
        if cat["key"] == key or cat["id"] == key:
            return cat
    return None


# ---------------------------------------------------------------------------
# Rendering: How to Use Landing Menu (Table of Contents)
# ---------------------------------------------------------------------------


def render_how_to_use_landing() -> str:
    """Render the primary How to Use landing menu table of contents."""
    title = "HOW TO USE ATLAS -- Interactive Learning Guide"
    path_label = "Home / How to Use ATLAS"
    hint = "Select a category to explore topics, active components, tools & debugging."

    lines: list[str] = [
        *_meta_lines(path_label, hint),
        *_section_header("Welcome to the ATLAS Interactive Guide"),
        *_wrap_body(
            "This guide is an interactive field guide inside the ATLAS terminal interface. "
            "It explains how ATLAS operates, what analytical capabilities it provides, how "
            "evidence moves between components, and how to systematically investigate the "
            "system when something goes wrong."
        ),
        "",
        *_wrap_body(
            "The guide uses progressive disclosure: start with plain-language orientation, "
            "drill into operational understanding, and reveal technical source references on demand."
        ),
        "",
        _subtle_rule("-", "brown"),
        "",
        *_section_header("Explore Categories"),
    ]

    for cat in CATEGORIES:
        key = cat["key"]
        cat_title = cat["title"]
        desc = f"{cat['subtitle']} -- {cat['description']}"
        lines.extend(_menu_line(key, cat_title, desc))
        lines.append("")

    lines.extend([
        _subtle_rule("-", "brown"),
        "",
        *_section_header("Navigation"),
        *_menu_line("1..7", "Open Category Topics"),
        *_menu_line("M", "Enter Main Research Console"),
        *_menu_line("B", "Return to Welcome Menu"),
        *_menu_line("Q", "Quit ATLAS"),
    ])

    return _block(title, lines)


# ---------------------------------------------------------------------------
# Rendering: Category Sub-Menu (Topic / Component / Tool Index)
# ---------------------------------------------------------------------------


def render_category_menu(category_id: str) -> str:
    """Render the browsable catalogue / topic list of a category."""
    cat = CATEGORY_MAP.get(category_id)
    if not cat:
        return _block("Category Not Found", ["Unknown category ID."])

    cat_title = cat["title"]
    path_label = f"How to Use ATLAS / {cat_title}"
    hint = "Select a topic by number to inspect its details, or [B] to return to TOC."

    items = get_category_items(category_id)
    is_components = category_id == "components"
    is_tools = category_id == "tools"

    lines: list[str] = [
        *_meta_lines(path_label, hint),
        *_section_header(cat["subtitle"]),
        *_wrap_body(cat["description"]),
        "",
        _subtle_rule("-", "brown"),
        "",
    ]

    if is_components:
        lines.extend(_section_header("Active Phase 3A/3B Components"))
        lines.extend(_wrap_body(
            "Select any component to inspect its plain-language purpose, inputs/outputs, "
            "prompt and validation design, and implementation source references."
        ))
        lines.append("")
    elif is_tools:
        lines.extend(_section_header("Registered Analytical Tools"))
        lines.extend(_wrap_body(
            "Select any registered tool to inspect the question it answers, input requirements, "
            "output statistics, interpretation limits, and capability records."
        ))
        lines.append("")
    else:
        lines.extend(_section_header("Available Topics"))

    for idx, item in enumerate(items, 1):
        if is_components:
            name = str(item.get("name", "Component"))
            role = str(item.get("role", ""))
            subsystem = str(item.get("subsystem", ""))
            desc = f"[{subsystem}] {role}"
            lines.extend(_menu_line(str(idx), name, desc))
        elif is_tools:
            name = str(item.get("display_name", "Tool"))
            role = str(item.get("epistemic_role", ""))
            scopes = ", ".join(item.get("supported_scopes", []))
            desc = f"Action: {role} (Scope: {scopes})"
            lines.extend(_menu_line(str(idx), name, desc))
        else:
            item_title = str(item.get("title", "Topic"))
            subtitle = str(item.get("subtitle", ""))
            lines.extend(_menu_line(str(idx), item_title, subtitle))
        lines.append("")

    lines.extend([
        _subtle_rule("-", "brown"),
        "",
        *_section_header("Navigation"),
        *_menu_line(f"1..{len(items)}", "Select Item to View"),
        *_menu_line("B", "Back to How to Use Categories"),
        *_menu_line("M", "Enter Main Research Console"),
        *_menu_line("W", "Return to Main Welcome Menu"),
        *_menu_line("Q", "Quit ATLAS"),
    ])

    return _block(f"ATLAS: {cat_title}", lines)


# ---------------------------------------------------------------------------
# Rendering: Detail Screen (Topic / Component / Tool)
# ---------------------------------------------------------------------------


def render_category_item(category_id: str, item_idx: int, show_details: bool = False) -> str:
    """Render the progressive disclosure detail screen for an item."""
    cat = CATEGORY_MAP.get(category_id)
    if not cat:
        return _block("Category Not Found", ["Unknown category ID."])

    items = get_category_items(category_id)
    if not (0 <= item_idx < len(items)):
        return _block("Item Not Found", ["Invalid item index."])

    item = items[item_idx]
    is_component = category_id == "components"
    is_tool = category_id == "tools"

    if is_component:
        title_str = str(item.get("name", "Component"))
        subtitle_str = f"{item.get('subsystem', '')} -- {item.get('role', '')}"
    elif is_tool:
        title_str = f"{item.get('display_name', 'Tool')} ({item.get('tool_name', '')})"
        subtitle_str = f"Action Class: {item.get('epistemic_role', '')}"
    else:
        title_str = str(item.get("title", "Topic"))
        subtitle_str = str(item.get("subtitle", ""))

    path_label = f"How to Use / {cat['title']} / [{item_idx + 1}] {title_str}"
    hint = "Press [D] to toggle Level 3 Implementation References. Use [N]/[P] to navigate."

    lines: list[str] = [
        *_meta_lines(path_label, hint),
        *_section_header(subtitle_str),
        "",
        *_section_header("Level 1 -- Orientation"),
    ]

    # Level 1 lines
    for p in item.get("level1_orientation", []):
        if p == "":
            lines.append("")
        elif p.startswith("- "):
            lines.extend(_wrap_bullet(p[2:], "-"))
        elif ":" in p and not p.startswith(" ") and len(p.split(":", 1)[0]) < 28:
            k, v = p.split(":", 1)
            lines.extend(_wrap_key_value(k.strip(), v.strip()))
        else:
            lines.extend(_wrap_body(p))
    lines.append("")

    # Level 2 lines
    lines.append(_subtle_rule("-", "brown"))
    lines.append("")
    lines.extend(_section_header("Level 2 -- Operational Understanding"))
    for p in item.get("level2_operational", []):
        if p == "":
            lines.append("")
        elif p.startswith("- "):
            lines.extend(_wrap_bullet(p[2:], "-"))
        elif ":" in p and not p.startswith(" ") and len(p.split(":", 1)[0]) < 28:
            k, v = p.split(":", 1)
            lines.extend(_wrap_key_value(k.strip(), v.strip()))
        else:
            lines.extend(_wrap_body(p))
    lines.append("")

    # Level 3 lines (Technical / Implementation references)
    lines.append(_subtle_rule("-", "brown"))
    lines.append("")
    if show_details:
        lines.extend(_section_header("Level 3 -- Implementation & Debugging References"))
        for p in item.get("level3_technical", []):
            if p == "":
                lines.append("")
            elif p.startswith("- "):
                lines.extend(_wrap_bullet(p[2:], "-"))
            elif ":" in p and not p.startswith(" ") and len(p.split(":", 1)[0]) < 28:
                k, v = p.split(":", 1)
                lines.extend(_wrap_key_value(k.strip(), v.strip()))
            else:
                lines.extend(_wrap_body(p))
        lines.append("")
    else:
        details_badge = "[D] Show Technical & Implementation References"
        if is_color_supported():
            details_badge = f"  {style(details_badge, 'amber', bold=True)}"
        else:
            details_badge = f"  {details_badge}"
        lines.append(details_badge)
        lines.extend(_wrap_body("(Reveals exact source paths, symbols, tests, schemas & persisted logs)"))
        lines.append("")

    # Navigation options footer
    lines.append(_subtle_rule("-", "brown"))
    lines.append("")
    lines.extend(_section_header("Navigation Controls"))

    details_label = "Hide Technical Details" if show_details else "Show Technical Details"
    lines.extend(_menu_line("D", f"{details_label} (Toggle Level 3)"))

    if item_idx < len(items) - 1:
        next_title = get_category_item_title(category_id, item_idx + 1)
        lines.extend(_menu_line("N", f"Next: {next_title}"))
    if item_idx > 0:
        prev_title = get_category_item_title(category_id, item_idx - 1)
        lines.extend(_menu_line("P", f"Previous: {prev_title}"))

    lines.extend([
        *_menu_line("B", f"Back to {cat['title']} Index"),
        *_menu_line("H", "Home (How to Use Categories)"),
        *_menu_line("M", "Enter Main Research Console"),
        *_menu_line("W", "Return to Main Welcome Menu"),
        *_menu_line("Q", "Quit ATLAS"),
    ])

    return _block(f"Topic: {title_str}", lines)


# ---------------------------------------------------------------------------
# Non-Interactive CLI Guide Summary (for python interface/cli.py --usage)
# ---------------------------------------------------------------------------


def get_non_interactive_usage_guide() -> str:
    """Render comprehensive, verified operational guidance for non-interactive use.

    Preserves verified command-line invocation patterns, prerequisites, component CLIs,
    and artifact directories while pointing users to the in-CLI interactive guide.
    """
    title = "HOW TO USE ATLAS -- Operational Research Guide"
    path_label = "ATLAS CLI / Non-Interactive Operational Guide"
    hint = "Run without --usage to launch the full interactive terminal guide."

    lines: list[str] = [
        *_meta_lines(path_label, hint),
        *_section_header("1. Environment & Prerequisites"),
        *_wrap_body(
            "ATLAS requires Python 3.10+ (tested with Python 3.13) and standard "
            "scientific dependencies (pandas, scikit-learn, scipy, openai, matplotlib)."
        ),
        *_wrap_body("Activate the virtual environment (.venv) and set your OpenAI API key:"),
        "    pip install -r requirements.txt",
        "    export OPENAI_API_KEY='your-key-here'  # or configure in .env",
        "",
        _subtle_rule("-", "brown"),
        "",
        *_section_header("2. Interactive Learning Guide & Research Console"),
        *_wrap_body(
            "Launch the interactive console from nids-smell-audit/Phase3:"
        ),
        "    python interface/cli.py",
        *_wrap_body(
            "From the welcome screen, select [3] How to Use ATLAS to open the redesigned "
            "interactive learning guide, or [1] Enter ATLAS to access:"
        ),
        "    [1] Batch Runtime : Multi-round batch pipeline execution & inspection",
        "    [2] Components    : Isolated execution & debugging of individual agents",
        "    [3] Session Config: Switch datasets, LLM models, and trace modes",
        "",
        _subtle_rule("-", "brown"),
        "",
        *_section_header("3. Non-Interactive & Full-Batch Execution"),
        *_wrap_body(
            "Execute end-to-end multi-round batch investigations without manual interaction:"
        ),
        '    python -c "from main import main_phase3a_batch; main_phase3a_batch()"',
        *_wrap_body("Or via the batch orchestrator CLI:"),
        "    python -m phase3_runtime.orchestrator --mode full_batch",
        "",
        _subtle_rule("-", "brown"),
        "",
        *_section_header("4. Granular Component CLIs"),
        *_wrap_body("Each research component can be invoked independently for targeted inspection:"),
        "    python -m semantic_extraction.cli --dataset <partition.csv>",
        "    python -m investigation_analysis.cli --metadata <metadata.json>",
        "    python -m hypothesis_ranking.cli --hypotheses <hypotheses.json>",
        "    python -m planner.cli --hypothesis \"<lead summary>\"",
        "    python -m router.cli --task-list <tasks.json>",
        "    python -m worker.cli --task <task.json> --context <context.json>",
        "    python -m aggregation.cli --findings <findings_dir/>",
        "    python -m critic.cli --findings <aggregated_results.json>",
        "    python -m final_batch_auditor.cli --round-results <rounds_dir/>",
        "    python -m dataset_runtime.cli --dataset-path <dataset_dir/>",
        "",
        _subtle_rule("-", "brown"),
        "",
        *_section_header("5. Artifact Locations & Reproducibility"),
        *_wrap_body("All ATLAS executions produce structured, inspectable artifacts on disk:"),
        "    logs/final_batch_report_runs/: Final multi-round partition audit reports",
        "    logs/round_report_runs/      : Scoped single-round audit reports",
        "    logs/phase3a_runtime_runs/   : Master batch ledgers, manifests & event streams",
        "    logs/worker_runs/            : Worker traces, ReAct steps & tool observations",
        "    docs/batch_reports/          : Benchmark partition reference dossiers",
        "    final_dataset/               : Phase 3B cross-partition merged dataset reports",
        "",
        _subtle_rule("-", "brown"),
        "",
        *_section_header("6. In-CLI Interactive Guide Hierarchy"),
        *_wrap_body(
            "Run 'python interface/cli.py' and press [3] to explore the full interactive guide:"
        ),
        "    [1] Getting Started with ATLAS (NIDS problem & epistemic hierarchy)",
        "    [2] Ways to Run ATLAS (Execution scopes & real CLI paths)",
        "    [3] General Investigation Flow (7-stage pipeline walkthrough)",
        "    [4] Components (All 12 active Phase 3A/3B components)",
        "    [5] Tools (All 9 registered analytical tools)",
        "    [6] Debugging & Observability (12 diagnostic stages & 14 failure guides)",
        "    [7] Reports & Persisted Outputs (Round reports vs final batch reports)",
    ]

    return _block(title, lines)
