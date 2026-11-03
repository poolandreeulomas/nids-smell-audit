"""Unit and integration tests for the Thesis Experiments CLI section in ATLAS.

Validates:
1. Welcome screen & Main menu integration ([4] Thesis Experiments).
2. Navigation state machine and screen transitions.
3. 15-run audited corpus inventory and forensic detail screens.
4. Scientific disclosure of batch status (final_batch_auditor root cause).
5. Discrepancy explanation (14 vs 15 runs, conceptual worker counts).
6. Figures & Tables catalog, metadata, and OS viewer action ([O]).
7. How to Use documentation integration.
8. Terminal line width constraints (WIDTH <= 68).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch
import pytest

from interface.cli import NidsAgentCli
from interface.how_to_use import get_category_items
from interface.terminal_ui import render_main_menu
from interface.welcome import render_welcome_screen
from interface.thesis_experiments import (
    CORPUS_RUNS,
    FIGURES_CATALOG,
    SECTIONS,
    TABLES_CATALOG,
    get_figures_dir,
    open_figure_file,
    render_figure_detail,
    render_figures_menu,
    render_run_detail,
    render_run_inventory,
    render_table_detail,
    render_thesis_experiments_menu,
    render_thesis_section,
    strip_ansi,
)


# ===========================================================================
# 1. Menu Presentation & Width Constraint Tests
# ===========================================================================


def test_welcome_screen_presents_thesis_experiments_option():
    screen = strip_ansi(render_welcome_screen())
    assert "[4] Thesis Experiments" in screen
    assert "Empirical evaluation: methodology, corpus & results." in screen
    for line in screen.splitlines():
        assert len(line) <= 68


def test_main_menu_presents_thesis_experiments_option():
    menu = strip_ansi(
        render_main_menu(
            model_name="gpt-4.1-mini",
            dataset_name="demo.csv",
            trace_enabled=False,
            max_steps=10,
            evaluation_window=5,
            stored_runs_count=0,
            has_cli_run=False,
        )
    )
    assert "[4] Thesis Experiments" in menu
    assert "Empirical evaluation: methodology, 15-run corpus" in menu
    for line in menu.splitlines():
        assert len(line) <= 68


def test_all_thesis_experiment_screens_conform_to_width_limit():
    screens = [
        render_thesis_experiments_menu(),
        render_run_inventory(),
        render_figures_menu(),
    ]
    for sec in SECTIONS:
        screens.append(render_thesis_section(sec["id"]))
    for fig in FIGURES_CATALOG:
        screens.append(render_figure_detail(fig["id"]))
    for tbl in TABLES_CATALOG:
        screens.append(render_table_detail(tbl["id"]))
    for run in CORPUS_RUNS:
        screens.append(render_run_detail(run["run_id"]))

    for screen_text in screens:
        plain = strip_ansi(screen_text)
        for line in plain.splitlines():
            assert len(line) <= 68, f"Line exceeds 68 chars ({len(line)}): {line}"


# ===========================================================================
# 2. Navigation Routing Tests
# ===========================================================================


def test_welcome_menu_selection_routes_to_thesis_experiments(monkeypatch):
    cli = NidsAgentCli(initial_screen="welcome")
    cli._render = lambda content: None
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "4")
    next_screen = cli._welcome_menu()
    assert next_screen == "thesis_experiments"


def test_main_menu_selection_routes_to_thesis_experiments(monkeypatch):
    cli = NidsAgentCli(initial_screen="main")
    cli._render = lambda content: None
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "4")
    next_screen = cli._main_menu()
    assert next_screen == "thesis_experiments"


def test_thesis_experiments_menu_routes_to_sections(monkeypatch):
    cli = NidsAgentCli(initial_screen="thesis_experiments")
    cli._render = lambda content: None

    for i in range(1, len(SECTIONS) + 1):
        monkeypatch.setattr(cli, "_read_menu_choice", lambda valid, choice=str(i): choice)
        next_screen = cli._thesis_experiments_menu()
        assert next_screen == "thesis_exp_section"
        assert cli._thesis_exp_section_idx == i - 1


def test_thesis_experiments_menu_routes_to_inventory_and_figures(monkeypatch):
    cli = NidsAgentCli(initial_screen="thesis_experiments")
    cli._render = lambda content: None

    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "I")
    assert cli._thesis_experiments_menu() == "thesis_exp_runs"

    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "F")
    assert cli._thesis_experiments_menu() == "thesis_exp_figures"

    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "B")
    assert cli._thesis_experiments_menu() == "welcome"

    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "M")
    assert cli._thesis_experiments_menu() == "main"


def test_section_menu_next_and_previous_paging(monkeypatch):
    cli = NidsAgentCli(initial_screen="thesis_exp_section")
    cli._render = lambda content: None
    cli._thesis_exp_section_idx = 0

    # Advance to section 1
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "N")
    assert cli._thesis_exp_section_menu() == "thesis_exp_section"
    assert cli._thesis_exp_section_idx == 1

    # Return to section 0
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "P")
    assert cli._thesis_exp_section_menu() == "thesis_exp_section"
    assert cli._thesis_exp_section_idx == 0

    # P at 0 does not decrement below 0
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "P")
    assert cli._thesis_exp_section_menu() == "thesis_exp_section"
    assert cli._thesis_exp_section_idx == 0

    # T returns to TOC
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "T")
    assert cli._thesis_exp_section_menu() == "thesis_experiments"


# ===========================================================================
# 3. 15-Run Corpus & Forensic Disclosure Tests
# ===========================================================================


def test_corpus_inventory_contains_all_15_runs():
    assert len(CORPUS_RUNS) == 15
    run_ids = [r["run_id"] for r in CORPUS_RUNS]
    expected_ids = [
        "050", "053", "064", "067", "070",
        "071", "072", "073", "074", "075",
        "076", "077", "080", "081", "082",
    ]
    assert run_ids == expected_ids

    inventory_text = strip_ansi(render_run_inventory())
    for rid in expected_ids:
        assert f"[{rid}]" in inventory_text


def test_run_detail_discloses_batch_status_accurately():
    # Completed run (050)
    detail_050 = strip_ansi(render_run_detail("050"))
    assert "Run 050 Detail" in detail_050
    assert "Friday-Morning" in detail_050
    assert "COMPLETED" in detail_050
    assert "3 of 3 (100% complete)" in detail_050
    assert "10 transitions persisted" in detail_050

    # Run with failed post-batch final_batch_auditor (071)
    detail_071 = strip_ansi(render_run_detail("071"))
    assert "Run 071 Detail" in detail_071
    assert "Tuesday" in detail_071
    assert "FAILED" in detail_071
    # Transparent scientific explanation of final_batch_auditor failure
    assert "post-batch final_batch_auditor formatting step" in detail_071
    assert "investigative cycle completed normally" in detail_071
    assert "all 3 rounds" in detail_071
    assert "27 worker tasks finished" in detail_071
    assert "valid and included in the thesis results" in detail_071


def test_corpus_runs_navigation_end_to_end(monkeypatch):
    cli = NidsAgentCli(initial_screen="thesis_exp_runs")
    cli._render = lambda content: None

    # Select run 071
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "071")
    assert cli._thesis_exp_runs_menu() == "thesis_exp_run_detail"
    assert cli._thesis_exp_selected_run_id == "071"

    # From detail, press I to go back to run inventory
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "I")
    assert cli._thesis_exp_run_detail_menu() == "thesis_exp_runs"


# ===========================================================================
# 4. Figures & Tables Inspection and OS Viewer Tests
# ===========================================================================


def test_figures_menu_contains_all_figures_and_tables():
    menu_text = strip_ansi(render_figures_menu())
    assert "Figure 1: Global Tool Allocation" in menu_text
    assert "Figure 4A: Weekday Radar Comparison" in menu_text
    assert "Figure 6: Reproducibility Ladder" in menu_text
    assert "Figure 10: Literature Recovery Matrix" in menu_text

    assert "Table 1: Evaluation Overview" in menu_text
    assert "Table 3: Reproducibility Summary" in menu_text
    assert "Table 7: Literature Flaw Validation Summary" in menu_text


def test_figure_detail_screen_metadata():
    detail_fig1 = strip_ansi(render_figure_detail("1"))
    assert "Figure 1: Global Tool Allocation" in detail_fig1
    assert "Thesis Caption:" in detail_fig1
    assert "Research Purpose:" in detail_fig1
    assert "Key Findings & Empirical Observations:" in detail_fig1
    assert "Figure_01_Global_Tool_Allocation.png" in detail_fig1
    assert "Open Viewer" in detail_fig1 or "Open" in detail_fig1


def test_table_detail_screen_renders_data():
    t1 = strip_ansi(render_table_detail("T1"))
    assert "Table 1: Evaluation Overview" in t1
    assert "Total Evaluation Runs" in t1
    assert "15" in t1
    assert "405 (27 workers x 15 runs)" in t1

    t3 = strip_ansi(render_table_detail("T3"))
    assert "Table 3: Reproducibility Summary" in t3
    assert "0.78" in t3
    assert "0.88" in t3
    assert "1.00" in t3
    assert "0.38" in t3


def test_figure_file_resolution_and_open_action(monkeypatch):
    fig_dir = get_figures_dir()
    assert fig_dir.exists()
    assert (fig_dir / "Figure_01_Global_Tool_Allocation.png").exists()

    # Mock system opener to prevent launching GUI windows during test
    if sys.platform.startswith("win"):
        mock_open = MagicMock()
        monkeypatch.setattr(os, "startfile", mock_open, raising=False)
        ok, msg = open_figure_file("1")
        assert ok is True
        assert "Figure_01_Global_Tool_Allocation.png" in msg
        mock_open.assert_called_once()
    else:
        with patch("subprocess.run") as mock_sub:
            ok, msg = open_figure_file("1")
            assert ok is True
            mock_sub.assert_called_once()


def test_figure_navigation_in_cli(monkeypatch):
    cli = NidsAgentCli(initial_screen="thesis_exp_figures")
    cli._render = lambda content: None

    # Select figure 6 (7th item in FIGURES_CATALOG due to 4A, 4B, 4C)
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "6")
    assert cli._thesis_exp_figures_menu() == "thesis_exp_figure_detail"
    assert cli._thesis_exp_figure_idx == 7  # 8th figure in catalog (index 7)

    # Open figure action [O]
    monkeypatch.setattr("interface.cli.open_figure_file", lambda key: (True, "Mock opened"))
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "O")
    assert cli._thesis_exp_figure_detail_menu() == "thesis_exp_figure_detail"
    assert cli._thesis_exp_feedback_msg == "Mock opened"

    # Next figure [N]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "N")
    assert cli._thesis_exp_figure_detail_menu() == "thesis_exp_figure_detail"
    assert cli._thesis_exp_figure_idx == 8

    # Back to figures catalog [F]
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: "F")
    assert cli._thesis_exp_figure_detail_menu() == "thesis_exp_figures"


# ===========================================================================
# 5. Scientific Discrepancy & Academic Rigor Tests
# ===========================================================================


def test_section_3_explains_14_vs_15_runs_discrepancy():
    sec3_text = strip_ansi(render_thesis_section("3"))
    assert "Discrepancy Clarification: 14 vs 15 Runs" in sec3_text
    assert "validate_corpus.py" in sec3_text
    assert "082" in sec3_text
    assert "Friday-PortScan" in sec3_text
    assert "results.tex" in sec3_text


def test_section_4_and_table_3_note_qualitative_nature_of_reproducibility():
    sec4_text = strip_ansi(render_thesis_section("4"))
    assert "Reproducibility Ladder" in sec4_text
    assert "0.78" in sec4_text
    assert "0.88" in sec4_text
    assert "1.00" in sec4_text
    assert "Literature Validation" in sec4_text
    assert "16 Benchmark Flaws" in sec4_text


def test_section_7_reflects_empirical_expansion_priorities():
    sec7_text = strip_ansi(render_thesis_section("7"))
    norm_text = " ".join(sec7_text.split())

    # Time and resource constraints & initial study framing
    assert "Time and Resource Constraints" in norm_text
    assert "initial empirical study" in norm_text
    assert "15.5 minutes" in norm_text
    assert "strengthen the empirical evidence by systematically expanding experimental coverage" in norm_text

    # Three principal empirical limitations clearly distinguished
    assert "Limited Repetitions per Partition" in norm_text
    assert "Friday-Morning has four runs" in norm_text
    assert "seven partitions have only a single execution" in norm_text
    assert "Limited Partition Coverage" in norm_text
    assert "Limited Dataset Diversity" in norm_text
    assert "Repetitions address stochastic variability within a condition" in norm_text
    assert "additional partitions improve scenario coverage across traffic profiles" in norm_text
    assert "additional datasets improve the breadth of cross-benchmark generalization" in norm_text

    # Prioritized future experimental plan (in exact order)
    pos_step1 = norm_text.find("1. Increase Repetitions on Existing Partitions")
    pos_step2 = norm_text.find("2. Expand Partition Coverage")
    pos_step3 = norm_text.find("3. Expand Dataset Coverage")
    pos_step4 = norm_text.find("4. Strengthen Statistical & Reproducibility Procedures")
    assert pos_step1 != -1 and pos_step2 != -1 and pos_step3 != -1 and pos_step4 != -1
    assert pos_step1 < pos_step2 < pos_step3 < pos_step4

    # Sample sizes as subsequent design decision, not arbitrary target
    assert "power analysis and experimental design in subsequent work" in norm_text

    # Removal of ungrounded significance claims
    assert "p < 0.01" not in norm_text

    # Secondary limitations and post-batch finalization clarification
    assert "Secondary Considerations & Technological Horizons" in norm_text
    assert "Tabular Flow Data Scope" in norm_text
    assert "Fixed Investigation Lifecycle" in norm_text
    assert "post-investigation finalization issue in final_batch_auditor" in norm_text
    assert "completed and persisted" in norm_text


# ===========================================================================
# 6. How to Use Documentation Integration Test
# ===========================================================================


def test_how_to_use_reports_category_documents_thesis_experiments():
    reports_topics = get_category_items("reports")
    eval_topic = next((t for t in reports_topics if t["id"] == "formal_evaluation_pipeline"), None)
    assert eval_topic is not None

    l1_text = " ".join(eval_topic["level1_orientation"])
    assert "[4] Thesis Experiments" in l1_text
    assert "Welcome Screen" in l1_text
    assert "Main Research Console" in l1_text

    l2_text = " ".join(eval_topic["level2_operational"])
    assert "Research Overview" in l2_text
    assert "Evaluation Corpus & Run Inventory" in l2_text
    assert "[O] Open Figure File" in l2_text or "[O]" in l2_text
    assert "validate_corpus.py" in l2_text

    l3_text = " ".join(eval_topic["level3_technical"])
    assert "15 runs across 10 partitions" in l3_text
    assert "final_batch_auditor" in l3_text
    assert "14 vs 15 Runs Discrepancy" in l3_text


# ===========================================================================
# 7. End-to-End CLI Navigation Simulation
# ===========================================================================


def test_simulated_user_session_end_to_end(monkeypatch):
    cli = NidsAgentCli(initial_screen="welcome")
    visited_screens = []
    cli._render = lambda content: visited_screens.append(cli._current_screen)

    # User journey:
    # 1. Welcome -> enter '4' (Thesis Experiments)
    # 2. Thesis Experiments -> enter '3' (Corpus section)
    # 3. Section 3 -> enter 'I' (Run Inventory)
    # 4. Inventory -> enter '071' (Run 071 Detail)
    # 5. Run 071 Detail -> enter 'I' (Back to Inventory)
    # 6. Inventory -> enter 'T' (Back to TOC)
    # 7. Thesis Experiments -> enter 'F' (Figures catalog)
    # 8. Figures catalog -> enter '1' (Figure 1 detail)
    # 9. Figure 1 detail -> enter 'F' (Back to Figures)
    # 10. Figures catalog -> enter 'T' (Back to TOC)
    # 11. Thesis Experiments -> enter 'B' (Welcome screen)
    # 12. Welcome -> enter 'Q' (Quit)
    inputs = iter([
        "4",     # 1. welcome -> thesis_experiments
        "3",     # 2. thesis_experiments -> thesis_exp_section (Section 3)
        "I",     # 3. section -> thesis_exp_runs
        "071",   # 4. runs -> thesis_exp_run_detail
        "I",     # 5. run detail -> thesis_exp_runs
        "T",     # 6. runs -> thesis_experiments
        "F",     # 7. thesis_experiments -> thesis_exp_figures
        "1",     # 8. figures -> thesis_exp_figure_detail
        "F",     # 9. figure detail -> thesis_exp_figures
        "T",     # 10. figures -> thesis_experiments
        "B",     # 11. thesis_experiments -> welcome
        "Q",     # 12. welcome -> quit
    ])
    monkeypatch.setattr(cli, "_read_menu_choice", lambda valid: next(inputs))

    cli.run()

    expected_sequence = [
        "welcome",
        "thesis_experiments",
        "thesis_exp_section",
        "thesis_exp_runs",
        "thesis_exp_run_detail",
        "thesis_exp_runs",
        "thesis_experiments",
        "thesis_exp_figures",
        "thesis_exp_figure_detail",
        "thesis_exp_figures",
        "thesis_experiments",
        "welcome",
    ]
    assert visited_screens == expected_sequence
    assert cli._running is False
