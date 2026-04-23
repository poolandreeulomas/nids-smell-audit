"""Terminal rendering helpers for the NIDS CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

WIDTH = 68


def _rule(char: str = "=") -> str:
    return char * WIDTH


def _block(title: str, lines: list[str] | None = None, char: str = "=") -> str:
    output = [_rule(char), title, _rule(char)]
    if lines:
        output.extend(lines)
    return "\n".join(output)


def _section(title: str, lines: list[str]) -> list[str]:
    return [title, "-" * len(title), *lines, ""]


def _meta_lines(path_label: str, hint: str | None = None) -> list[str]:
    lines = [f"Path: {path_label}"]
    if hint:
        lines.append(f"Hint: {hint}")
    lines.append("")
    return lines


def _menu_lines(options: list[tuple[str, str]]) -> list[str]:
    return [f"[{key}] {label}" for key, label in options]


def _kv_lines(pairs: list[tuple[str, str]]) -> list[str]:
    if not pairs:
        return ["- none"]
    width = max(len(key) for key, _ in pairs)
    return [f"- {key:<{width}} : {value}" for key, value in pairs]


def render_main_menu(
    *,
    model_name: str,
    dataset_name: str,
    trace_enabled: bool,
    evaluation_window: int,
    stored_runs_count: int,
    has_cli_run: bool,
) -> str:
    lines = [
        "Interactive research console for MVP runs.",
        "",
        *_meta_lines("Home", "Type one letter and press Enter."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("model", model_name),
                    ("dataset", dataset_name),
                    ("trace", "on" if trace_enabled else "off"),
                    ("eval_window", str(evaluation_window)),
                ]
            ),
        )),
        *(_section(
            "Workspace",
            _kv_lines(
                [
                    ("stored_runs", str(stored_runs_count)),
                    ("last_cli_run", "yes" if has_cli_run else "no"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Agent"),
                    ("L", "Latest Run"),
                    ("V", "View Runs"),
                    ("E", "Evaluate Runs"),
                    ("M", "Session Config"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("NIDS Agent CLI", lines)


def render_session_config(
    *,
    model_name: str,
    dataset_name: str,
    trace_enabled: bool,
    evaluation_window: int,
) -> str:
    lines = [
        *_meta_lines("Home / Session Config",
                     "Changes affect only this session."),
        *(_section(
            "Current Session Configuration",
            _kv_lines(
                [
                    ("model", model_name),
                    ("dataset", dataset_name),
                    ("trace", "on" if trace_enabled else "off"),
                    ("evaluation_window", str(evaluation_window)),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("1", "Change Model"),
                    ("2", "Select Partition"),
                    ("3", "Toggle Trace"),
                    ("4", "Change Evaluation Window"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Session Config", lines)


def render_dataset_selection(paths: list[Path], current_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Session Config / Dataset",
                     "Choose the partition used by the next run."),
        *(_section(
            "Available Partitions",
            [
                f"[{index}] {path.name}{'  <current>' if path.name == current_name else ''}"
                for index, path in enumerate(paths, start=1)
            ] or ["none"]
        )),
        *(_section(
            "Actions",
            _menu_lines([
                ("B", "Back"),
                ("Q", "Quit"),
            ])
        )),
    ]
    return _block("Dataset Partition", lines)


def render_model_selection(models: list[tuple[str, str]], current_name: str) -> str:
    lines = [
        *_meta_lines("Home / Session Config / Model",
                     "Choose the OpenAI model used by the next run."),
        *(_section(
            "Available Models",
            [
                f"[{index}] {label}{'  <current>' if model == current_name else ''}"
                for index, (label, model) in enumerate(models, start=1)
            ]
        )),
        *(_section(
            "Actions",
            _menu_lines([
                ("B", "Back"),
                ("Q", "Quit"),
            ])
        )),
    ]
    return _block("Model Selection", lines)


def render_run_summary(
    *,
    title: str,
    run_name: str | None,
    intro_line: str | None,
    metrics: list[tuple[str, str]],
    top_features: list[str],
    errors: list[str],
    conclusion: str,
    options: list[tuple[str, str]] | None = None,
    path_label: str | None = None,
    hint: str | None = None,
) -> str:
    lines: list[str] = []
    if path_label:
        lines.extend(_meta_lines(path_label, hint))
    if run_name:
        lines.append(run_name)
        lines.append("")
    if intro_line:
        lines.append(intro_line)
        lines.append("")

    lines.extend(_section("Metrics", _kv_lines(metrics)))
    if top_features:
        lines.extend(_section("Top Features", [
                     f"{index}. {name}" for index, name in enumerate(top_features, start=1)]))
    else:
        lines.extend(_section("Top Features", ["none"]))

    if errors:
        lines.extend(_section("Errors", [f"- {item}" for item in errors]))
    else:
        lines.extend(_section("Errors", ["none"]))

    lines.extend(_section("Conclusion", [conclusion]))
    if options:
        lines.extend(_section("Actions", _menu_lines(options)))
    return _block(title, lines)


def render_step_by_step(history: list[dict[str, Any]], path_label: str | None = None) -> str:
    lines: list[str] = []
    if path_label:
        lines.extend(_meta_lines(
            path_label, "Read-only inspection of stored steps."))

    if not history:
        lines.append("No steps were recorded.")
        return _block("Step-by-Step", lines)

    for step in history:
        action_input = step.get("action_input") or {}
        observation = step.get("observation") or {}
        feature_name = action_input.get("feature_name") or "n/a"
        lines.append(f"Step {step.get('step_id', '?')}")
        lines.append(f"- action     : {step.get('action') or 'n/a'}")
        lines.append(f"- feature    : {feature_name}")
        lines.append(
            f"- status     : {step.get('execution_status') or 'UNKNOWN'}")
        if observation.get("value") is not None:
            lines.append(f"- value      : {observation.get('value')}")
        if observation.get("error_code"):
            lines.append(f"- error_code : {observation.get('error_code')}")
        lines.append("")
    return _block("Step-by-Step", lines[:-1] if lines and lines[-1] == "" else lines)


def render_artifact_paths(artifact_paths: dict[str, str]) -> str:
    pairs = []
    run_log_path = artifact_paths.get("run_log_path")
    metrics_log_path = artifact_paths.get("metrics_log_path")
    if run_log_path:
        pairs.append(("run_log", run_log_path))
    if metrics_log_path:
        pairs.append(("metrics_log", metrics_log_path))

    lines = [
        *_meta_lines("Artifacts",
                     "Use these paths directly from VS Code or the terminal."),
        *(_section("Artifacts", _kv_lines(pairs))),
        "Automatic file opening is disabled in the CLI.",
        "Use these paths directly from the editor or terminal.",
    ]
    return _block("Artifact Paths", lines)


def render_run_json_path(run_log_path: str) -> str:
    return _block("Raw JSON Path", [*_meta_lines("Artifacts / Raw JSON"), run_log_path or "unavailable"])


def render_recent_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "View Runs",
            [
                *_meta_lines("Home / View Runs",
                             "Select a run number, or use N to change the list size."),
                "No run logs were found in logs/runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Home / View Runs",
                     "Select a run number, or use N to change the list size."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("View Runs", lines)


def render_evaluation_overview(result: dict[str, Any], latest: int, options: list[tuple[str, str]] | None = None) -> str:
    aggregate = dict(result.get("aggregate", {}))
    executive_summary = dict(aggregate.get("executive_summary", {}))
    score_summary = dict(aggregate.get("score_summary", {}))
    run_metrics_summary = dict(aggregate.get("run_metrics_summary", {}))
    top1_frequency = dict(aggregate.get("top1_frequency", {}))
    feature_frequency = dict(executive_summary.get("feature_frequency", {}))
    confirmed_frequency = dict(feature_frequency.get("confirmed_features", {}))
    error_frequency = dict(executive_summary.get("error_frequency", {}))

    def _summary_value(summary: dict[str, Any], key: str) -> str:
        metric_summary = dict(summary.get(key, {}))
        return str(metric_summary.get("median", 0.0))

    metric_pairs = [
        ("runs_analyzed", str(aggregate.get("run_count", 0))),
        ("average_score", f"{score_summary.get('average', 0.0)}/100"),
        ("median_score", f"{score_summary.get('median', 0.0)}/100"),
        ("median_steps", _summary_value(run_metrics_summary, "steps")),
        ("median_errors", _summary_value(run_metrics_summary, "errors")),
        ("median_attempted", _summary_value(
            run_metrics_summary, "features_attempted")),
        ("median_successful", _summary_value(
            run_metrics_summary, "features_successful")),
        ("median_valid_action",
         f"{dict(run_metrics_summary.get('valid_action_rate', {})).get('median', 0.0):.2f}"),
        ("median_tool_error",
         f"{dict(run_metrics_summary.get('tool_error_rate', {})).get('median', 0.0):.2f}"),
        ("both_tools_rate", f"{aggregate.get('both_tools_rate', 0.0):.2f}"),
        ("error_reaction_rate",
         f"{aggregate.get('error_reaction_rate', 0.0):.2f}"),
    ]

    top_feature_lines = [
        f"{feature_name}: {count} run(s)"
        for feature_name, count in list(top1_frequency.items())[:3]
    ]
    if confirmed_frequency:
        top_feature_lines.extend(
            f"confirmed {feature_name}: {count} run(s)"
            for feature_name, count in list(confirmed_frequency.items())[:3]
        )

    error_lines = [
        f"{error_key}: {count} run(s)"
        for error_key, count in list(error_frequency.items())[:5]
    ]

    conclusion_parts = [executive_summary.get(
        "headline", "No evaluation summary available.")]
    discoveries = list(executive_summary.get("discoveries", []))
    limitations = list(executive_summary.get("limitations", []))
    if discoveries:
        conclusion_parts.append("Key pattern: " + discoveries[0])
    if limitations:
        conclusion_parts.append("Main limitation: " + limitations[0])

    lines = [
        *_meta_lines("Home / Evaluate Runs",
                     "Deterministic multi-run analysis over the current session window."),
        f"Latest window: {latest} run(s)",
        "",
        *(_section("Metrics", _kv_lines(metric_pairs))),
    ]

    lines.extend(_section("Top Features", top_feature_lines or ["none"]))
    lines.extend(_section("Errors", error_lines or ["none"]))
    lines.extend(_section("Conclusion", conclusion_parts))

    if options:
        lines.extend(_section("Actions", _menu_lines(options)))
    return _block("Evaluate Runs", lines)


def render_evaluation_ranking(result: dict[str, Any]) -> str:
    runs = list(result.get("runs", []))
    if not runs:
        return _block("Full Ranking", [*_meta_lines("Evaluate Runs / Full Ranking"), "No runs are available in this evaluation window."])

    lines: list[str] = [*_meta_lines("Evaluate Runs / Full Ranking",
                                     "Runs are ordered by deterministic evaluation score.")]
    for index, run_summary in enumerate(runs, start=1):
        score = dict(run_summary.get("score", {}))
        run_name = Path(run_summary.get("path", "")).name or "unknown"
        lines.append(f"{index}. {run_name}")
        lines.append(
            f"- score        : {score.get('score', 0.0)}/100 ({score.get('verdict', 'unknown')})")
        lines.append(
            f"- top_features : {', '.join(run_summary.get('top_features', [])) or 'none'}")
        lines.append("")
    return _block("Full Ranking", lines[:-1] if lines and lines[-1] == "" else lines)


def render_evaluation_aggregate(result: dict[str, Any]) -> str:
    aggregate = dict(result.get("aggregate", {}))
    executive_summary = dict(aggregate.get("executive_summary", {}))
    verdict_counts = dict(aggregate.get("verdict_counts", {}))
    top1_frequency = dict(aggregate.get("top1_frequency", {}))
    error_frequency = dict(executive_summary.get("error_frequency", {}))

    lines = [
        *_meta_lines("Evaluate Runs / Aggregate Findings",
                     "Cross-run patterns over the current evaluation window."),
        *(_section("Verdict Counts",
          [f"- {verdict}: {count}" for verdict, count in verdict_counts.items()] or ["- none"])),
        *(_section("Top-1 Frequency",
          [f"- {feature_name}: {count}" for feature_name, count in top1_frequency.items()] or ["- none"])),
        *(_section("Common Failure Patterns",
          [f"- {error_key}: {count}" for error_key, count in list(error_frequency.items())[:5]] or ["- none"])),
    ]
    return _block("Aggregate Findings", lines)


def render_saved_report(artifact_paths: dict[str, str]) -> str:
    return _block(
        "Saved Evaluation Report",
        [
            *_meta_lines("Evaluate Runs / Save Report",
                         "Artifacts were written under reports/evaluations."),
            *(_section(
                "Artifacts",
                _kv_lines(
                    [
                        ("report_text", artifact_paths.get(
                            "report_text_path", "unavailable")),
                        ("report_json", artifact_paths.get(
                            "report_json_path", "unavailable")),
                    ]
                ),
            )),
        ],
    )


def render_info(message: str) -> str:
    return _block("Info", [*_meta_lines("Status"), message], char="-")


def render_error(message: str) -> str:
    return _block("Error", [*_meta_lines("Status"), message], char="!")
