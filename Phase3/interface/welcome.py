"""Brand identity, welcome screen, and concept presentation for ATLAS.

ATLAS: Agent-Based Dataset Auditing Framework
Tagline: Explore. Investigate. Understand.
"""

from __future__ import annotations

import os
import re
import sys
from textwrap import fill
from typing import Any

# Standard terminal rendering width, consistent with existing terminal_ui.py
WIDTH = 68

ATLAS_NAME = "ATLAS"
ATLAS_DESCRIPTOR = "Agent-Based Dataset Auditing Framework"
ATLAS_TAGLINE = "Explore. Investigate. Understand."
ATLAS_VERSION = "Phase 3A (Research Prototype)"

ATLAS_DESCRIPTION = (
    "ATLAS is an agent-based framework for systematic dataset auditing. "
    "It investigates dataset properties through hypothesis-driven analysis, "
    "tool-assisted exploration, evidence collection, and the aggregation "
    "of findings."
)

# ---------------------------------------------------------------------------
# Color and Terminal Styling
# ---------------------------------------------------------------------------


def is_color_supported() -> bool:
    """Determine whether ANSI colors should be enabled in the current terminal."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    term = os.environ.get("TERM", "")
    if term.lower() == "dumb":
        return False
    return True


def is_truecolor_supported() -> bool:
    """Check if the terminal indicates 24-bit TrueColor support."""
    colorterm = os.environ.get("COLORTERM", "").lower()
    if colorterm in {"truecolor", "24bit"}:
        return True
    if os.environ.get("WT_SESSION") or os.environ.get("VSCODE_INJECTION"):
        return True
    return False


# ANSI Escape Codes for the warm, restrained ochre, amber, and brown palette
# With graceful 16-color fallbacks when 24-bit truecolor is not indicated
_TRUECOLOR_PALETTE = {
    "ochre": "\033[38;2;204;119;34m",       # #CC7722 rich earth ochre
    "amber": "\033[38;2;255;191;0m",        # #FFBF00 bright warm amber
    "gold": "\033[38;2;240;196;70m",        # #F0C446 warm yellow / summit gold
    "brown": "\033[38;2;160;105;60m",       # #A0693C warm saddle brown
    "dark_brown": "\033[38;2;110;70;35m",   # #6E4623 deep terrain brown
    "light_grey": "\033[38;2;215;215;215m", # #D7D7D7 supporting text
    "muted": "\033[38;2;135;135;135m",      # #878787 secondary text
    "green": "\033[38;2;90;185;110m",       # status green
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}

_ANSI16_PALETTE = {
    "ochre": "\033[33m",
    "amber": "\033[33;1m",
    "gold": "\033[93m",
    "brown": "\033[33m",
    "dark_brown": "\033[30;1m",
    "light_grey": "\033[37m",
    "muted": "\033[90m",
    "green": "\033[32m",
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}


def _get_palette() -> dict[str, str]:
    if not is_color_supported():
        return {key: "" for key in _TRUECOLOR_PALETTE}
    if is_truecolor_supported():
        return _TRUECOLOR_PALETTE
    return _ANSI16_PALETTE


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from string."""
    return re.sub(r"\033\[[0-9;]*[a-zA-Z]", "", text)


def style(text: str, color_key: str, bold: bool = False, dim: bool = False) -> str:
    """Apply palette color and attributes if color is enabled."""
    if not is_color_supported():
        return text
    pal = _get_palette()
    prefix = pal.get(color_key, "")
    if bold:
        prefix = pal.get("bold", "") + prefix
    if dim:
        prefix = pal.get("dim", "") + prefix
    suffix = pal.get("reset", "")
    return f"{prefix}{text}{suffix}"


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


# ---------------------------------------------------------------------------
# ASCII Logo and Wordmark
# ---------------------------------------------------------------------------


