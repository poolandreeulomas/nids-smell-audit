"""Tests for the ATLAS terminal welcome experience, concept section, and navigation."""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest

from interface.cli import NidsAgentCli, SessionConfig, main
from interface.welcome import (
    ATLAS_DESCRIPTION,
    ATLAS_DESCRIPTOR,
    ATLAS_NAME,
    ATLAS_TAGLINE,
    ATLAS_VERSION,
    CONCEPT_CHAPTERS,
    get_ascii_logo,
    is_color_supported,
    render_all_concept_chapters,
    render_concept_chapter,
    render_concept_toc,
    render_usage_screen,
    render_welcome_screen,
    strip_ansi,
    style,
)


# ===========================================================================
# 1. Welcome Screen Rendering Tests
# ===========================================================================


def test_ascii_logo_contains_brand_and_mountain_geometry():
    logo_plain = get_ascii_logo(colored=False)
    assert "/\\" in logo_plain
    assert "/_/    \\__/\\_\\" in logo_plain
    assert "A  T  L  A  S" in logo_plain
    assert ATLAS_DESCRIPTOR in logo_plain
    assert ATLAS_TAGLINE in logo_plain

    # Verify line width stays within standard 68-char boundary
    for line in logo_plain.splitlines():
        assert len(line) <= 68


def test_welcome_screen_renders_all_required_components():
    screen = render_welcome_screen(dataset_name="demo_partition.csv")
    screen_plain = strip_ansi(screen)

    # Visual identity & wordmark
    assert "A  T  L  A  S" in screen_plain
    assert ATLAS_DESCRIPTOR in screen_plain
    assert ATLAS_TAGLINE in screen_plain

    # Short accurate description
    assert "ATLAS is an agent-based framework for systematic dataset" in screen_plain
    assert "auditing." in screen_plain
    assert "hypothesis-driven analysis" in screen_plain
    assert "tool-assisted exploration" in screen_plain
    assert "evidence collection" in screen_plain

    # Metadata & version
    assert ATLAS_VERSION in screen_plain
    assert "demo_partition.csv" in screen_plain

    # Menu options
    assert "[1] Enter ATLAS" in screen_plain
    assert "[2] The Concept" in screen_plain
    assert "[3] How to Use ATLAS" in screen_plain
    assert "[0] Exit" in screen_plain


def test_welcome_screen_width_bounds():
    screen = render_welcome_screen()
    screen_plain = strip_ansi(screen)
    for line in screen_plain.splitlines():
        assert len(line) <= 68


# ===========================================================================
# 2. Concept Section Rendering & Thesis Faithfulness Tests
# ===========================================================================


def test_concept_chapters_grounded_in_thesis_analogy():
    assert len(CONCEPT_CHAPTERS) == 5

    # Chapter 1: Territory & Cities -> Dataset & Partitions
    chap1 = CONCEPT_CHAPTERS[0]
    assert "Unfamiliar Territory" in chap1["title"]
    assert "unknown continent" in chap1["thesis_quote"].lower()
    chap1_text = " ".join(chap1["explanation"])
    assert "CIC-IDS2017" in chap1_text or "benchmark" in chap1_text
    assert "shortcut" in chap1_text
    assert "divide-and-conquer" in chap1_text

    # Chapter 2: Aerial Survey & Leads -> Substrate & Hypotheses
    chap2 = CONCEPT_CHAPTERS[1]
    assert "Aerial Survey" in chap2["title"]
    assert "sketch an initial map" in chap2["thesis_quote"].lower()
    chap2_text = " ".join(chap2["explanation"])
    assert "semantic substrate" in chap2_text
    assert "hypothesis generation" in chap2_text
    assert "hypothesis ranking" in chap2_text

    # Chapter 3: Expeditions, Workers & Analytical Instruments
    chap3 = CONCEPT_CHAPTERS[2]
    assert "Analytical Instruments" in chap3["title"]
    assert "specialized explorers equipped with different instruments" in chap3["thesis_quote"].lower()
    chap3_text = " ".join(chap3["explanation"])
    assert "Router" in chap3_text
    assert "Worker" in chap3_text
    assert "ReAct" in chap3_text

    # Verify all 8 analytical tools are explicitly documented
    for tool_name in [
        "feature_summary",
        "cardinality_analysis",
        "distribution_analysis",
        "feature_relation",
        "dependency_concentration",
        "shortcut_analysis",
        "neighborhood_consistency",
        "duplication_analysis",
    ]:
        assert tool_name in chap3_text

    # Chapter 4: Synthesis, State Evolution & The Unified Atlas
    chap4 = CONCEPT_CHAPTERS[3]
    assert "Unified Atlas" in chap4["title"]
    assert "consolidated into a unified atlas" in chap4["thesis_quote"].lower()
    chap4_text = " ".join(chap4["explanation"])
    assert "Hypothesis Aggregation" in chap4_text
    assert "State Manager" in chap4_text
    assert "Critic" in chap4_text
    assert "Coverage Builder" in chap4_text or "Dataset Merger" in chap4_text

    # Chapter 5: Analogy vs Architecture Mapping Table
    chap5 = CONCEPT_CHAPTERS[4]
    chap5_text = " ".join(chap5["explanation"])
    assert "Unknown Continent" in chap5_text
    assert "Complete Benchmark Dataset" in chap5_text
    assert "Specialized Tools" in chap5_text
    assert "The Completed Atlas" in chap5_text


