"""Terminal rendering helpers for the NIDS CLI."""

from __future__ import annotations

from pathlib import Path
from textwrap import fill
from typing import Any

from utils.human_readable import parse_thought_fields, summarize_action, summarize_observation

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


def _wrap_line(text: str, *, initial: str = "- ", subsequent: str = "  ") -> list[str]:
    return fill(
        text,
        width=WIDTH,
        initial_indent=initial,
        subsequent_indent=subsequent,
    ).splitlines()


def _wrap_field(label: str, value: str, *, initial: str = "  ") -> list[str]:
    return fill(
        f"{label:<13} {value}",
        width=WIDTH,
        initial_indent=initial,
        subsequent_indent=" " * len(initial) + " " * 14,
    ).splitlines()


def _render_risk_cards(items: list[dict[str, str]], *, include_context: bool) -> list[str]:
    if not items:
        return ["No clear issues were detected in the analyzed evidence."]

    lines: list[str] = []
    for item in items:
        name = item.get("name", "unknown")
        level = item.get("level", "medium")
        where = item.get("where", name)
        why = item.get("why", "No explanation available.")
        context = item.get("context", "")

        lines.append(name)
        lines.extend(_wrap_field("Risk", level.upper()))
        lines.extend(_wrap_field("Where", where))
        lines.extend(_wrap_field("Why", why))
        if include_context and context:
            lines.extend(_wrap_field("Context", context))
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    return lines


def render_main_menu(
    *,
    model_name: str,
    dataset_name: str,
    trace_enabled: bool,
    max_steps: int,
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
                    ("max_steps", str(max_steps)),
                    ("live_trace", "on" if trace_enabled else "off"),
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
                    ("J", "Run Judge"),
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
    judge_model_name: str,
    dataset_name: str,
    trace_enabled: bool,
    max_steps: int,
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
                    ("judge_model", judge_model_name),
                    ("dataset", dataset_name),
                    ("max_steps", str(max_steps)),
                    ("live_trace", "on" if trace_enabled else "off"),
                    ("evaluation_window", str(evaluation_window)),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("1", "Change Model"),
                    ("2", "Change Judge Model"),
                    ("3", "Select Partition"),
                    ("4", "Toggle Live Trace"),
                    ("5", "Change Max Steps"),
                    ("6", "Change Evaluation Window"),
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
                     "Choose the OpenAI model used by the next run or enter a custom model ID."),
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
                ("C", "Custom model ID"),
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


def render_reasoning_trace(history: list[dict[str, Any]], path_label: str | None = None) -> str:
    lines: list[str] = []
    if path_label:
        lines.extend(_meta_lines(
            path_label, "Step-by-step reasoning trace in execution order."))

    if not history:
        lines.append("No steps were recorded for this run.")
        return _block("Reasoning Trace", lines)

    for step in history:
        step_id = step.get("step_id", "?")
        thought = step.get(
            "thought") or "No useful thought was recorded for this step."
        thought_fields = parse_thought_fields(thought)
        status = step.get("execution_status") or "UNKNOWN"
        observation = summarize_observation(
            step.get("observation") or {}, failure_noun="tool")

        lines.append(_rule("-"))
        lines.append(f"STEP {int(step_id):02d}" if isinstance(
            step_id, int) else f"STEP {step_id}")
        lines.extend(_wrap_field("Status", str(status)))
        lines.extend(_wrap_field(
            "Hypothesis", thought_fields.get("hypothesis") or thought))
        if thought_fields.get("scope"):
            lines.extend(_wrap_field("Scope", thought_fields["scope"]))
        if thought_fields.get("next_action"):
            lines.extend(_wrap_field("Plan", thought_fields["next_action"]))
        lines.extend(_wrap_field("Action", summarize_action(
            step.get("action"), step.get("action_input"))))
        lines.extend(_wrap_field("Observation", observation))
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    return _block("Reasoning Trace", lines)


