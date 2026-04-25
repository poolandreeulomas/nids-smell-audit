"""Interactive CLI for the NIDS agent project."""

from __future__ import annotations

from collections import Counter
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
from config import DATA_DIR, LOG_DIR, MAX_STEPS
from experiments.compare_runs import compare_runs
from experiments.evaluate_runs import (
    evaluate_runs,
    render_evaluation_report,
    save_evaluation_artifacts,
)
from experiments.export_jif import export_jif
from interface.terminal_ui import (
    render_dataset_selection,
    render_error,
    render_feature_analysis,
    render_judge_mode_selection,
    render_judge_report,
    render_judge_source_selection,
    render_model_selection,
    render_multi_run_summary,
    render_evaluation_aggregate,
    render_evaluation_overview,
    render_evaluation_ranking,
    render_info,
    render_main_menu,
    render_reasoning_trace,
    render_recent_runs,
    render_run_review,
    render_run_summary,
    render_saved_judge_report,
    render_saved_report,
    render_session_config,
    render_technical_details,
)
from judge.judge_runner import load_jif_payloads, merge_jif_payloads, run_judge
from main import main as run_main
from utils.human_readable import first_metric_text, split_bullet_lines
from utils.metrics import state_metrics_payload
from utils.run_logging import DEFAULT_RUNS_DIR, build_session_run_basename, load_json, save_run_artifacts

REVIEW_MENU_OPTIONS = [
    ("1", "Reasoning Trace"),
    ("2", "Feature Analysis"),
    ("3", "Technical Details"),
    ("4", "Evaluate Recent Runs"),
    ("B", "Back"),
    ("Q", "Quit"),
]

SIGNAL_REVIEWS: dict[str, tuple[str, str]] = {
    "high_duplication": ("high", "Heavy duplication suggests the partition may contain repeated traffic patterns."),
    "high_redundancy": ("high", "This feature overlaps strongly with another feature and may be redundant."),
    "low_cardinality": ("high", "Very low variability suggests determinism or direct leakage."),
    "high_class_separation": ("medium", "The feature separates classes unusually well and may act as a shortcut."),
}


@dataclass
class SessionConfig:
    """Session-level defaults that later phases can wire into real actions."""

    model_name: str = "gpt-4.1-mini"
    judge_model_name: str = "gpt-4.1"
    dataset_name: str | None = None
    trace_enabled: bool = False
    max_steps: int = MAX_STEPS
    evaluation_window: int = 5


