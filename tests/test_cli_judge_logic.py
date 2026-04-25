from interface import cli as cli_module
from interface.cli import NidsAgentCli, SessionConfig


def test_main_menu_routes_to_judge(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(dataset_name="dataset.csv")
    cli._last_run = None
    cli._running = True
    cli._render = lambda content: None
    cli._count_persisted_runs = lambda: 3
    cli._get_selected_dataset_label = lambda: "dataset.csv"
    monkeypatch.setattr(cli, "_read_letter_choice", lambda valid_choices: "J")

    next_screen = cli._main_menu()

    assert next_screen == "judge"


def test_build_jif_payload_for_judge_uses_existing_jif_paths(monkeypatch):
    cli = object.__new__(NidsAgentCli)
    cli.session_config = SessionConfig(dataset_name="dataset.csv")
    cli._read_comma_separated_paths = lambda prompt: [
        "jif_a.json", "jif_b.json"]

    monkeypatch.setattr(cli_module, "load_jif_payloads", lambda paths: [
        {"header": {"run_count": 1, "source_run_ids": ["r1"], "source_artifacts": ["jif_a.json"]}, "cohort_context": {"objective_frequency": {}, "dataset_frequency": {}, "model_name_frequency": {}, "model_version_frequency": {
        }, "max_steps_frequency": {}, "tool_set": []}, "aggregate": {"run_count": 1, "total_steps": 2, "tool_frequency": {}, "step_type_frequency": {}, "redundant_step_frequency": {}, "signal_frequency": {}}, "run_cards": [{"run_id": "r1"}]},
        {"header": {"run_count": 1, "source_run_ids": ["r2"], "source_artifacts": ["jif_b.json"]}, "cohort_context": {"objective_frequency": {}, "dataset_frequency": {}, "model_name_frequency": {}, "model_version_frequency": {
        }, "max_steps_frequency": {}, "tool_set": []}, "aggregate": {"run_count": 1, "total_steps": 3, "tool_frequency": {}, "step_type_frequency": {}, "redundant_step_frequency": {}, "signal_frequency": {}}, "run_cards": [{"run_id": "r2"}]},
    ])
    monkeypatch.setattr(cli_module, "merge_jif_payloads", lambda payloads: {"aggregate": {
                        "run_count": 2, "total_steps": 5}, "run_cards": [{"run_id": "r1"}, {"run_id": "r2"}]})

    payload, source_summary = cli._build_jif_payload_for_judge(
        source_choice="3", mode="multi_run")

    assert payload["aggregate"]["run_count"] == 2
    assert source_summary == "existing JIF file(s) (2)"