def render_run_review(
    *,
    title: str,
    run_name: str | None,
    intro_line: str | None,
    problems: list[dict[str, str]],
    llm_overview: list[str],
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

    lines.extend(_section("Detected Issues", _render_risk_cards(
        problems, include_context=False)))
    lines.extend(_section("LLM Overview", [
                 f"- {line}" for line in llm_overview] or ["- No review summary available."]))
    if options:
        lines.extend(_section("Actions", _menu_lines(options)))
    return _block(title, lines)


def render_feature_analysis(
    items: list[dict[str, str]],
    *,
    path_label: str | None = None,
    hint: str | None = None,
) -> str:
    lines: list[str] = []
    if path_label:
        lines.extend(_meta_lines(path_label, hint))
    lines.extend(_render_risk_cards(items, include_context=True))
    return _block("Feature Analysis", lines)


def render_technical_details(
    *,
    title: str,
    run_name: str | None,
    metrics: list[tuple[str, str]],
    tools_used: list[str],
    artifact_paths: dict[str, str],
    path_label: str | None = None,
    hint: str | None = None,
) -> str:
    lines: list[str] = []
    if path_label:
        lines.extend(_meta_lines(path_label, hint))
    if run_name:
        lines.append(run_name)
        lines.append("")

    lines.extend(_section("Metrics", _kv_lines(metrics)))
    lines.extend(_section("Tools Used", [
                 f"- {tool}" for tool in tools_used] or ["- none"]))
    lines.extend(_section(
        "Artifacts",
        _kv_lines([
            ("run_log", artifact_paths.get("run_log_path", "unavailable")),
            ("metrics_log", artifact_paths.get("metrics_log_path", "unavailable")),
        ]),
    ))
    return _block(title, lines)


def render_multi_run_summary(
    *,
    title: str,
    intro_line: str | None,
    metrics: list[tuple[str, str]],
    tool_usage: list[str],
    feature_summary: list[str],
    consistency: list[str],
    path_label: str | None = None,
    hint: str | None = None,
) -> str:
    lines: list[str] = []
    if path_label:
        lines.extend(_meta_lines(path_label, hint))
    if intro_line:
        lines.append(intro_line)
        lines.append("")

    lines.extend(_section("Metrics", _kv_lines(metrics)))
    lines.extend(_section("Tool Usage", tool_usage or ["- none"]))
    lines.extend(_section("Feature Exploration",
                 feature_summary or ["- none"]))
    lines.extend(_section("Consistency", consistency or ["- none"]))
    return _block(title, lines)


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


def render_judge_source_selection(*, judge_model_name: str) -> str:
    lines = [
        *_meta_lines("Home / Run Judge / Source",
                     "Choose the judge input source."),
        *(_section("Current Judge Model", [f"- {judge_model_name}"])),
        *(_section(
            "Sources",
            _menu_lines(
                [
                    ("1", "Latest N Runs"),
                    ("2", "Explicit Run Paths"),
                    ("3", "Existing JIF File(s)"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Run Judge", lines)


def render_judge_mode_selection() -> str:
    lines = [
        *_meta_lines("Home / Run Judge / Mode", "Choose the analysis mode."),
        *(_section(
            "Modes",
            _menu_lines(
                [
                    ("1", "Multi-Run Analysis"),
                    ("2", "Single-Run Debug"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Judge Mode", lines)


def render_judge_report(
    *,
    title: str,
    mode: str,
    model_name: str,
    source_summary: str,
    report: dict[str, Any],
    path_label: str | None = None,
    hint: str | None = None,
) -> str:
    lines: list[str] = []
    if path_label:
        lines.extend(_meta_lines(path_label, hint))
    lines.extend(
        _section(
            "Report Metadata",
            _kv_lines(
                [
                    ("mode", mode),
                    ("model", model_name),
                    ("source", source_summary),
                ]
            ),
        )
    )
    lines.extend(_section("Behavior Summary", _wrap_line(
        str(report.get("behavior_summary", "No behavior summary available.")))))

    def _claim_lines(items: list[dict[str, Any]]) -> list[str]:
        if not items:
            return ["- none"]
        output: list[str] = []
        for item in items:
            output.extend(_wrap_line(str(item.get("statement", ""))))
            output.extend(_wrap_field(
                "Confidence", str(item.get("confidence", "low"))))
            output.extend(_wrap_field(
                "Evidence", ", ".join(item.get("evidence", []))))
            output.append("")
        if output and output[-1] == "":
            output.pop()
        return output

    lines.extend(_section("Key Patterns", _claim_lines(
        list(report.get("key_patterns", [])))))
    lines.extend(_section("Weaknesses", _claim_lines(
        list(report.get("weaknesses", [])))))
    lines.extend(_section("Strengths", _claim_lines(
        list(report.get("strengths", [])))))
    lines.extend(_section("Recommendations", _claim_lines(
        list(report.get("recommendations", [])))))
    return _block(title, lines)


def render_saved_judge_report(artifact_paths: dict[str, str]) -> str:
    return _block(
        "Saved Judge Report",
        [
            *_meta_lines("Run Judge / Save Report",
                         "Artifacts were written under reports/judge."),
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