@dataclass
class RunContext:
    """Saved context for the most recent CLI-triggered or loaded run."""

    artifact_paths: dict[str, str]
    run_payload: dict[str, Any]
    metrics: dict[str, Any]
    insights: dict[str, Any]
    llm_overview: list[str] | None = None


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
        self._session_run_counter = 0
        self._running = True
        self._current_screen = "main"
        self._screen_handlers: dict[str, ScreenHandler] = {
            "main": self._main_menu,
            "run": self._run_agent_menu,
            "judge": self._judge_menu,
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
                max_steps=self.session_config.max_steps,
                evaluation_window=self.session_config.evaluation_window,
                stored_runs_count=self._count_persisted_runs(),
                has_cli_run=self._last_run is not None,
            )
        )

        choice = self._read_letter_choice({"R", "J", "L", "V", "E", "M", "Q"})
        routes = {
            "J": "judge",
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
        choice = self._show_review_menu(
            title="Run Review",
            run_context=run_context,
            intro_line="Run completed. Start with risks and only expand what you need.",
            path_label="Home / Run Agent / Result",
            hint="The default view hides raw metrics and keeps the reasoning story visible.",
        )
        if choice == "B":
            return "main"
        if choice == "Q":
            self._quit()
            return "run"
        return self._handle_review_choice(choice, run_context, "run")

    def _latest_run_menu(self) -> str:
        try:
            run_context = self._get_latest_run_context()
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"failed to load latest run: {exc}")
            return "main"

        if run_context is None:
            self._render(render_error(
                "No persisted run logs are available yet."))
            print("[B] Back")
            print("[Q] Quit")
            print()
            choice = self._read_letter_choice({"B", "Q"})
            if choice == "Q":
                self._quit()
                return "latest"
            return "main"

        choice = self._show_review_menu(
            title="Latest Run",
            run_context=run_context,
            intro_line="Most recent persisted run.",
            path_label="Home / Latest Run",
            hint="Use this screen to understand the latest reasoning before opening raw files.",
        )
        if choice == "4":
            return "evaluate"
        if choice == "B":
            return "main"
        if choice == "Q":
            self._quit()
            return "latest"
        return self._handle_review_choice(choice, run_context, "latest")

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
        result = self._edit_session_config_flow()
        if result == "quit":
            self._quit()
            return "session"
        return "main"

    def _judge_menu(self) -> str:
        self._render(render_judge_source_selection(
            judge_model_name=self.session_config.judge_model_name))
        source_choice = self._read_menu_choice({"1", "2", "3", "B", "Q"})
        if source_choice == "B":
            return "main"
        if source_choice == "Q":
            self._quit()
            return "judge"

        self._render(render_judge_mode_selection())
        mode_choice = self._read_menu_choice({"1", "2", "B", "Q"})
        if mode_choice == "B":
            return "main"
        if mode_choice == "Q":
            self._quit()
            return "judge"

        mode = "multi_run" if mode_choice == "1" else "single_run"

        try:
            payload, source_summary = self._build_jif_payload_for_judge(
                source_choice=source_choice,
                mode=mode,
            )
            judge_result = run_judge(
                payload,
                model_name=self.session_config.judge_model_name,
                mode=mode,
                prefix="cli_judge",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"failed to run judge: {exc}")
            return "main"

        self._render(
            render_judge_report(
                title="Judge Report",
                mode=judge_result["mode"],
                model_name=self.session_config.judge_model_name,
                source_summary=source_summary,
                report=judge_result["report"],
                path_label="Home / Run Judge / Report",
                hint="LLM-grounded analysis over JIF only.",
            )
        )
        self._wait_for_enter()
        self._render(render_saved_judge_report(judge_result["artifact_paths"]))
        self._wait_for_enter()
        return "main"

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

    def _read_comma_separated_paths(self, prompt: str) -> list[str]:
        self._clear_screen()
        print(prompt)
        print("Separate multiple paths with commas.")
        while True:
            raw_value = input("> ").strip()
            if not raw_value:
                print("Enter at least one path.")
                continue
            paths = [item.strip()
                     for item in raw_value.split(",") if item.strip()]
            if not paths:
                print("Enter at least one path.")
                continue
            return paths

    def _start_run_agent_flow(self) -> str:
        while True:
            dataset_label = self._get_selected_dataset_label()
            self._render(
                render_run_summary(
                    title="Run Agent",
                    run_name=None,
                    intro_line="Review the current configuration before starting execution.",
                    metrics=[
                        ("model", self.session_config.model_name),
                        ("dataset", dataset_label),
                        ("max_steps", str(self.session_config.max_steps)),
                        ("live_trace", "on" if self.session_config.trace_enabled else "off"),
                        ("eval_window", str(self.session_config.evaluation_window)),
                    ],
                    top_features=[],
                    errors=[],
                    conclusion="Continue, modify the session configuration, or cancel.",
                    path_label="Home / Run Agent",
                    hint="This is the only flow that may trigger an external API call.",
                    options=[("Y", "Continue"),
                             ("M", "Modify Config"), ("N", "Cancel")],
                )
            )
            choice = self._read_letter_choice({"Y", "M", "N"})
            if choice == "N":
                return "main"
            if choice == "M":
                result = self._edit_session_config_flow()
                if result == "quit":
                    self._quit()
                    return "run"
                continue
            break

        run_count = self._prompt_run_count(default=1)
        try:
            run_contexts = self._execute_multi_run_flow(run_count)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"run failed: {exc}")
            return "main"

        self._last_run = run_contexts[-1]
        self._evaluation_context = None
        self._render_multi_run_summary(run_contexts)
        self._wait_for_enter()
        return "run"

    def _execute_run(self, *, basename: str | None = None) -> RunContext:
        previous_model = os.environ.get("OPENAI_MODEL")
        previous_trace = os.environ.get("REACT_TRACE")
        previous_dataset = os.environ.get("NIDS_DATASET_PATH")
        previous_max_steps = os.environ.get("NIDS_MAX_STEPS")
        os.environ["OPENAI_MODEL"] = self.session_config.model_name
        os.environ["REACT_TRACE"] = "1" if self.session_config.trace_enabled else "0"
        os.environ["NIDS_DATASET_PATH"] = self._get_selected_dataset_path().name
        os.environ["NIDS_MAX_STEPS"] = str(self.session_config.max_steps)

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
            self._restore_env_var("NIDS_MAX_STEPS", previous_max_steps)

        if basename:
            final_state.run_id = basename
            final_state.metadata["session_run_label"] = basename

        metrics = state_metrics_payload(final_state)
        artifact_paths = save_run_artifacts(
            final_state, metrics, log_dir=LOG_DIR, basename=basename)
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

    def _show_review_menu(
        self,
        *,
        title: str,
        run_context: RunContext,
        intro_line: str,
        path_label: str,
        hint: str,
    ) -> str:
        self._render_run_review_screen(
            title=title,
            run_context=run_context,
            intro_line=intro_line,
            path_label=path_label,
            hint=hint,
            options=REVIEW_MENU_OPTIONS,
        )
        return self._read_menu_choice({"1", "2", "3", "4", "B", "Q"})

    def _handle_review_choice(
        self,
        choice: str,
        run_context: RunContext,
        screen_name: str,
    ) -> str:
        if choice == "1":
            self._print_reasoning_trace(run_context)
            return screen_name
        if choice == "2":
            self._print_feature_analysis(run_context)
            return screen_name
        if choice == "3":
            self._print_technical_details(run_context)
            return screen_name
        return "evaluate"

    def _render_run_review_screen(
        self,
        *,
        title: str,
        run_context: RunContext,
        intro_line: str,
        path_label: str,
        hint: str,
        options: list[tuple[str, str]],
    ) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "run_log_path", "")).name or None
        reviews = self._build_feature_reviews(run_context)
        problems = [review for review in reviews if int(
            review["score"]) >= 3][:3]
        if not problems:
            problems = reviews[:3]

        self._render(
            render_run_review(
                title=title,
                run_name=run_name,
                intro_line=intro_line,
                problems=problems,
                llm_overview=self._get_review_overview(run_context),
                path_label=path_label,
                hint=hint,
                options=options,
            )
        )

    def _print_reasoning_trace(self, run_context: RunContext) -> None:
        self._render(
            render_reasoning_trace(
                list(run_context.run_payload.get("history", [])),
                path_label="Inspection / Reasoning Trace",
            )
        )
        self._wait_for_enter()

    def _print_feature_analysis(self, run_context: RunContext) -> None:
        self._render(
            render_feature_analysis(
                self._build_feature_reviews(run_context),
                path_label="Inspection / Feature Analysis",
                hint="Each feature card shows risk, scope, explanation, and supporting context.",
            )
        )
        self._wait_for_enter()

    def _print_technical_details(self, run_context: RunContext) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "run_log_path", "")).name or None
        self._render(
            render_technical_details(
                title="Technical Details",
                run_name=run_name,
                metrics=self._build_technical_metric_pairs(run_context),
                tools_used=self._build_used_tools(run_context),
                artifact_paths=run_context.artifact_paths,
                path_label="Inspection / Technical Details",
                hint="Raw metrics and artifact paths stay hidden until you open them here.",
            )
        )
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

        choice = self._show_review_menu(
            title="View Run",
            run_context=run_context,
            intro_line="Selected persisted run.",
            path_label="Home / View Runs / Selected Run",
            hint="Use this screen to inspect one stored run without opening raw JSON.",
        )
        if choice == "4":
            return "evaluate"
        if choice == "Q":
            self._quit()
            return "view"
        if choice != "B":
            return self._handle_review_choice(choice, run_context, "view")

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

    def _edit_session_config_flow(self) -> str:
        while True:
            self._render(
                render_session_config(
                    model_name=self.session_config.model_name,
                    judge_model_name=self.session_config.judge_model_name,
                    dataset_name=self._get_selected_dataset_label(),
                    trace_enabled=self.session_config.trace_enabled,
                    max_steps=self.session_config.max_steps,
                    evaluation_window=self.session_config.evaluation_window,
                )
            )

            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "6", "B", "Q"})
            if choice == "B":
                return "back"
            if choice == "Q":
                return "quit"
            if choice == "1":
                self._change_model_name()
                continue
            if choice == "2":
                self._change_judge_model_name()
                continue
            if choice == "3":
                self._change_dataset_partition()
                continue
            if choice == "4":
                self._toggle_trace_enabled()
                continue
            if choice == "5":
                self._change_max_steps()
                continue
            self._change_evaluation_window()

    def _build_jif_payload_for_judge(self, *, source_choice: str, mode: str) -> tuple[dict[str, Any], str]:
        if source_choice == "1":
            default = 1 if mode == "single_run" else self.session_config.evaluation_window
            run_count = self._prompt_run_count(default=default)
            if mode == "single_run" and run_count != 1:
                raise ValueError("single-run mode requires exactly one run")
            run_paths = [str(path)
                         for path in self._get_recent_run_paths(run_count)]
            if len(run_paths) != run_count:
                raise ValueError(
                    f"requested {run_count} run(s), but only {len(run_paths)} are available")
            return export_jif(run_paths=run_paths, latest=len(run_paths)), f"latest {len(run_paths)} run(s)"

        if source_choice == "2":
            run_paths = self._read_comma_separated_paths(
                "Enter run log JSON path(s) for the judge."
            )
            if mode == "single_run" and len(run_paths) != 1:
                raise ValueError(
                    "single-run mode requires exactly one run path")
            return export_jif(run_paths=run_paths, latest=len(run_paths)), f"explicit run paths ({len(run_paths)})"

        jif_paths = self._read_comma_separated_paths(
            "Enter existing JIF JSON path(s) for the judge."
        )
        if mode == "single_run" and len(jif_paths) != 1:
            raise ValueError("single-run mode requires exactly one JIF file")
        payloads = load_jif_payloads(jif_paths)
        return merge_jif_payloads(payloads), f"existing JIF file(s) ({len(jif_paths)})"

    def _prompt_run_count(self, default: int = 1) -> int:
        self._clear_screen()
        print(f"How many runs do you want to execute? [{default}]")
        while True:
            raw_value = input("> ").strip()
            if not raw_value:
                return default
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            run_count = int(raw_value)
            if run_count <= 0:
                print("Enter a positive integer.")
                continue
            return run_count

    def _next_session_run_basename(self) -> str:
        self._session_run_counter += 1
        return build_session_run_basename(self._session_run_counter)

    def _execute_multi_run_flow(self, run_count: int) -> list[RunContext]:
        run_contexts: list[RunContext] = []
        dataset_label = self._get_selected_dataset_label()

        for run_index in range(1, run_count + 1):
            basename = self._next_session_run_basename()
            print(
                render_info(
                    "\n".join(
                        [
                            f"RUN {run_index} / {run_count}",
                            f"Run ID: {basename}",
                            f"Model: {self.session_config.model_name}",
                            f"Dataset: {dataset_label}",
                            f"Max steps: {self.session_config.max_steps}",
                        ]
                    )
                )
            )

            run_context = self._execute_run(basename=basename)
            run_contexts.append(run_context)
            print(
                render_run_summary(
                    title=f"RUN {run_index} / {run_count}",
                    run_name=basename,
                    intro_line="Completed run summary.",
                    metrics=self._build_single_run_metric_pairs(run_context),
                    top_features=list(run_context.insights.get(
                        "top_features", []))[:5],
                    errors=self._build_single_run_error_lines(run_context),
                    conclusion=f"Saved as {Path(run_context.artifact_paths['run_log_path']).name}.",
                    path_label="Run Agent / Multi-Run Execution",
                    hint="Compact summary for the completed run.",
                )
            )
            print()

        return run_contexts

    def _build_single_run_metric_pairs(self, run_context: RunContext) -> list[tuple[str, str]]:
        behavior = dict(run_context.insights.get("behavior", {}))
        return [
            ("steps", str(behavior.get("num_steps", 0))),
            ("features_attempted", str(behavior.get("unique_features_attempted", 0))),
            ("features_successful", str(behavior.get("unique_features_successful", 0))),
            ("valid_action_rate",
             f"{run_context.metrics.get('valid_action_rate', 0.0):.2f}"),
            ("tool_error_rate",
             f"{run_context.metrics.get('tool_error_rate', 0.0):.2f}"),
        ]

    def _build_single_run_error_lines(self, run_context: RunContext) -> list[str]:
        errors = list(run_context.insights.get("errors", []))[:3]
        return [
            f"{error.get('feature_name') or 'unknown'}: {error.get('error_code') or 'UNKNOWN'}"
            for error in errors
        ]

    def _build_multi_run_summary_payload(self, run_contexts: list[RunContext]) -> dict[str, Any]:
        run_paths = [context.artifact_paths["run_log_path"]
                     for context in run_contexts]
        evaluation_result = evaluate_runs(
            run_paths=run_paths, latest=len(run_paths))
        comparison_result = compare_runs(run_paths)
        aggregate = dict(evaluation_result.get("aggregate", {}))
        run_metrics_summary = dict(aggregate.get("run_metrics_summary", {}))

        tool_calls = Counter()
        tool_run_presence = Counter()
        feature_counter = Counter()

        for context in run_contexts:
            tools_in_run: set[str] = set()
            for step in list(context.run_payload.get("history", [])):
                action = step.get("action")
                if isinstance(action, str) and action:
                    tool_calls[action] += 1
                    tools_in_run.add(action)
                feature_name = (step.get("action_input")
                                or {}).get("feature_name")
                if isinstance(feature_name, str) and feature_name:
                    feature_counter[feature_name] += 1
            for tool_name in tools_in_run:
                tool_run_presence[tool_name] += 1

        metrics = [
            ("runs", str(len(run_contexts))),
            ("avg_steps", str(dict(run_metrics_summary.get(
                "steps", {})).get("average", 0.0))),
            ("avg_features_attempted", str(dict(run_metrics_summary.get(
                "features_attempted", {})).get("average", 0.0))),
            ("avg_features_successful", str(dict(run_metrics_summary.get(
                "features_successful", {})).get("average", 0.0))),
            ("avg_overlap",
             f"{comparison_result.get('average_overlap_score', 1.0):.2f}"),
        ]

        tool_usage = [
            f"- {tool}: {count} call(s) | {tool_run_presence[tool]}/{len(run_contexts)} run(s)"
            for tool, count in sorted(tool_calls.items())
        ]

        feature_summary = [
            f"- unique features explored: {len(feature_counter)}"
        ]
        feature_summary.extend(
            f"- {feature}: {count} hit(s)"
            for feature, count in feature_counter.most_common(10)
        )

        best_run = None
        ranked_runs = list(evaluation_result.get("runs", []))
        if ranked_runs:
            best_run = Path(ranked_runs[0].get("path", "")).name or None

        consistency = [
            f"- average overlap between runs: {comparison_result.get('average_overlap_score', 1.0):.2f}",
            f"- best run by deterministic score: {best_run or 'n/a'}",
        ]

        return {
            "metrics": metrics,
            "tool_usage": tool_usage,
            "feature_summary": feature_summary,
            "consistency": consistency,
        }

    def _render_multi_run_summary(self, run_contexts: list[RunContext]) -> None:
        summary = self._build_multi_run_summary_payload(run_contexts)
        self._render(
            render_multi_run_summary(
                title="Multi-Run Summary",
                intro_line=f"Executed {len(run_contexts)} run(s) sequentially with the current session configuration.",
                metrics=summary["metrics"],
                tool_usage=summary["tool_usage"],
                feature_summary=summary["feature_summary"],
                consistency=summary["consistency"],
                path_label="Home / Run Agent / Multi-Run Summary",
                hint="Aggregated view built from the completed run logs.",
            )
        )

    def _change_model_name(self) -> None:
        self._render(
            render_model_selection(OPENAI_MODEL_OPTIONS,
                                   self.session_config.model_name)
        )
        valid_choices = {str(index) for index in range(
            1, len(OPENAI_MODEL_OPTIONS) + 1)} | {"B", "Q"}
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

    def _change_judge_model_name(self) -> None:
        self._render(
            render_model_selection(OPENAI_MODEL_OPTIONS,
                                   self.session_config.judge_model_name)
        )
        valid_choices = {str(index) for index in range(
            1, len(OPENAI_MODEL_OPTIONS) + 1)} | {"B", "Q"}
        choice = self._read_menu_choice(valid_choices)
        if choice == "B":
            return
        if choice == "Q":
            self._quit()
            return

        selected_model = OPENAI_MODEL_OPTIONS[int(choice) - 1][1]
        self.session_config.judge_model_name = selected_model
        self._show_info(
            f"Judge model updated to: {self.session_config.judge_model_name}")

    def _change_dataset_partition(self) -> None:
        dataset_paths = self._get_available_dataset_paths()
        if not dataset_paths:
            self._show_error(f"no dataset partitions found under {DATA_DIR}")
            return

        self._render(
            render_dataset_selection(
                dataset_paths, self.session_config.dataset_name)
        )
        valid_choices = {str(index) for index in range(
            1, len(dataset_paths) + 1)} | {"B", "Q"}
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
        self._show_info(f"Live reasoning trace is now: {trace_value}")

    def _change_max_steps(self) -> None:
        self._clear_screen()
        print("Enter max reasoning steps for the next run:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            step_budget = int(raw_value)
            if step_budget <= 0:
                print("Enter a positive integer.")
                continue
            self.session_config.max_steps = step_budget
            self._show_info(f"Max reasoning steps set to: {step_budget}")
            return

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

    def _build_feature_reviews(self, run_context: RunContext) -> list[dict[str, Any]]:
        evidence_map = dict(run_context.insights.get("feature_evidence", {}))
        reviews: list[dict[str, Any]] = []

        for feature_name, evidence in evidence_map.items():
            if not isinstance(feature_name, str) or not isinstance(evidence, dict):
                continue

            signals = [str(signal) for signal in (evidence.get(
                "signals") or []) if isinstance(signal, str)]
            tools_used = [str(tool) for tool in (evidence.get(
                "tools_used") or []) if isinstance(tool, str)]
            status = str(evidence.get("status") or "active")
            metric_text = first_metric_text(
                dict(evidence.get("metrics", {}) or {}))
            level, why = ("high", "Partition-level evidence suggests a structural issue worth reviewing.") if feature_name == "__dataset__" else next(
                (SIGNAL_REVIEWS[signal]
                 for signal in signals if signal in SIGNAL_REVIEWS),
                (("medium", "The feature shows structural signals that justify manual review.") if signals else (
                    "low", "Evidence is still limited for a stronger conclusion.")),
            )
            if status == "weakened":
                level = "high" if level == "medium" else level
                why += " The hypothesis was revised once, so this result deserves extra caution."

            context = [
                part for part in (
                    "tools=" + ", ".join(tools_used) if tools_used else "",
                    "signals=" + ", ".join(signals[:2]) if signals else "",
                    metric_text or "",
                    f"status={status}",
                ) if part
            ]

            reviews.append(
                {
                    "name": feature_name,
                    "level": level,
                    "where": "dataset partition" if feature_name == "__dataset__" else feature_name,
                    "why": why,
                    "context": "; ".join(context),
                    "score": {"high": 3, "medium": 2, "low": 1}[level],
                }
            )

        if not reviews:
            for error in list(run_context.insights.get("errors", []))[:3]:
                feature_name = error.get("feature_name") or "unknown"
                error_code = error.get("error_code") or "UNKNOWN"
                reviews.append(
                    {
                        "name": feature_name,
                        "level": "medium",
                        "where": feature_name,
                        "why": f"The tool failed with {error_code}, so this branch of the reasoning remained unvalidated.",
                        "context": f"error_code={error_code}",
                        "score": 3,
                    }
                )

        reviews.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
        return reviews

    def _build_used_tools(self, run_context: RunContext) -> list[str]:
        tools: list[str] = []
        for step in list(run_context.run_payload.get("history", [])):
            action = step.get("action")
            if isinstance(action, str) and action and action not in tools:
                tools.append(action)
        return tools

    def _build_agent_overview_lines(self, run_context: RunContext) -> list[str]:
        behavior = dict(run_context.insights.get("behavior", {}))
        patterns = dict(run_context.insights.get("patterns", {}))
        history = list(run_context.run_payload.get("history", []))
        used_tools = self._build_used_tools(run_context)
        confirmed = list(patterns.get("confirmed_features", []))
        contradiction_count = len(
            list(run_context.run_payload.get("contradiction_memory", []))
        )
        key_actions = [
            f"{step.get('action')} on {(step.get('action_input') or {}).get('feature_name')}"
            for step in history[:4]
            if isinstance(step.get("action"), str) and step.get("action")
        ]

        if confirmed and behavior.get("used_both_tools") and behavior.get("num_errors", 0) == 0:
            quality = "high: the run combined evidence well, used multiple tools, and stayed stable"
        elif behavior.get("used_both_tools") or contradiction_count > 0:
            quality = "medium: the run revised ideas and accumulated evidence, but still needs stronger closure"
        else:
            quality = "limited: the run relied on too little evidence or too few tools"

        lines = [
            f"The run used {behavior.get('num_steps', 0)} steps and explored {behavior.get('unique_features_attempted', 0)} features.",
            f"Tools used: {', '.join(used_tools) or 'none'}.",
            f"Key actions: {'; '.join(key_actions) or 'no actions recorded'}.",
            f"Reasoning quality: {quality}.",
        ]
        if confirmed:
            lines.append(f"Useful confirmations: {', '.join(confirmed[:3])}.")
        elif contradiction_count > 0:
            lines.append(
                f"The run recorded {contradiction_count} hypothesis revisions, which suggests it did not stick to its first idea."
            )
        return lines

    def _build_review_summary_text(self, run_context: RunContext) -> str:
        behavior = dict(run_context.insights.get("behavior", {}))
        patterns = dict(run_context.insights.get("patterns", {}))
        reviews = self._build_feature_reviews(run_context)
        top_reviews = reviews[:3]
        top_features = list(run_context.insights.get("top_features", []))[:5]
        confirmed = list(patterns.get("confirmed_features", []))[:3]
        contradictions = len(
            list(run_context.run_payload.get("contradiction_memory", [])))
        errors = list(run_context.insights.get("errors", []))[:3]

        lines = [
            f"Run file: {Path(run_context.artifact_paths.get('run_log_path', '')).name or 'unknown'}",
            f"Steps: {behavior.get('num_steps', 0)}",
            f"Unique features attempted: {behavior.get('unique_features_attempted', 0)}",
            f"Unique features successful: {behavior.get('unique_features_successful', 0)}",
            f"Tools used: {', '.join(self._build_used_tools(run_context)) or 'none'}",
            f"Top features: {', '.join(top_features) or 'none'}",
            f"Confirmed features: {', '.join(confirmed) or 'none'}",
            f"Contradictions recorded: {contradictions}",
        ]
        if top_reviews:
            lines.append("Top detected issues:")
            lines.extend(
                f"- {item['name']} | risk={item['level']} | why={item['why']} | context={item['context']}"
                for item in top_reviews
            )
        if errors:
            lines.append("Observed errors:")
            lines.extend(
                f"- {error.get('feature_name') or 'unknown'} | {error.get('error_code') or 'UNKNOWN'}"
                for error in errors
            )
        return "\n".join(lines)

    def _get_review_overview(self, run_context: RunContext) -> list[str]:
        if run_context.llm_overview is not None:
            return run_context.llm_overview

        summary_text = self._build_review_summary_text(run_context)
        fallback_lines = self._build_agent_overview_lines(run_context)
        try:
            from openai import OpenAI
        except ImportError:
            run_context.llm_overview = fallback_lines
            return run_context.llm_overview

        try:
            client = OpenAI()
            response = client.responses.create(
                model=self.session_config.model_name,
                temperature=0.0,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You explain audit runs for researchers. "
                            "Respond in English only. "
                            "Use 3 to 5 short bullet lines. "
                            "Be specific to the provided run summary. "
                            "Do not repeat generic template language."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Summarize what happened in this run, why the main issues matter, "
                            "and what a researcher should inspect next.\n\n"
                            + summary_text
                        ),
                    },
                ],
            )
            overview_lines = split_bullet_lines(response.output_text)
            run_context.llm_overview = overview_lines or fallback_lines
        except Exception:
            run_context.llm_overview = fallback_lines

        return run_context.llm_overview

    def _build_technical_metric_pairs(self, run_context: RunContext) -> list[tuple[str, str]]:
        behavior = dict(run_context.insights.get("behavior", {}))
        metrics = run_context.metrics
        payload_metadata = dict(run_context.run_payload.get("metadata", {}))
        contradiction_count = len(
            list(run_context.run_payload.get("contradiction_memory", [])))
        evidence_features = len(
            dict(run_context.insights.get("feature_evidence", {})))

        return [
            ("steps", str(behavior.get("num_steps", 0))),
            ("features_attempted", str(behavior.get("unique_features_attempted", 0))),
            ("features_successful", str(behavior.get("unique_features_successful", 0))),
            ("max_steps", str(run_context.run_payload.get("max_steps", 0))),
            ("evidence_features", str(evidence_features)),
            ("contradictions", str(contradiction_count)),
            ("overview_usage", str(int(payload_metadata.get("overview_usage", 0) or 0))),
            ("valid_action_rate",
             f"{metrics.get('valid_action_rate', 0.0):.2f}"),
            ("tool_error_rate", f"{metrics.get('tool_error_rate', 0.0):.2f}"),
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
