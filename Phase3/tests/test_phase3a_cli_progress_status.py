from interface.cli import NidsAgentCli, SessionConfig
from interface.terminal_ui import (
    render_aggregation_menu,
    render_critic_menu,
    render_final_batch_auditor_menu,
    render_hypothesis_ranking_menu,
    render_investigation_analysis_menu,
    render_planner_menu,
    render_phase3a_runtime_menu,
    render_router_menu,
    render_semantic_extraction_menu,
    render_state_manager_menu,
    render_tools_menu,
    render_worker_menu,
)


def test_component_menus_hide_available_labels_and_keep_planned_progress_labels():
    semantic_menu = render_semantic_extraction_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    investigation_menu = render_investigation_analysis_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    ranking_menu = render_hypothesis_ranking_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    planner_menu = render_planner_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    router_menu = render_router_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    worker_menu = render_worker_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    aggregation_menu = render_aggregation_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    state_manager_menu = render_state_manager_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    critic_menu = render_critic_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    final_batch_auditor_menu = render_final_batch_auditor_menu(
        dataset_name="dataset.csv",
        model_name="gpt-4.1-mini",
        latest_run_name=None,
    )
    phase3a_runtime_menu = render_phase3a_runtime_menu(
        dataset_name="dataset.csv",
        default_model_name="gpt-4.1-mini",
        planning_model_name="gpt-5-mini",
        worker_model_name="gpt-4.1-mini",
        synthesis_model_name="gpt-5.4",
        latest_run_name=None,
    )
    tools_menu = render_tools_menu(
        dataset_name="dataset.csv",
        latest_run_name=None,
        selected_tool_name=None,
    )

    assert "Run Semantic Extraction" in semantic_menu
    assert "<available>" not in semantic_menu
    assert "Evaluate Semantic Extraction Runs  <planned>" in semantic_menu
    assert "Debug / Replay Semantic Extraction  <planned>" in semantic_menu
    assert "Semantic Extraction Config  <planned>" in semantic_menu

    assert "Run Investigation Analysis" in investigation_menu
    assert "Evaluate Investigation Analysis Runs  <planned>" in investigation_menu
    assert "Debug / Replay Investigation Analysis  <planned>" in investigation_menu
    assert "Investigation Analysis Config  <planned>" in investigation_menu

    assert "Run Hypothesis Ranking" in ranking_menu
    assert "Evaluate Hypothesis Ranking Runs  <planned>" in ranking_menu
    assert "Debug / Replay Hypothesis Ranking  <planned>" in ranking_menu
    assert "Hypothesis Ranking Config  <planned>" in ranking_menu

    assert "Run Planner" in planner_menu
    assert "Evaluate Planner Runs  <planned>" in planner_menu
    assert "Debug / Replay Planner  <planned>" in planner_menu
    assert "Planner Config  <planned>" in planner_menu

    assert "Run Router" in router_menu
    assert "Evaluate Router Runs  <planned>" in router_menu
    assert "Debug / Replay Router  <planned>" in router_menu
    assert "Router Config  <planned>" in router_menu

    assert "Run Worker" in worker_menu
    assert "Evaluate Worker Runs  <planned>" in worker_menu
    assert "Debug / Replay Worker  <planned>" in worker_menu
    assert "Worker Config  <planned>" in worker_menu

    assert "Run Aggregation" in aggregation_menu
    assert "Evaluate Aggregation Runs  <planned>" in aggregation_menu
    assert "Debug / Replay Aggregation  <planned>" in aggregation_menu
    assert "Aggregation Config  <planned>" in aggregation_menu

    assert "Run State Manager" in state_manager_menu
    assert "Evaluate State Manager Runs  <planned>" in state_manager_menu
    assert "Debug / Replay State Manager  <planned>" in state_manager_menu
    assert "State Manager Config  <planned>" in state_manager_menu

    assert "Run Critic" in critic_menu
    assert "Evaluate Critic Runs  <planned>" in critic_menu
    assert "Debug / Replay Critic  <planned>" in critic_menu
    assert "Critic Config  <planned>" in critic_menu

    assert "Run Final Batch Auditor" in final_batch_auditor_menu
    assert "Evaluate Final Batch Audits  <planned>" in final_batch_auditor_menu
    assert "Debug / Replay Final Batch Audit  <planned>" in final_batch_auditor_menu
    assert "Final Batch Auditor Config  <planned>" in final_batch_auditor_menu

    assert "Run Cognitive Chain" in phase3a_runtime_menu
    assert "Run Hypothesis Execution" in phase3a_runtime_menu
    assert "Run Full Round" in phase3a_runtime_menu
    assert "Run Full Batch" in phase3a_runtime_menu
    assert "Review Latest Phase 3A Batch Run" in phase3a_runtime_menu
    assert "View Saved Phase 3A Batch Runs" in phase3a_runtime_menu
    assert "Evaluate Phase 3A Batch Runs  <planned>" in phase3a_runtime_menu
    assert "Debug / Replay Phase 3A Batch Run  <planned>" in phase3a_runtime_menu
    assert "Open Session Config" in phase3a_runtime_menu
    assert "planning_model" in phase3a_runtime_menu
    assert "worker_model" in phase3a_runtime_menu
    assert "synthesis_model" in phase3a_runtime_menu

    assert "Run Tool" in tools_menu
    assert "Inspect Tool Inventory" in tools_menu
    assert "Evaluate Tool Runs  <planned>" in tools_menu
    assert "Debug / Replay Tool Run  <planned>" in tools_menu
    assert "Tools Config  <planned>" in tools_menu