def test_concept_toc_renders_navigation():
    toc = render_concept_toc()
    toc_plain = strip_ansi(toc)
    assert "ATLAS: THE CONCEPT" in toc_plain
    assert "[1] The Unfamiliar Territory" in toc_plain
    assert "[2] The Aerial Survey" in toc_plain
    assert "[3] Expeditions, Workers" in toc_plain
    assert "[4] Synthesis, State Evolution" in toc_plain
    assert "[5] Analogy vs. Architecture" in toc_plain
    assert "[A] Read Full Narrative" in toc_plain
    assert "[B] Return to Welcome Menu" in toc_plain


def test_concept_individual_chapters_render_navigation_controls():
    # First chapter: has Next, but no Prev
    chap0 = strip_ansi(render_concept_chapter(0))
    assert "[N] Next Chapter" in chap0
    assert "[P] Previous Chapter" not in chap0
    assert "[T] Table of Contents" in chap0
    assert "[B] Back to Welcome Menu" in chap0

    # Middle chapter: has both Next and Prev
    chap2 = strip_ansi(render_concept_chapter(2))
    assert "[N] Next Chapter" in chap2
    assert "[P] Previous Chapter" in chap2

    # Last chapter: has Prev, but no Next
    chap4 = strip_ansi(render_concept_chapter(4))
    assert "[N] Next Chapter" not in chap4
    assert "[P] Previous Chapter" in chap4


def test_render_all_concept_chapters_combines_full_story():
    full_narrative = strip_ansi(render_all_concept_chapters())
    assert "ATLAS: THE CONCEPT -- FULL NARRATIVE" in full_narrative
    assert "Chapter 1 of 5" in full_narrative
    assert "Chapter 5 of 5" in full_narrative


# ===========================================================================
# 3. How to Use ATLAS Rendering Tests
# ===========================================================================


def test_usage_screen_contains_verified_commands_and_paths():
    usage = render_usage_screen()
    usage_plain = strip_ansi(usage)

    # Prerequisites & Environment
    assert "pip install -r requirements.txt" in usage_plain
    assert "OPENAI_API_KEY" in usage_plain

    # Interactive launcher
    assert "python interface/cli.py" in usage_plain

    # Non-interactive / Batch orchestrator
    assert "main_phase3a_batch()" in usage_plain
    assert "phase3_runtime.orchestrator --mode full_batch" in usage_plain

    # Component CLIs
    assert "python -m semantic_extraction.cli" in usage_plain
    assert "python -m worker.cli" in usage_plain
    assert "python -m aggregation.cli" in usage_plain
    assert "python -m final_batch_auditor.cli" in usage_plain

    # Verified artifact directories
    assert "logs/final_batch_report_runs/" in usage_plain
    assert "logs/round_report_runs/" in usage_plain
    assert "logs/phase3a_runtime_runs/" in usage_plain
    assert "logs/worker_runs/" in usage_plain
    assert "docs/batch_reports/" in usage_plain
    assert "final_dataset/" in usage_plain


# ===========================================================================
# 4. Interactive Navigation & State Transition Tests
# ===========================================================================


def test_welcome_menu_routes_to_main_menu(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli._get_selected_dataset_label = lambda: "test_dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._quit = lambda: None
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "1")

    next_screen = cli._welcome_menu()
    assert next_screen == "main"


def test_welcome_menu_routes_to_concept(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli._get_selected_dataset_label = lambda: "test_dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._quit = lambda: None
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "2")

    next_screen = cli._welcome_menu()
    assert next_screen == "concept"