def get_ascii_logo(*, colored: bool = True) -> str:
    """Generate the compact mountain-inspired ASCII logo and ATLAS wordmark.

    The geometry depicts dual mountain summits evoking exploration and
    cartographic contour triangulation, fitting precisely within WIDTH = 68.
    Pure standard ASCII characters ensure full cross-platform compatibility.
    """
    if not colored or not is_color_supported():
        return (
            "       /\\\n"
            "      /  \\  /\\             A  T  L  A  S\n"
            "     / /\\ \\/  \\            Agent-Based Dataset Auditing Framework\n"
            "    / /  \\ \\/\\ \\\n"
            "   /_/    \\__/\\_\\          Explore. Investigate. Understand."
        )

    ochre = _get_palette()["ochre"]
    gold = _get_palette()["gold"]
    amber = _get_palette()["amber"]
    brown = _get_palette()["brown"]
    light_grey = _get_palette()["light_grey"]
    bold = _get_palette()["bold"]
    reset = _get_palette()["reset"]

    lines = [
        f"{ochre}       /\\{reset}",
        f"{ochre}      /  \\  {gold}/\\{reset}             {bold}{amber}A  T  L  A  S{reset}",
        f"{ochre}     / /\\ \\{gold}/  \\{reset}            {gold}{ATLAS_DESCRIPTOR}{reset}",
        f"{ochre}    / /  \\ {gold}\\/\\ \\{reset}",
        f"{brown}   /_/    \\__/\\_\\{reset}          {light_grey}{ATLAS_TAGLINE}{reset}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Welcome Screen Rendering
# ---------------------------------------------------------------------------


def render_welcome_screen(
    *,
    dataset_name: str | None = None,
    version: str = ATLAS_VERSION,
) -> str:
    """Render the full interactive welcome screen with logo, description, and navigation."""
    use_color = is_color_supported()

    logo = get_ascii_logo(colored=use_color)
    top_rule = _rule("=", "ochre")
    sub_rule = _subtle_rule("-", "brown")
    bot_rule = _rule("=", "ochre")

    wrapped_desc = fill(
        ATLAS_DESCRIPTION,
        width=WIDTH - 4,
        initial_indent="  ",
        subsequent_indent="  ",
    )
    if use_color:
        wrapped_desc = "\n".join(
            style(line, "light_grey") for line in wrapped_desc.splitlines()
        )

    dataset_label = dataset_name or "Auto-discovered partition"
    meta_lines = [
        f"  Version: {version}",
        f"  Active Dataset: {dataset_label}",
    ]
    if use_color:
        meta_lines = [
            f"  {style('Version:', 'muted')} {style(version, 'gold')}",
            f"  {style('Active Dataset:', 'muted')} {style(dataset_label, 'light_grey')}",
        ]

    menu_header = "  Welcome Navigation"
    if use_color:
        menu_header = f"  {style('Welcome Navigation', 'amber', bold=True)}"

    menu_items = [
        ("1", "Enter ATLAS", "Launch interactive console and batch runtime."),
        ("2", "The Concept", "The explorer analogy: dataset auditing as cartography."),
        ("3", "How to Use ATLAS", "Interactive guide: workflows, components, tools & debugging."),
        ("4", "Thesis Experiments", "Empirical evaluation: methodology, corpus & results."),
        ("0", "Exit", "Exit the application."),
    ]

    rendered_menu: list[str] = []
    for key, title, desc in menu_items:
        if use_color:
            rendered_menu.append(f"  {style(f'[{key}]', 'gold', bold=True)} {style(title, 'amber', bold=True)}")
            rendered_menu.append(f"      {style(desc, 'muted')}")
        else:
            rendered_menu.append(f"  [{key}] {title}")
            rendered_menu.append(f"      {desc}")
        rendered_menu.append("")

    if rendered_menu and rendered_menu[-1] == "":
        rendered_menu.pop()

    sections = [
        top_rule,
        logo,
        top_rule,
        "",
        wrapped_desc,
        "",
        sub_rule,
        *meta_lines,
        sub_rule,
        "",
        menu_header,
        "",
        *rendered_menu,
        "",
        bot_rule,
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# The Concept Section Narrative
# Grounded in Thesis methodology.tex (lines 94-142)
# ---------------------------------------------------------------------------

CONCEPT_CHAPTERS: list[dict[str, Any]] = [
    {
        "id": "1",
        "title": "The Unfamiliar Territory & Partitioning",
        "subtitle": "The Continent & Independent Cities -> Dataset & Partitions",
        "thesis_quote": (
            '"Imagine that a group of explorers arrives at a previously unknown '
            "continent. Their objective is not to find a specific city, mountain, "
            "or river. Instead, their objective is much more difficult: they must "
            "discover whatever is unusual, important, or potentially dangerous "
            "within the territory. The continent is vast. Attempting to explore "
            "everything at once would quickly become impossible. The explorers "
            "therefore divide the territory into independent cities and assign a "
            'team to each one. Each city can now be investigated separately."'
        ),
        "explanation": [
            "In modern machine learning research, datasets used for Network Intrusion "
            "Detection (such as CIC-IDS2017 or UNSW-NB15) are treated as benchmarks for "
            "evaluating models. However, benchmark datasets frequently contain subtle, "
            "unintentional design artefacts: label leakage, artificial separability, "
            "data duplication, and spurious correlations.",
            "",
            "Machine learning models exploit these artefacts as predictive shortcuts -- "
            "achieving deceptive near-perfect benchmark scores while failing to generalize "
            "in real-world operational deployments.",
            "",
            "Auditing a dataset cannot rely on a fixed checklist because the nature, "
            "location, and combination of flaws are unknown in advance. Like an unknown "
            "continent with millions of records and dozens of features, monolithic auditing "
            "would quickly saturate both memory and reasoning context windows.",
            "",
            "ATLAS adopts the thesis's divide-and-conquer strategy: decomposing the vast "
            "dataset continent into independent, auditable partitions (cities) that can be "
            "explored thoroughly and autonomously.",
        ],
    },
    {
        "id": "2",
        "title": "The Aerial Survey & Scouting Leads",
        "subtitle": "Initial Sketch Map & Regions of Interest -> Substrate & Hypotheses",
        "thesis_quote": (
            '"Before sending expeditions into the field, the explorers first sketch an '
            "initial map using the limited information available from aerial observations. "
            "The map is incomplete and likely inaccurate, but it provides enough information "
            "to identify regions that may conceal something worth investigating. Within a "
            "city, several potentially interesting regions are identified... Since resources "
            "are limited, the explorers cannot investigate every region simultaneously. "
            'They must therefore decide which leads are most worth pursuing."'
        ),
        "explanation": [
            "Before launching costly deep investigations, ATLAS constructs an initial "
            "observational representation of each partition. Rather than exposing raw records "
            "to reasoning agents, the system first extracts metadata: feature types, cardinality, "
            "missingness, class distributions, and dependency indicators.",
            "",
            "This information is compressed into a dynamic semantic substrate -- the explorers' "
            "aerial sketch map. The substrate captures weak signals, contradictions, and "
            "unresolved tensions without jumping to premature conclusions.",
            "",
            "From this substrate, the hypothesis generation module formulates competing "
            "interpretations. An observed pattern is not assumed to be a confirmed defect; "
            "instead, multiple candidate explanations coexist while explicitly preserving "
            "uncertainty.",
            "",
            "Because computational and analytical budgets are finite, the hypothesis ranking "
            "module evaluates candidate leads, allocating exploration resources to the highest "
            "value-of-information directions (such as shortcut risks or label leakage).",
        ],
    },
    {
        "id": "3",
        "title": "Expeditions, Workers & Analytical Instruments",
        "subtitle": "Mission Tasks & Field Instruments -> Router, ReAct Workers & Tools",
        "thesis_quote": (
            '"For each selected region, an expedition plan is created. The expedition '
            "leader then divides the mission into smaller tasks and distributes them among "
            "specialized explorers equipped with different instruments. The explorers "
            "venture into the field, collect observations, test local hypotheses, and "
            'return with evidence."'
        ),
        "explanation": [
            "Selected leads are not investigated haphazardly. The Planner first produces a "
            "strategic investigation plan that defines explicit verification questions and "
            "falsification criteria, separating strategy from low-level execution mechanics.",
            "",
            "The Router acts as the expedition leader, decomposing the strategy into bounded "
            "worker tasks. Each Worker agent is given an isolated local context, strictly "
            "preventing bias and cognitive overload.",
            "",
            "Workers do not speculate: they venture into the data equipped with an ecosystem "
            "of 8 specialized analytical tools:",
            "  - feature_summary: Class-conditioned structural overview",
            "  - cardinality_analysis: Discretization and constant behaviors",
            "  - distribution_analysis: Class separability and distributional skew",
            "  - feature_relation: Pairwise correlation and dependency",
            "  - dependency_concentration: Information leakage into narrow subsets",
            "  - shortcut_analysis: Direct predictive leverage estimation",
            "  - neighborhood_consistency: Local feature clustering and label purity",
            "  - duplication_analysis: Dataset-level exact duplicate detection",
            "",
            "Workers follow a disciplined ReAct protocol, interleaving reasoning and tool "
            "usage, producing objective evidence rather than ungrounded narrative claims.",
        ],
    },
    {
        "id": "4",
        "title": "Synthesis, State Evolution & The Unified Atlas",
        "subtitle": "Regional Reports & City Maps -> Aggregation, Memory & Dataset Report",
        "thesis_quote": (
            '"Their findings are combined into a regional report. Once all regional '
            "expeditions have concluded, the city team consolidates the discoveries into "
            "a city-wide map. The explorers then return to headquarters. Using the new "
            "evidence, they refine their understanding of the city, revisit assumptions "
            "from previous expeditions, and identify new regions that may deserve "
            "attention. A new expedition begins. This process repeats across multiple "
            "expeditions... Finally, once every city has been explored, the discoveries "
            "from each expedition are consolidated into a unified atlas representing the "
            'best available understanding of the entire continent."'
        ),
        "explanation": [
            "Exploration findings are consolidated hierarchically to maintain rigorous "
            "evidence provenance:",
            "",
            "1. Hypothesis Aggregation: Worker reports for a hypothesis are combined. "
            "Convergent findings strengthen confidence, while contradictions and gaps are "
            "explicitly preserved rather than smoothed over.",
            "",
            "2. Round Aggregation: Inter-hypothesis synthesis consolidates all hypothesis "
            "outcomes into a canonical round artifact without loss of evidence lineage.",
            "",
            "3. State Evolution: The State Manager conservatively updates the persistent "
            "investigation memory using an append-oriented strategy.",
            "",
            "4. Critic Feedback: A dedicated Critic evaluates the investigation process across "
            "rounds, detecting overconcentration, premature convergence, or diminishing returns.",
            "",
            "5. The Final Atlas: When partition rounds conclude, the final batch auditor produces "
            "a traceable partition report. Finally, the Coverage Builder and Dataset Merger "
            "unify all partition findings into the authoritative dataset-level report: ATLAS -- "
            "a comprehensive, evidence-grounded atlas of dataset structure and shortcut risks.",
        ],
    },
    {
        "id": "5",
        "title": "Analogy vs. Architecture Reference",
        "subtitle": "The Conceptual Explorer Analogy Mapped to Software Architecture",
        "thesis_quote": (
            '"The proposed dataset auditing framework follows exactly the same '
            'divide-and-conquer exploration strategy."'
        ),
        "explanation": [
            "The table below details the exact correspondence between the thesis's "
            "explorer analogy and the implemented research architecture:",
            "",
            "  +-----------------------+-----------------------------+",
            "  | Explorer Analogy      | Implemented ATLAS Component |",
            "  +-----------------------+-----------------------------+",
            "  | Unknown Continent     | Complete Benchmark Dataset  |",
            "  | Independent Cities    | Dataset Partitions (Slices) |",
            "  | Aerial Observations   | Metadata Extraction Layer   |",
            "  | Initial Sketch Map    | Semantic Substrate & Memory |",
            "  | Regions of Interest   | Formulated Hypotheses       |",
            "  | Deciding Leads        | Hypothesis Ranking Module   |",
            "  | Expedition Plan       | Top Hypothesis Planner      |",
            "  | Expedition Leader     | Router & Task Allocator     |",
            "  | Field Explorers       | ReAct Worker Agents         |",
            "  | Specialized Tools     | 8 Analytical Tools Ecosystem|",
            "  | Field Observations    | Traceable Evidence Blocks   |",
            "  | Regional Report       | Hypothesis-Level Aggregation|",
            "  | City-Wide Map Update  | State Manager (Persistent)  |",
            "  | HQ Expedition Review  | Critic Feedback Module      |",
            "  | Next Expeditions      | Multi-Round Iterative Loop  |",
            "  | The Completed Atlas   | Final Dataset Audit Report  |",
            "  +-----------------------+-----------------------------+",
            "",
            "Every component in ATLAS is engineered for transparency and traceability: "
            "any finding in the final atlas can be traced back through hypothesis plans "
            "down to the exact tool call and dataset row slice that produced it.",
        ],
    },
]


def render_concept_toc() -> str:
    """Render the Concept Table of Contents screen."""
    use_color = is_color_supported()
    top_rule = _rule("=", "ochre")
    sub_rule = _subtle_rule("-", "brown")
    bot_rule = _rule("=", "ochre")

    title = "ATLAS: THE CONCEPT -- Dataset Auditing as Territory Exploration"
    if use_color:
        title = style(title, "amber", bold=True)

    header_lines = [
        f"  {title}",
        "",
        fill(
            'In the research thesis "Auditing NIDS Datasets Using LLM Agents", '
            "dataset auditing is framed not as a static checklist of rules, but "
            "as the systematic, evidence-driven exploration of an unfamiliar "
            "territory.",
            width=WIDTH - 4,
            initial_indent="  ",
            subsequent_indent="  ",
        ),
    ]

    chapter_lines: list[str] = []
    for chap in CONCEPT_CHAPTERS:
        cid = chap["id"]
        ctitle = chap["title"]
        csub = chap["subtitle"]
        if use_color:
            chapter_lines.append(f"  {style(f'[{cid}]', 'gold', bold=True)} {style(ctitle, 'amber', bold=True)}")
            chapter_lines.append(f"      {style(csub, 'muted')}")
        else:
            chapter_lines.append(f"  [{cid}] {ctitle}")
            chapter_lines.append(f"      {csub}")
        chapter_lines.append("")

    nav_title = "Navigation"
    if use_color:
        nav_title = style(nav_title, "gold", bold=True)

    nav_lines = [
        f"  {nav_title}:",
        "  [A] Read Full Narrative (All Chapters sequentially)",
        "  [1-5] Jump directly to a Chapter",
        "  [B] Return to Welcome Menu",
    ]
    if use_color:
        nav_lines = [
            f"  {nav_title}:",
            f"  {style('[A]', 'gold', bold=True)} Read Full Narrative (All Chapters sequentially)",
            f"  {style('[1-5]', 'gold', bold=True)} Jump directly to a Chapter",
            f"  {style('[B]', 'gold', bold=True)} Return to Welcome Menu",
        ]

    sections = [
        top_rule,
        *header_lines,
        sub_rule,
        "",
        "  Chapters:",
        "",
        *chapter_lines,
        sub_rule,
        *nav_lines,
        bot_rule,
    ]
    return "\n".join(sections)


def render_concept_chapter(chapter_idx: int) -> str:
    """Render a single concept chapter (0-indexed)."""
    if not (0 <= chapter_idx < len(CONCEPT_CHAPTERS)):
        chapter_idx = 0

    chap = CONCEPT_CHAPTERS[chapter_idx]
    use_color = is_color_supported()
    top_rule = _rule("=", "ochre")
    sub_rule = _subtle_rule("-", "brown")
    bot_rule = _rule("=", "ochre")

    cid = chap["id"]
    ctitle = chap["title"]
    csub = chap["subtitle"]
    quote = chap["thesis_quote"]
    explanation = chap["explanation"]

    header = f"  Chapter {cid} of {len(CONCEPT_CHAPTERS)}: {ctitle}"
    if use_color:
        header = f"  {style(f'Chapter {cid} of {len(CONCEPT_CHAPTERS)}:', 'gold')} {style(ctitle, 'amber', bold=True)}"

    sub_header = f"  {csub}"
    if use_color:
        sub_header = f"  {style(csub, 'muted')}"

    wrapped_quote = fill(
        quote,
        width=WIDTH - 6,
        initial_indent="    ",
        subsequent_indent="    ",
    )
    if use_color:
        wrapped_quote = "\n".join(
            style(line, "ochre", dim=True) for line in wrapped_quote.splitlines()
        )

    body_lines: list[str] = []
    for paragraph in explanation:
        if not paragraph:
            body_lines.append("")
        elif paragraph.startswith("  "):
            # Indented list or table row
            if use_color:
                body_lines.append(style(paragraph, "light_grey"))
            else:
                body_lines.append(paragraph)
        else:
            wrapped = fill(
                paragraph,
                width=WIDTH - 4,
                initial_indent="  ",
                subsequent_indent="  ",
            )
            if use_color:
                body_lines.append("\n".join(style(line, "light_grey") for line in wrapped.splitlines()))
            else:
                body_lines.append(wrapped)

    nav_items = []
    if chapter_idx < len(CONCEPT_CHAPTERS) - 1:
        nav_items.append("[N] Next Chapter")
    if chapter_idx > 0:
        nav_items.append("[P] Previous Chapter")
    nav_items.append("[T] Table of Contents")
    nav_items.append("[B] Back to Welcome Menu")

    rendered_nav = "  " + "  |  ".join(nav_items)
    if use_color:
        rendered_nav = "  " + "  |  ".join(
            re.sub(r"\[([A-Z0-9])\]", lambda m: style(f"[{m.group(1)}]", "gold", bold=True), item)
            for item in nav_items
        )

    sections = [
        top_rule,
        header,
        sub_header,
        sub_rule,
        "",
        "  Thesis Foundation:",
        wrapped_quote,
        "",
        sub_rule,
        "",
        *body_lines,
        "",
        sub_rule,
        rendered_nav,
        bot_rule,
    ]
    return "\n".join(sections)


def render_all_concept_chapters() -> str:
    """Render all concept chapters consecutively for continuous reading or scripting."""
    output = [
        _rule("=", "ochre"),
        "  ATLAS: THE CONCEPT -- FULL NARRATIVE",
        _rule("=", "ochre"),
        "",
    ]
    for i in range(len(CONCEPT_CHAPTERS)):
        output.append(render_concept_chapter(i))
        output.append("")
    return "\n".join(output)


# ---------------------------------------------------------------------------
# How to Use ATLAS Section
# Grounded in repository structure, scripts, and verified CLI tools
# ---------------------------------------------------------------------------


def render_usage_screen() -> str:
    """Render practical, verified operational guidance for using ATLAS."""
    from interface.how_to_use import get_non_interactive_usage_guide
    return get_non_interactive_usage_guide()
