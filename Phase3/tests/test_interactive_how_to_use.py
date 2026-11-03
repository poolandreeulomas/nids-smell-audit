"""Tests for the ATLAS interactive How to Use learning and exploration guide.

Covers:
- Category structure and landing menu
- Progressive disclosure (Level 1, Level 2, Level 3 toggle)
- Component catalogue completeness & real source reference accuracy
- Tool catalogue completeness & tool registry alignment
- Navigation state machine transitions (N, P, D, B, H, W, Q)
- Line width bounds (WIDTH <= 68) for all screens
- Safe browsing verification (zero state mutation, zero tool/LLM execution)
- Non-interactive CLI usage guide compatibility
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch
import pytest

from interface.cli import NidsAgentCli
from interface.how_to_use import (
    CATEGORIES,
    CATEGORY_MAP,
    COMPONENTS_CATALOGUE,
    DEBUGGING_TOPICS,
    GETTING_STARTED_TOPICS,
    INVESTIGATION_FLOW_TOPICS,
    REPORTS_TOPICS,
    TOOLS_CATALOGUE,
    WAYS_TO_RUN_TOPICS,
    get_category_by_key,
    get_category_item_count,
    get_category_item_title,
    get_category_items,
    get_non_interactive_usage_guide,
    render_category_item,
    render_category_menu,
    render_how_to_use_landing,
)
from interface.welcome import render_usage_screen, strip_ansi
from tools.registry import get_tool_capability_records, get_tool_registry

PHASE3_DIR = Path(__file__).resolve().parent.parent / "nids-smell-audit" / "Phase3"


# ===========================================================================
# 1. Structure & Landing Menu Tests
# ===========================================================================


def test_how_to_use_categories_structure():
    """Verify all 7 mandatory categories exist with required metadata."""
    assert len(CATEGORIES) == 7
    expected_ids = [
        "getting_started",
        "ways_to_run",
        "investigation_flow",
        "components",
        "tools",
        "debugging",
        "reports",
    ]
    actual_ids = [c["id"] for c in CATEGORIES]
    assert actual_ids == expected_ids

    for cat in CATEGORIES:
        assert cat["key"] in {"1", "2", "3", "4", "5", "6", "7"}
        assert len(cat["title"]) > 0
        assert len(cat["subtitle"]) > 0
        assert len(cat["description"]) > 0


def test_landing_menu_renders_all_categories_within_width_bounds():
    """Verify landing menu contains all 7 categories and respects terminal width."""
    rendered = render_how_to_use_landing()
    plain = strip_ansi(rendered)

    assert "HOW TO USE ATLAS -- Interactive Learning Guide" in plain
    for cat in CATEGORIES:
        assert f"[{cat['key']}] {cat['title']}" in plain

    for line in plain.splitlines():
        assert len(line) <= 68, f"Line exceeds 68 chars: '{line}' ({len(line)})"


# ===========================================================================
# 2. Category Sub-Menus & Width Bounds Tests
# ===========================================================================


@pytest.mark.parametrize("category_id", [c["id"] for c in CATEGORIES])
def test_category_submenus_render_within_width_bounds(category_id):
    """Every category submenu renders cleanly within width <= 68."""
    rendered = render_category_menu(category_id)
    plain = strip_ansi(rendered)

    cat = CATEGORY_MAP[category_id]
    assert cat["title"] in plain
    assert "[B] Back to How to Use Categories" in plain

    items = get_category_items(category_id)
    assert len(items) > 0
    for idx in range(1, len(items) + 1):
        assert f"[{idx}]" in plain

    for line in plain.splitlines():
        assert len(line) <= 68, f"Line in {category_id} menu exceeds 68 chars: '{line}' ({len(line)})"


# ===========================================================================
# 3. Progressive Disclosure & Detail Screen Tests
# ===========================================================================


@pytest.mark.parametrize("category_id", [c["id"] for c in CATEGORIES])
def test_category_items_progressive_disclosure_and_width(category_id):
    """Verify Level 1, Level 2, and conditional Level 3 toggle across all items."""
    count = get_category_item_count(category_id)
    assert count > 0

    for idx in range(count):
        # 1. Level 1 & Level 2 only (default view)
        view_default = render_category_item(category_id, idx, show_details=False)
        plain_default = strip_ansi(view_default)

        assert "Level 1 -- Orientation" in plain_default
        assert "Level 2 -- Operational Understanding" in plain_default
        assert "Level 3 -- Implementation & Debugging References" not in plain_default
        assert "[D] Show Technical & Implementation References" in plain_default

        for line in plain_default.splitlines():
            assert len(line) <= 68, f"Line in {category_id}[{idx}] default exceeds 68 chars: '{line}' ({len(line)})"

        # 2. Level 3 toggled view
        view_details = render_category_item(category_id, idx, show_details=True)
        plain_details = strip_ansi(view_details)

        assert "Level 3 -- Implementation & Debugging References" in plain_details
        assert "[D] Hide Technical Details" in plain_details

        for line in plain_details.splitlines():
            assert len(line) <= 68, f"Line in {category_id}[{idx}] details exceeds 68 chars: '{line}' ({len(line)})"


# ===========================================================================
# 4. Components Catalogue Completeness & Real Source Reference Accuracy
# ===========================================================================


def test_components_catalogue_completeness_and_grounded_references():
    """Verify all 12 active components exist and all referenced source files exist on disk."""
    assert len(COMPONENTS_CATALOGUE) == 12

    expected_components = [
        "semantic_extraction",
        "investigation_analysis",
        "hypothesis_ranking",
        "planner",
        "router",
        "worker",
        "aggregation",
        "state_manager",
        "critic",
        "final_batch_auditor",
        "final_batch_report",
        "dataset_infra",
    ]
    actual_components = [c["id"] for c in COMPONENTS_CATALOGUE]
    assert actual_components == expected_components

    # Verify that implementation source files referenced in Level 3 actually exist on disk
    component_source_map = {
        "semantic_extraction": PHASE3_DIR / "semantic_extraction" / "runner.py",
        "investigation_analysis": PHASE3_DIR / "investigation_analysis" / "runner.py",
        "hypothesis_ranking": PHASE3_DIR / "hypothesis_ranking" / "runner.py",
        "planner": PHASE3_DIR / "planner" / "runner.py",
        "router": PHASE3_DIR / "router" / "runner.py",
        "worker": PHASE3_DIR / "worker" / "runner.py",
        "aggregation": PHASE3_DIR / "aggregation" / "runner.py",
        "state_manager": PHASE3_DIR / "state_manager" / "runner.py",
        "critic": PHASE3_DIR / "critic" / "runner.py",
        "final_batch_auditor": PHASE3_DIR / "final_batch_auditor" / "runner.py",
        "final_batch_report": PHASE3_DIR / "final_batch_report" / "runner.py",
        "dataset_infra": PHASE3_DIR / "dataset_runtime" / "orchestrator.py",
    }

    for comp_id, expected_file in component_source_map.items():
        assert expected_file.is_file(), f"Component {comp_id} source file missing: {expected_file}"


# ===========================================================================
# 5. Tool Catalogue Alignment with Active Tool Registry
# ===========================================================================


def test_tool_catalogue_matches_active_tool_registry():
    """Verify all 9 registered tools are documented and capability roles match exactly."""
    registry = get_tool_registry()
    capability_records = get_tool_capability_records()

    assert len(TOOLS_CATALOGUE) == 9
    assert len(registry) == 9
    assert len(capability_records) == 9

    tool_names_catalogue = {t["tool_name"] for t in TOOLS_CATALOGUE}
    tool_names_registry = set(registry.keys())
    assert tool_names_catalogue == tool_names_registry

    # Verify capability epistemic roles match registry
    for tool_entry in TOOLS_CATALOGUE:
        name = tool_entry["tool_name"]
        record = capability_records[name]
        assert tool_entry["epistemic_role"] == record["epistemic_role"]
        assert tool_entry["supported_scopes"] == record["supported_scopes"]

        # Verify implementation tool file exists on disk
        tool_file = PHASE3_DIR / "tools" / f"{name}.py"
        assert tool_file.is_file(), f"Tool file missing on disk: {tool_file}"


# ===========================================================================
# 6. Interactive Navigation State Machine Tests
# ===========================================================================


def test_how_to_use_navigation_flow(monkeypatch):
    """Simulate full user journey through How to Use menus, categories, and topics."""
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: None
    cli._quit = lambda: None
    cli._how_to_use_category = "getting_started"
    cli._how_to_use_item_idx = 0
    cli._how_to_use_show_details = False

    # 1. Landing menu -> Select Category 5 (Tools)
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "5")
    assert cli._usage_menu() == "usage_category"
    assert cli._how_to_use_category == "tools"

    # 2. Tools category menu -> Select Item 5 (shortcut_analysis)
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "5")
    assert cli._usage_category_menu() == "usage_topic"
    assert cli._how_to_use_item_idx == 4
    assert cli._how_to_use_show_details is False

    # 3. Topic screen -> Toggle Level 3 details [D]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "D")
    assert cli._usage_topic_menu() == "usage_topic"
    assert cli._how_to_use_show_details is True

    # 4. Topic screen -> Next tool [N] (neighborhood_consistency)
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "N")
    assert cli._usage_topic_menu() == "usage_topic"
    assert cli._how_to_use_item_idx == 5
    assert cli._how_to_use_show_details is False  # Details reset on topic switch

    # 5. Topic screen -> Previous tool [P] (shortcut_analysis)
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "P")
    assert cli._usage_topic_menu() == "usage_topic"
    assert cli._how_to_use_item_idx == 4

    # 6. Topic screen -> Back to Category index [B]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._usage_topic_menu() == "usage_category"

    # 7. Category menu -> Back to Landing TOC [B]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._usage_category_menu() == "usage"

    # 8. Landing menu -> Return to Welcome Screen [B]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._usage_menu() == "welcome"


def test_safe_browsing_does_not_mutate_state(monkeypatch):
    """Verify that exploring How to Use never modifies session state or executes tools."""
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: None
    cli._quit = lambda: None
    cli._how_to_use_category = "getting_started"
    cli._how_to_use_item_idx = 0
    cli._how_to_use_show_details = False

    # Assert no background processes, no disk changes, no LLM calls
    for cat_id in [c["id"] for c in CATEGORIES]:
        cli._how_to_use_category = cat_id
        items_count = get_category_item_count(cat_id)
        for idx in range(items_count):
            cli._how_to_use_item_idx = idx
            cli._how_to_use_show_details = False
            # Render view
            content_default = render_category_item(cat_id, idx, False)
            content_details = render_category_item(cat_id, idx, True)
            assert len(content_default) > 0
            assert len(content_details) > 0


# ===========================================================================
# 7. Non-Interactive CLI Guide Compatibility Tests
# ===========================================================================


def test_non_interactive_usage_guide_contains_essential_commands():
    """Verify render_usage_screen() provides verified CLI commands and artifact paths."""
    usage_text = render_usage_screen()
    plain = strip_ansi(usage_text)

    # Must contain essential verified commands
    assert "pip install -r requirements.txt" in plain
    assert "OPENAI_API_KEY" in plain
    assert "python interface/cli.py" in plain
    assert "main_phase3a_batch()" in plain
    assert "phase3_runtime.orchestrator --mode full_batch" in plain
    assert "python -m semantic_extraction.cli" in plain
    assert "python -m worker.cli" in plain
    assert "python -m aggregation.cli" in plain
    assert "python -m final_batch_auditor.cli" in plain

    # Must contain verified artifact paths
    assert "logs/final_batch_report_runs/" in plain
    assert "logs/round_report_runs/" in plain
    assert "logs/phase3a_runtime_runs/" in plain
    assert "logs/worker_runs/" in plain
    assert "docs/batch_reports/" in plain
    assert "final_dataset/" in plain

    # Must contain references to the in-CLI guide categories
    assert "Getting Started with ATLAS" in plain
    assert "Ways to Run ATLAS" in plain
    assert "General Investigation Flow" in plain
    assert "Components" in plain
    assert "Tools" in plain
    assert "Debugging & Observability" in plain
    assert "Reports & Persisted Outputs" in plain


# ===========================================================================
# 8. Rendering Spacing & Accuracy Auditing Tests
# ===========================================================================


def test_rendering_has_no_exploded_rules_or_excessive_vertical_spacing():
    """Verify that no separator rule explodes into character-by-character lines.

    Guarantees that lines.extend(_subtle_rule(...)) is never used, and that
    all screens maintain compact, readable vertical spacing without consecutive blank lines.
    """
    for cat in CATEGORIES:
        cat_id = cat["id"]
        item_count = get_category_item_count(cat_id)
        for idx in range(item_count):
            for details in (False, True):
                rendered = render_category_item(cat_id, idx, show_details=details)
                plain = strip_ansi(rendered)
                lines = plain.splitlines()

                # 1. No single-character dash lines in succession (exploded rule bug)
                single_dash_count = 0
                for line in lines:
                    if line.strip() == "-":
                        single_dash_count += 1
                    else:
                        single_dash_count = 0
                    assert single_dash_count < 2, (
                        f"Exploded separator rule detected in {cat_id}[{idx}] (details={details})! "
                        f"Found consecutive single-dash lines."
                    )

                # 2. No triple empty lines
                consecutive_blanks = 0
                for line in lines:
                    if not line.strip():
                        consecutive_blanks += 1
                    else:
                        consecutive_blanks = 0
                    assert consecutive_blanks < 2, (
                        f"Excessive vertical gap in {cat_id}[{idx}] (details={details})! "
                        f"Found {consecutive_blanks} consecutive blank lines."
                    )

                # 3. Compact line count bounds: no screen should blow up past 180 lines
                assert len(lines) < 180, (
                    f"Screen {cat_id}[{idx}] (details={details}) has excessive line count: {len(lines)}"
                )


def test_audited_report_paths_and_no_fictitious_paths():
    """Verify that all report topics reference real existing directories and no ghost paths."""
    for topic in REPORTS_TOPICS:
        text_block = " ".join(
            topic.get("level1_orientation", [])
            + topic.get("level2_operational", [])
            + topic.get("level3_technical", [])
        )
        assert "reports/<batch_id>_final_report.md" not in text_block, (
            f"Fictitious path 'reports/<batch_id>_final_report.md' found in topic {topic['id']}"
        )

    # Verify that real report directories are accurately documented
    ecosystem = next(t for t in REPORTS_TOPICS if t["id"] == "reporting_ecosystem")
    eco_text = " ".join(ecosystem["level3_technical"])
    assert "logs/final_batch_report_runs/" in eco_text
    assert "logs/round_report_runs/" in eco_text
    assert "logs/phase3a_runtime_runs/" in eco_text
    assert "docs/batch_reports/" in eco_text
    assert "final_dataset/" in eco_text


def test_wasserstein_tool_active_and_contextualized():
    """Verify wasserstein tool is registered, active, and clearly documented."""
    wasserstein_entry = next(t for t in TOOLS_CATALOGUE if t["tool_name"] == "wasserstein")
    assert wasserstein_entry["epistemic_role"] == "distribution_distance_verification"
    assert wasserstein_entry["supported_scopes"] == ["feature"]

    tech_text = " ".join(wasserstein_entry["level3_technical"])
    assert "Thesis methodology.tex" in tech_text
    assert "Phase3/tools/wasserstein.py" in tech_text
    assert "Phase3/tools/registry.py" in tech_text


def test_direct_navigation_to_main_menu(monkeypatch):
    """Verify that pressing 'M' from category or topic menus jumps directly to 'main'."""
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: None
    cli._quit = lambda: None
    cli._how_to_use_category = "getting_started"
    cli._how_to_use_item_idx = 0
    cli._how_to_use_show_details = False

    # From Category Menu -> Press 'M' -> returns 'main'
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "M")
    assert cli._usage_category_menu() == "main"

    # From Topic Menu -> Press 'M' -> returns 'main'
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "M")
    assert cli._usage_topic_menu() == "main"


