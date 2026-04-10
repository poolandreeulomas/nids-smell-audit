"""Interactive CLI for the NIDS agent project."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Any, Callable

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

from analysis.interpreter import extract_run_insights
from config import DATA_DIR, LOG_DIR
from experiments.evaluate_runs import (
    evaluate_runs,
    render_evaluation_report,
    save_evaluation_artifacts,
)
from interface.terminal_ui import (
    render_artifact_paths,
    render_dataset_selection,
    render_error,
    render_model_selection,
    render_evaluation_aggregate,
    render_evaluation_overview,
    render_evaluation_ranking,
    render_info,
    render_main_menu,
    render_recent_runs,
    render_run_json_path,
    render_run_summary,
    render_saved_report,
    render_session_config,
    render_step_by_step,
)
from main import main as run_main
from utils.metrics import state_metrics_payload
from utils.run_logging import DEFAULT_RUNS_DIR, load_json, save_run_artifacts


@dataclass
class SessionConfig:
    """Session-level defaults that later phases can wire into real actions."""

    model_name: str = "gpt-4.1-mini"
    dataset_name: str | None = None
    trace_enabled: bool = False
    evaluation_window: int = 5


@dataclass
class RunContext:
    """Saved context for the most recent CLI-triggered or loaded run."""

    artifact_paths: dict[str, str]
    run_payload: dict[str, Any]
    metrics: dict[str, Any]
    insights: dict[str, Any]


@dataclass
class EvaluationContext:
    """Cached deterministic evaluation result for the current session window."""

    latest: int
    result: dict[str, Any]


ScreenHandler = Callable[[], str | None]

OPENAI_MODEL_OPTIONS = [
    ("Low cost  | gpt-4.1-nano", "gpt-4.1-nano"),
    ("Balanced  | gpt-4.1-mini", "gpt-4.1-mini"),
    ("Powerful  | gpt-4.1", "gpt-4.1"),
]


class NidsAgentCli:
    """Simple keyboard-driven CLI shell for research workflows."""

    def __init__(self) -> None:
        self.session_config = SessionConfig()
        available_datasets = self._get_available_dataset_paths()
        if available_datasets:
            self.session_config.dataset_name = available_datasets[0].name
        self._evaluation_context: EvaluationContext | None = None
        self._last_run: RunContext | None = None
        self._view_runs_limit = 5
        self._selected_view_run: RunContext | None = None
        self._running = True
        self._current_screen = "main"
        self._screen_handlers: dict[str, ScreenHandler] = {
            "main": self._main_menu,
            "run": self._run_agent_menu,
            "latest": self._latest_run_menu,
            "view": self._view_runs_menu,
            "evaluate": self._evaluate_runs_menu,
            "session": self._session_config_menu,
        }

    def run(self) -> None:
        """Start the CLI navigation loop."""
        while self._running:
            handler = self._screen_handlers[self._current_screen]
            next_screen = handler()
            if next_screen is not None:
                self._current_screen = next_screen

    def _clear_screen(self) -> None:
        # Clear visible content and reset the cursor so each screen starts at the top.
        print("\033[2J\033[3J\033[H", end="", flush=True)

    def _render(self, content: str) -> None:
        self._clear_screen()
        print(content)

    def _wait_for_enter(self, prompt: str = "Press Enter to continue.") -> None:
        print()
        input(prompt)

    def _main_menu(self) -> str | None:
        self._render(
            render_main_menu(
                model_name=self.session_config.model_name,
                dataset_name=self._get_selected_dataset_label(),
                trace_enabled=self.session_config.trace_enabled,
                evaluation_window=self.session_config.evaluation_window,
                stored_runs_count=self._count_persisted_runs(),
                has_cli_run=self._last_run is not None,
            )
        )

        choice = self._read_letter_choice({"R", "L", "V", "E", "M", "Q"})
        routes = {
            "L": "latest",
            "V": "view",
            "E": "evaluate",
            "M": "session",
        }
        if choice == "Q":
            self._quit()
            return None
        if choice == "R":
            return self._start_run_agent_flow()
        return routes[choice]

    def _run_agent_menu(self) -> str:
        if self._last_run is None:
            self._render(render_error(
                "No CLI-triggered run is available yet. Start a run from the main menu first."))
            print("[B] Back")
            print("[Q] Quit")
            print()
            choice = self._read_letter_choice({"B", "Q"})
            if choice == "Q":
                self._quit()
                return "run"
            return "main"

        run_context = self._last_run
        self._print_run_summary(run_context)

        choice = self._read_menu_choice({"1", "2", "3", "4", "B", "Q"})
        if choice == "B":
            return "main"
        if choice == "Q":
            self._quit()
            return "run"
        if choice == "1":
            self._print_step_by_step(run_context.run_payload)
            return "run"
        if choice == "2":
            return "run"
        if choice == "3":
            self._print_artifact_paths(run_context.artifact_paths)
            return "run"
        return "evaluate"

    def _latest_run_menu(self) -> str:
        try:
            run_context = self._get_latest_run_context()
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"failed to load latest run: {exc}")
            return "main"

        if run_context is None:
            self._render(render_error("No persisted run logs are available yet."))
            print("[B] Back")
            print("[Q] Quit")
            print()
            choice = self._read_letter_choice({"B", "Q"})
            if choice == "Q":
                self._quit()
                return "latest"
            return "main"

        run_name = Path(run_context.artifact_paths.get(
            "run_log_path", "")).name or None
        self._render(
            render_run_summary(
                title="Latest Run",
                run_name=run_name,
                intro_line="Most recent persisted run.",
                metrics=self._build_metric_pairs(run_context),
                top_features=list(
                    run_context.insights.get("top_features", [])),
                errors=self._build_error_lines(run_context),
                conclusion=self._build_conclusion_line(run_context),
                path_label="Home / Latest Run",
                hint="Use this screen for a fast check of the latest persisted result.",
                options=[
                    ("1", "Step-by-step view"),
                    ("2", "Show raw artifact paths"),
                    ("3", "Evaluate recent runs"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

        choice = self._read_menu_choice({"1", "2", "3", "B", "Q"})
        if choice == "1":
            self._print_step_by_step(run_context.run_payload)
            return "latest"
        if choice == "2":
            self._print_artifact_paths(run_context.artifact_paths)
            return "latest"
        if choice == "3":
            return "evaluate"
        if choice == "B":
            return "main"
        self._quit()
        return "latest"

    def _view_runs_menu(self) -> str:
        if self._selected_view_run is None:
            return self._view_runs_list_menu()
        return self._view_selected_run_menu()

    def _evaluate_runs_menu(self) -> str:
        try:
            evaluation_context = self._get_evaluation_context()
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"failed to evaluate runs: {exc}")
            return "main"

        self._print_evaluation_overview(
            evaluation_context.result, evaluation_context.latest)

        choice = self._read_menu_choice({"1", "2", "3", "4", "B", "Q"})
        if choice == "1":
            self._print_evaluation_ranking(evaluation_context.result)
            return "evaluate"
        if choice == "2":
            self._print_evaluation_aggregate_findings(
                evaluation_context.result)
            return "evaluate"
        if choice == "3":
            self._change_evaluation_window()
            self._evaluation_context = None
            return "evaluate"
        if choice == "4":
            self._save_evaluation_report(evaluation_context)
            return "evaluate"
        if choice == "B":
            return "main"
        self._quit()
        return "evaluate"

    def _session_config_menu(self) -> str:
        self._render(
            render_session_config(
                model_name=self.session_config.model_name,
                dataset_name=self._get_selected_dataset_label(),
                trace_enabled=self.session_config.trace_enabled,
                evaluation_window=self.session_config.evaluation_window,
            )
        )

        choice = self._read_menu_choice({"1", "2", "3", "4", "B", "Q"})
        if choice == "B":
            return "main"
        if choice == "Q":
            self._quit()
            return "session"
        if choice == "1":
            self._change_model_name()
            return "session"
        if choice == "2":
            self._change_dataset_partition()
            return "session"
        if choice == "3":
            self._toggle_trace_enabled()
            return "session"
        self._change_evaluation_window()
        return "session"

    def _read_letter_choice(self, valid_choices: set[str]) -> str:
        while True:
            raw_value = input("> ").strip().upper()
            if len(raw_value) != 1 or not raw_value.isalpha():
                print("Enter a single letter.")
                continue
            if raw_value not in valid_choices:
                options = ", ".join(sorted(valid_choices))
                print(f"Invalid option. Choose one of: {options}")
                continue
            return raw_value

    def _read_menu_choice(self, valid_choices: set[str]) -> str:
        while True:
            raw_value = input("> ").strip().upper()
            if raw_value not in valid_choices:
                options = ", ".join(sorted(valid_choices))
                print(f"Invalid option. Choose one of: {options}")
                continue
            return raw_value

    def _start_run_agent_flow(self) -> str:
        dataset_label = self._get_selected_dataset_label()
        self._render(
            render_run_summary(
                title="Run Agent",
                run_name=None,
                intro_line="This action will run the MVP agent using the configured API model. External API cost may apply.",
                metrics=[
                    ("model", self.session_config.model_name),
                    ("dataset", dataset_label),
                    ("trace", "on" if self.session_config.trace_enabled else "off"),
                ],
                top_features=[],
                errors=[],
                conclusion="Confirm to start the run.",
                path_label="Home / Run Agent",
                hint="This is the only flow that may trigger an external API call.",
                options=[("Y", "Continue"), ("N", "Cancel")],
            )
        )
        choice = self._read_letter_choice({"Y", "N"})
        if choice == "N":
            return "main"

        self._clear_screen()
        print("Running MVP agent...")
        print(f"Dataset: {dataset_label}")
        print(f"Model: {self.session_config.model_name}")
        try:
            run_context = self._execute_run()
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"run failed: {exc}")
            return "main"

        self._last_run = run_context
        self._evaluation_context = None
        print()
        return "run"

    def _execute_run(self) -> RunContext:
        previous_model = os.environ.get("OPENAI_MODEL")
        previous_trace = os.environ.get("REACT_TRACE")
        previous_dataset = os.environ.get("NIDS_DATASET_PATH")
        os.environ["OPENAI_MODEL"] = self.session_config.model_name
        os.environ["REACT_TRACE"] = "1" if self.session_config.trace_enabled else "0"
        os.environ["NIDS_DATASET_PATH"] = self._get_selected_dataset_path().name

        try:
            try:
                final_state = run_main()
            except FileNotFoundError as exc:
                dataset_dir = DATA_DIR.resolve()
                raise RuntimeError(
                    f"dataset not available under '{dataset_dir}'. Confirm that CSV files exist there."
                ) from exc
        finally:
            self._restore_env_var("OPENAI_MODEL", previous_model)
            self._restore_env_var("REACT_TRACE", previous_trace)
            self._restore_env_var("NIDS_DATASET_PATH", previous_dataset)

        metrics = state_metrics_payload(final_state)
        artifact_paths = save_run_artifacts(
            final_state, metrics, log_dir=LOG_DIR)
        run_payload = load_json(artifact_paths["run_log_path"])
        insights = extract_run_insights(run_payload)
        return RunContext(
            artifact_paths=artifact_paths,
            run_payload=run_payload,
            metrics=metrics,
            insights=insights,
        )

    def _restore_env_var(self, key: str, previous_value: str | None) -> None:
        if previous_value is None:
            os.environ.pop(key, None)
            return
        os.environ[key] = previous_value

    def _get_selected_dataset_label(self) -> str:
        try:
            dataset_path = self._get_selected_dataset_path()
        except FileNotFoundError:
            return f"missing from {DATA_DIR}"
        return dataset_path.name

    def _get_available_dataset_paths(self) -> list[Path]:
        return sorted(
            path
            for path in Path(DATA_DIR).iterdir()
            if path.is_file() and path.suffix.lower() in {".csv", ".tsv", ".tab"}
        )

    def _get_selected_dataset_path(self) -> Path:
        candidates = self._get_available_dataset_paths()
        if not candidates:
            raise FileNotFoundError(DATA_DIR)
        selected_name = self.session_config.dataset_name
        if selected_name:
            for candidate in candidates:
                if candidate.name == selected_name:
                    return candidate
        selected_path = candidates[0]
        self.session_config.dataset_name = selected_path.name
        return selected_path

    def _print_run_summary(self, run_context: RunContext) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "run_log_path", "")).name or None
        self._render(
            render_run_summary(
                title="Run Summary",
                run_name=run_name,
                intro_line="Run completed.",
                metrics=self._build_metric_pairs(run_context),
                top_features=list(
                    run_context.insights.get("top_features", [])),
                errors=self._build_error_lines(run_context),
                conclusion=self._build_conclusion_line(run_context),
                path_label="Home / Run Agent / Result",
                hint="Review the run, inspect steps, or jump into evaluation.",
                options=[
                    ("1", "Step-by-step"),
                    ("2", "View Summary Again"),
                    ("3", "Show Raw Artifact Paths"),
                    ("4", "Evaluate Recent Runs"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _print_step_by_step(self, run_payload: dict[str, Any]) -> None:
        self._render(render_step_by_step(list(run_payload.get("history", [])),
                     path_label="Inspection / Step-by-Step"))
        self._wait_for_enter()

    def _print_artifact_paths(self, artifact_paths: dict[str, str]) -> None:
        self._render(render_artifact_paths(artifact_paths))
        self._wait_for_enter()

    def _print_run_json_path(self, run_context: RunContext) -> None:
        self._render(render_run_json_path(
            run_context.artifact_paths.get("run_log_path", "unavailable")))
        self._wait_for_enter()

    def _view_runs_list_menu(self) -> str:
        recent_runs = self._get_recent_run_paths(self._view_runs_limit)
        self._render(render_recent_runs(recent_runs, self._view_runs_limit))
        if not recent_runs:
            choice = self._read_letter_choice({"B", "Q"})
            if choice == "Q":
                self._quit()
                return "view"
            return "main"

        valid_choices = {str(index) for index in range(
            1, len(recent_runs) + 1)} | {"N", "B", "Q"}
        choice = self._read_menu_choice(valid_choices)
        if choice == "B":
            return "main"
        if choice == "Q":
            self._quit()
            return "view"
        if choice == "N":
            self._change_view_runs_limit()
            return "view"

        selected_path = recent_runs[int(choice) - 1]
        try:
            self._selected_view_run = self._load_run_context(selected_path)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"failed to load run file: {exc}")
            return "view"
        return "view"

    def _view_selected_run_menu(self) -> str:
        run_context = self._selected_view_run
        if run_context is None:
            return "view"

        run_name = Path(run_context.artifact_paths.get(
            "run_log_path", "")).name or None
        self._render(
            render_run_summary(
                title="View Run",
                run_name=run_name,
                intro_line="Selected persisted run.",
                metrics=self._build_metric_pairs(run_context),
                top_features=list(
                    run_context.insights.get("top_features", [])),
                errors=self._build_error_lines(run_context),
                conclusion=self._build_conclusion_line(run_context),
                path_label="Home / View Runs / Selected Run",
                hint="Use this screen to inspect one stored run without opening JSON.",
                options=[
                    ("1", "Step-by-step"),
                    ("2", "Show raw artifact paths"),
                    ("3", "Show raw JSON path"),
                    ("4", "Evaluate with recent runs"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

        choice = self._read_menu_choice({"1", "2", "3", "4", "B", "Q"})
        if choice == "1":
            self._print_step_by_step(run_context.run_payload)
            return "view"
        if choice == "2":
            self._print_artifact_paths(run_context.artifact_paths)
            return "view"
        if choice == "3":
            self._print_run_json_path(run_context)
            return "view"
        if choice == "4":
            return "evaluate"
        if choice == "Q":
            self._quit()
            return "view"

        self._selected_view_run = None
        return "view"

    def _get_recent_run_paths(self, limit: int) -> list[Path]:
        candidates = sorted(
            path
            for path in DEFAULT_RUNS_DIR.glob("run_*.json")
            if not path.name.endswith("_metrics.json") and path.name != "run_test_metrics.json"
        )
        if limit <= 0:
            return []
        return list(reversed(candidates[-limit:]))

    def _count_persisted_runs(self) -> int:
        return len(self._get_recent_run_paths(9999))

    def _get_latest_run_context(self) -> RunContext | None:
        latest_paths = self._get_recent_run_paths(1)
        if not latest_paths:
            return None
        return self._load_run_context(latest_paths[0])

    def _change_view_runs_limit(self) -> None:
        print("Enter number of runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_runs_limit = limit
            self._show_info(f"Visible runs set to: {limit}")
            return

    def _change_model_name(self) -> None:
        self._render(
            render_model_selection(OPENAI_MODEL_OPTIONS, self.session_config.model_name)
        )
        valid_choices = {str(index) for index in range(1, len(OPENAI_MODEL_OPTIONS) + 1)} | {"B", "Q"}
        choice = self._read_menu_choice(valid_choices)
        if choice == "B":
            return
        if choice == "Q":
            self._quit()
            return

        selected_model = OPENAI_MODEL_OPTIONS[int(choice) - 1][1]
        self.session_config.model_name = selected_model
        self._show_info(
            f"Session model updated to: {self.session_config.model_name}")

    def _change_dataset_partition(self) -> None:
        dataset_paths = self._get_available_dataset_paths()
        if not dataset_paths:
            self._show_error(f"no dataset partitions found under {DATA_DIR}")
            return

        self._render(
            render_dataset_selection(dataset_paths, self.session_config.dataset_name)
        )
        valid_choices = {str(index) for index in range(1, len(dataset_paths) + 1)} | {"B", "Q"}
        choice = self._read_menu_choice(valid_choices)
        if choice == "B":
            return
        if choice == "Q":
            self._quit()
            return

        selected_path = dataset_paths[int(choice) - 1]
        self.session_config.dataset_name = selected_path.name
        self._show_info(f"Dataset partition updated to: {selected_path.name}")

    def _toggle_trace_enabled(self) -> None:
        self.session_config.trace_enabled = not self.session_config.trace_enabled
        trace_value = "on" if self.session_config.trace_enabled else "off"
        self._show_info(f"Trace is now: {trace_value}")

    def _change_evaluation_window(self) -> None:
        self._clear_screen()
        print("Enter number of runs to evaluate:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self.session_config.evaluation_window = limit
            self._evaluation_context = None
            self._show_info(f"Evaluation window set to: {limit}")
            return

    def _load_run_context(self, run_log_path: Path) -> RunContext:
        run_payload = load_json(run_log_path)
        metrics = dict(run_payload.get("metrics", {}))
        metrics_path = run_log_path.with_name(
            f"{run_log_path.stem}_metrics.json")
        artifact_paths = {
            "run_log_path": str(run_log_path),
            "metrics_log_path": str(metrics_path),
        }
        insights = extract_run_insights(run_payload)
        return RunContext(
            artifact_paths=artifact_paths,
            run_payload=run_payload,
            metrics=metrics,
            insights=insights,
        )

    def _build_conclusion_line(self, run_context: RunContext) -> str:
        behavior = dict(run_context.insights.get("behavior", {}))
        patterns = dict(run_context.insights.get("patterns", {}))
        errors = list(run_context.insights.get("errors", []))
        confirmed = list(patterns.get("confirmed_features", []))

        if confirmed and not errors and behavior.get("used_both_tools"):
            return "Conclusion: clear signal with balanced tool usage and no tool errors."
        if confirmed and errors:
            return "Conclusion: useful signal was confirmed, but some tool errors remain."
        if run_context.insights.get("top_features"):
            return "Conclusion: the run produced a usable feature ranking, but evidence is still limited."
        return "Conclusion: the run did not produce a strong ranking yet."

    def _build_metric_pairs(self, run_context: RunContext) -> list[tuple[str, str]]:
        behavior = dict(run_context.insights.get("behavior", {}))
        metrics = run_context.metrics
        return [
            ("steps", str(behavior.get("num_steps", 0))),
            ("features_attempted", str(behavior.get("unique_features_attempted", 0))),
            ("features_successful", str(behavior.get("unique_features_successful", 0))),
            ("valid_action_rate",
             f"{metrics.get('valid_action_rate', 0.0):.2f}"),
            ("tool_error_rate", f"{metrics.get('tool_error_rate', 0.0):.2f}"),
        ]

    def _build_error_lines(self, run_context: RunContext) -> list[str]:
        errors = list(run_context.insights.get("errors", []))
        if not errors:
            return []
        return [
            f"{error.get('feature_name') or 'unknown'}: {error.get('error_code') or 'UNKNOWN'}"
            for error in errors[-3:]
        ]

    def _get_evaluation_context(self) -> EvaluationContext:
        latest = self.session_config.evaluation_window
        if self._evaluation_context and self._evaluation_context.latest == latest:
            return self._evaluation_context

        result = evaluate_runs(latest=latest)
        self._evaluation_context = EvaluationContext(
            latest=latest, result=result)
        return self._evaluation_context

    def _print_evaluation_overview_for_current_window(self) -> None:
        try:
            evaluation_context = self._get_evaluation_context()
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"failed to evaluate runs: {exc}")
            return
        self._print_evaluation_overview(
            evaluation_context.result, evaluation_context.latest)

    def _print_evaluation_overview(self, result: dict[str, Any], latest: int) -> None:
        self._render(
            render_evaluation_overview(
                result,
                latest,
                [
                    ("1", "View full ranking"),
                    ("2", "View aggregate findings"),
                    ("3", "Change number of runs"),
                    ("4", "Save evaluation report"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _print_evaluation_ranking(self, result: dict[str, Any]) -> None:
        self._render(render_evaluation_ranking(result))
        self._wait_for_enter()

    def _print_evaluation_aggregate_findings(self, result: dict[str, Any]) -> None:
        self._render(render_evaluation_aggregate(result))
        self._wait_for_enter()

    def _save_evaluation_report(self, evaluation_context: EvaluationContext) -> None:
        report_text = render_evaluation_report(evaluation_context.result)
        try:
            artifact_paths = save_evaluation_artifacts(
                evaluation_context.result,
                report_text,
                prefix="cli_evaluation",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"failed to save evaluation report: {exc}")
            return

        self._render(render_saved_report(artifact_paths))
        self._wait_for_enter()

    def _show_info(self, message: str) -> None:
        self._render(render_info(message))
        self._wait_for_enter()

    def _show_error(self, message: str) -> None:
        self._render(render_error(message))
        self._wait_for_enter()

    def _quit(self) -> None:
        print()
        print("Exiting NIDS Agent CLI.")
        self._running = False


def main() -> None:
    """Run the interactive CLI shell."""
    cli = NidsAgentCli()
    try:
        cli.run()
    except KeyboardInterrupt:
        print()
        print("Exiting NIDS Agent CLI.")


if __name__ == "__main__":
    main()