def test_welcome_menu_routes_to_usage(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli._get_selected_dataset_label = lambda: "test_dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._quit = lambda: None
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "3")

    next_screen = cli._welcome_menu()
    assert next_screen == "usage"


def test_welcome_menu_exit_with_zero_or_q(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli._get_selected_dataset_label = lambda: "test_dataset.csv"
    cli._render = lambda content: None
    cli._running = True
    cli._quit = lambda: setattr(cli, "_running", False)

    # Choice "0"
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "0")
    next_screen = cli._welcome_menu()
    assert next_screen is None
    assert cli._running is False

    # Choice "Q"
    cli._running = True
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "Q")
    next_screen = cli._welcome_menu()
    assert next_screen is None
    assert cli._running is False


def test_main_menu_can_return_to_welcome_screen(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(dataset_name="dataset.csv")
    cli._last_run = None
    cli._running = True
    cli._render = lambda content: None
    cli._count_persisted_runs = lambda: 0
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._quit = lambda: None

    # Choice "B"
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._main_menu() == "welcome"

    # Choice "0"
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "0")
    assert cli._main_menu() == "welcome"

    # Choice "W"
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "W")
    assert cli._main_menu() == "welcome"


def test_concept_navigation_and_return_to_welcome(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli._concept_chapter_idx = 0
    cli._render = lambda content: None
    cli._wait_for_enter = lambda *args: None
    cli._quit = lambda: None

    # TOC -> Chapter 3
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "3")
    next_screen = cli._concept_menu()
    assert next_screen == "concept_chapter"
    assert cli._concept_chapter_idx == 2  # 0-indexed

    # In Chapter 3 -> Next Chapter
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "N")
    next_screen = cli._concept_chapter_menu()
    assert next_screen == "concept_chapter"
    assert cli._concept_chapter_idx == 3

    # In Chapter 4 -> Previous Chapter
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "P")
    next_screen = cli._concept_chapter_menu()
    assert next_screen == "concept_chapter"
    assert cli._concept_chapter_idx == 2

    # In Chapter -> Table of contents
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "T")
    assert cli._concept_chapter_menu() == "concept"

    # From TOC -> Back to welcome
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._concept_menu() == "welcome"


def test_usage_menu_navigation(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli._render = lambda content: None
    cli._quit = lambda: None
    cli._how_to_use_category = "getting_started"
    cli._how_to_use_item_idx = 0
    cli._how_to_use_show_details = False

    # Usage -> Return to welcome
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._usage_menu() == "welcome"

    # Usage -> Enter ATLAS main menu via [M]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "M")
    assert cli._usage_menu() == "main"

    # Usage -> Open Category 1 (Getting Started)
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "1")
    assert cli._usage_menu() == "usage_category"
    assert cli._how_to_use_category == "getting_started"

    # Usage -> Open Category 4 (Components)
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "4")
    assert cli._usage_menu() == "usage_category"
    assert cli._how_to_use_category == "components"

    # Category -> Select Item 1 -> usage_topic
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "1")
    assert cli._usage_category_menu() == "usage_topic"
    assert cli._how_to_use_item_idx == 0

    # Topic -> Toggle details [D]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "D")
    assert cli._usage_topic_menu() == "usage_topic"
    assert cli._how_to_use_show_details is True

    # Topic -> Next Item [N]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "N")
    assert cli._usage_topic_menu() == "usage_topic"
    assert cli._how_to_use_item_idx == 1
    assert cli._how_to_use_show_details is False

    # Topic -> Previous Item [P]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "P")
    assert cli._usage_topic_menu() == "usage_topic"
    assert cli._how_to_use_item_idx == 0

    # Topic -> Back to Category [B]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._usage_topic_menu() == "usage_category"

    # Category -> Back to Usage TOC [B]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    assert cli._usage_category_menu() == "usage"


# ===========================================================================
# 5. Non-Interactive CLI Arguments and Degradation Tests
# ===========================================================================


def test_cli_version_flag_exits_non_interactively(capsys):
    main(["--version"])
    captured = capsys.readouterr()
    assert ATLAS_NAME in captured.out
    assert ATLAS_VERSION in captured.out
    assert ATLAS_DESCRIPTOR in captured.out


def test_cli_concept_flag_exits_non_interactively(capsys):
    main(["--concept"])
    captured = capsys.readouterr()
    assert "ATLAS: THE CONCEPT" in captured.out
    assert "Chapter 1 of 5" in captured.out