def test_planner_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_planner_run = None
    cli._get_latest_planner_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_letter_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._planner_menu()

    assert route == "planner"
    assert captured["message"] == (
        "Planner evaluation is not implemented yet. Current CLI progress: "
        "run, latest-run review, and saved-run browsing are implemented."
    )


def test_router_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_router_run = None
    cli._get_latest_router_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_letter_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._router_menu()

    assert route == "router"
    assert captured["message"] == (
        "Router evaluation is not implemented yet. Current CLI progress: "
        "run, latest-run review, and saved-run browsing are implemented."
    )


def test_worker_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_worker_run = None
    cli._get_latest_worker_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_letter_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._worker_menu()

    assert route == "worker"
    assert captured["message"] == (
        "Worker evaluation is not implemented yet. Current CLI progress: "
        "run, latest-run review, and saved-run browsing are implemented."
    )


def test_aggregation_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_aggregation_run = None
    cli._get_latest_aggregation_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_letter_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._aggregation_menu()

    assert route == "aggregation"
    assert captured["message"] == (
        "Aggregation evaluation is not implemented yet. Current CLI progress: "
        "run, latest-run review, and saved-run browsing are implemented."
    )


def test_state_manager_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_state_manager_run = None
    cli._get_latest_state_manager_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_letter_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._state_manager_menu()

    assert route == "state_manager"
    assert captured["message"] == (
        "State Manager evaluation is not implemented yet. Current CLI progress: "
        "run, latest-run review, and saved-run browsing are implemented."
    )


def test_critic_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_critic_run = None
    cli._get_latest_critic_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_letter_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._critic_menu()

    assert route == "critic"
    assert captured["message"] == (
        "Critic evaluation is not implemented yet. Current CLI progress: "
        "run, latest-run review, and saved-run browsing are implemented."
    )


def test_final_batch_auditor_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_final_batch_auditor_run = None
    cli._get_latest_final_batch_auditor_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_letter_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._final_batch_auditor_menu()

    assert route == "final_batch_auditor"
    assert captured["message"] == (
        "Final Batch Auditor evaluation is not implemented yet. Current CLI progress: "
        "run, latest-run review, and saved-run browsing are implemented."
    )


def test_phase3a_runtime_menu_reports_pending_actions_explicitly():
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(model_name="gpt-4.1-mini")
    cli._last_phase3a_runtime_run = None
    cli._get_latest_phase3a_runtime_run_context = lambda: None
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    cli._render = lambda content: setattr(cli, "_last_rendered", content)
    cli._read_menu_choice = lambda valid_choices: "E"
    cli._quit = lambda: None

    captured: dict[str, str] = {}
    cli._show_info = lambda message: captured.setdefault("message", message)

    route = cli._phase3a_runtime_menu()

    assert route == "phase3a_runtime"
    assert captured["message"] == (
        "Phase 3A Runtime evaluation is not implemented yet. Current CLI progress: "
        "grouped execution, latest-run review, and saved-run browsing are implemented."
    )