def test_cli_usage_flag_exits_non_interactively(capsys):
    main(["--usage"])
    captured = capsys.readouterr()
    assert "HOW TO USE ATLAS" in captured.out
    assert "pip install -r requirements.txt" in captured.out


def test_cli_skip_welcome_starts_at_main():
    cli = NidsAgentCli(initial_screen="main")
    assert cli._current_screen == "main"

    cli_default = NidsAgentCli()
    assert cli_default._current_screen == "welcome"


def test_color_degradation_with_no_color_environment(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert is_color_supported() is False

    styled = style("hello", "ochre", bold=True)
    assert styled == "hello"
    assert "\033" not in styled

    screen = render_welcome_screen()
    assert "\033" not in screen


def test_welcome_menu_invalid_choice_reprompts(monkeypatch, capsys):
    cli = object.__new__(NidsAgentCli)
    cli._get_selected_dataset_label = lambda: "test_dataset.csv"
    cli._render = lambda content: None
    cli._quit = lambda: None

    inputs = iter(["invalid_option", "9", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    next_screen = cli._welcome_menu()
    assert next_screen == "main"
    captured = capsys.readouterr()
    assert "Invalid option." in captured.out


def test_cli_eof_handling_during_run(monkeypatch, capsys):
    cli = NidsAgentCli(initial_screen="welcome")
    cli._render = lambda content: None

    def raise_eof(prompt=""):
        raise EOFError()

    monkeypatch.setattr("builtins.input", raise_eof)

    with pytest.raises(EOFError):
        cli.run()

    # Now verify main() catches EOFError cleanly
    with patch("builtins.input", side_effect=EOFError):
        main([])
    captured = capsys.readouterr()
    assert "Exiting ATLAS" in captured.out


def test_direct_main_phase3a_batch_unaffected():
    import main as main_module
    assert hasattr(main_module, "main_phase3a_batch")
    assert callable(main_module.main_phase3a_batch)
    assert hasattr(main_module, "main")
    assert callable(main_module.main)



def test_main_menu_presents_batch_runtime_option():
    from interface.terminal_ui import render_main_menu
    output = render_main_menu(
        model_name="gpt-4.1-mini",
        dataset_name="test_data.csv",
        trace_enabled=False,
        max_steps=10,
        evaluation_window=5,
        stored_runs_count=0,
        has_cli_run=False,
    )
    assert "[1] Batch Runtime" in output
    assert "Execute and inspect complete batches" in output


def test_main_menu_selection_routes_to_phase3a_runtime(monkeypatch):
    cli = NidsAgentCli(initial_screen="main")
    cli._render = lambda content: None
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "1")
    next_screen = cli._main_menu()
    assert next_screen == "phase3a_runtime"


def test_main_menu_batch_runtime_navigation_end_to_end(monkeypatch):
    cli = NidsAgentCli(initial_screen="main")
    rendered_screens = []
    cli._render = lambda content: rendered_screens.append(content)

    # Sequence:
    # 1. Main menu -> enter '1' (Batch Runtime)
    # 2. Batch runtime menu -> enter 'Q' (Quit)
    choices = iter(["1", "Q"])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: next(choices))

    cli.run()

    # Verify both screens were rendered in order
    assert len(rendered_screens) >= 2
    # Screen 1 is Main Menu with Batch Runtime option
    assert "[1] Batch Runtime" in rendered_screens[0]
    # Screen 2 is ATLAS Batch Runtime submenu
    assert "ATLAS Batch Runtime" in rendered_screens[1]
    assert "[4] Run Full Batch" in rendered_screens[1]
    assert "[1] Run Cognitive Chain" in rendered_screens[1]
    # Verify screen state ended after entering batch runtime
    assert cli._current_screen == "phase3a_runtime"


def test_phase3a_runtime_menu_fast_render_without_heavy_loading(monkeypatch):
    cli = NidsAgentCli(initial_screen="main")
    rendered_screens = []
    cli._render = lambda content: rendered_screens.append(content)
    cli._last_phase3a_runtime_run = None

    # Verify _get_latest_phase3a_runtime_run_context is NOT called during menu display
    def _explode():
        raise AssertionError("Heavy run context loader should not be called to render the menu!")
    monkeypatch.setattr(cli, "_get_latest_phase3a_runtime_run_context", _explode)

    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid_choices: "B")
    ret = cli._phase3a_runtime_menu()
    assert ret == "main"
    assert len(rendered_screens) == 1
    assert "ATLAS Batch Runtime" in rendered_screens[0]
