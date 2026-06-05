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


def _clean_ui_text(text: str) -> str:
    return (
        str(text)
        .replace("  <available>", "")
        .replace(" <available>", "")
        .replace(" are available", " are implemented")
        .replace("Available Models", "Models")
        .replace("Available Partitions", "Partitions")
        .replace("available models", "models")
    )


def _meta_lines(path_label: str, hint: str | None = None) -> list[str]:
    lines = [f"Path: {path_label}"]
    if hint:
        lines.append(f"Hint: {_clean_ui_text(hint)}")
    lines.append("")
    return lines


def _menu_lines(options: list[tuple[str, str]]) -> list[str]:
    return [f"[{key}] {_clean_ui_text(label)}" for key, label in options]


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
                    ("P", "Phase 3A Components"),
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


def render_phase3a_components_menu() -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components", "Phase 3A Batch Runtime, Semantic Extraction, Investigation Analysis, Hypothesis Ranking, Planner, Router, Worker, Aggregation, State Manager, Critic, Final Batch Auditor, and Tools have core run/review surfaces."),
        *(_section(
            "Components",
            [
                "[1]  Semantic Extraction  <available>",
                "[2]  Investigation Analysis  <available>",
                "[3]  Hypothesis Ranking  <available>",
                "[4]  Planner  <available>",
                "[5]  Router  <available>",
                "[6]  Worker  <available>",
                "[7]  Aggregation  <available>",
                "[8]  State Manager  <available>",
                "[9]  Critic  <available>",
                "[10] Final Batch Auditor  <available>",
                "[11] Tools",
                "[12] Phase 3A Batch Runtime",
            ],
        )),
        *(_section("Actions", _menu_lines([("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Phase 3A Components", lines)


def render_phase3a_runtime_menu(
    *,
    dataset_name: str,
    default_model_name: str,
    planning_model_name: str,
    worker_model_name: str,
    synthesis_model_name: str,
    latest_run_name: str | None,
) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Batch Runtime",
                     "Authoritative deterministic Phase 3A orchestration with ledger-first review. Grouped execution, latest-run review, and saved-run browsing are implemented; evaluate and replay remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("default_model", default_model_name),
                    ("planning_model", planning_model_name),
                    ("worker_model", worker_model_name),
                    ("synthesis_model", synthesis_model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("1", "Run Cognitive Chain"),
                    ("2", "Run Hypothesis Execution"),
                    ("3", "Run Full Round"),
                    ("4", "Run Full Batch"),
                    ("L", "Review Latest Phase 3A Batch Run"),
                    ("V", "View Saved Phase 3A Batch Runs"),
                    ("E", "Evaluate Phase 3A Batch Runs  <planned>"),
                    ("D", "Debug / Replay Phase 3A Batch Run  <planned>"),
                    ("C", "Open Session Config"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Phase 3A Batch Runtime", lines)


def render_tools_menu(*, dataset_name: str, latest_run_name: str | None, selected_tool_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Tools",
                     "Direct deterministic tools execution and artifact review. Run, inventory, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("selected_tool", selected_tool_name or "none"),
                    ("latest_tool_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Tool  <available>"),
                    ("I", "Inspect Tool Inventory  <available>"),
                    ("L", "Review Latest Tool Run  <available>"),
                    ("V", "View Saved Tool Runs  <available>"),
                    ("E", "Evaluate Tool Runs  <planned>"),
                    ("D", "Debug / Replay Tool Run  <planned>"),
                    ("C", "Tools Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Tools", lines)


def render_semantic_extraction_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Semantic Extraction",
                     "One-shot structural compression over overview evidence with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Semantic Extraction  <available>"),
                    ("L", "Review Latest Semantic Extraction Run  <available>"),
                    ("V", "View Saved Semantic Extraction Runs  <available>"),
                    ("E", "Evaluate Semantic Extraction Runs  <planned>"),
                    ("D", "Debug / Replay Semantic Extraction  <planned>"),
                    ("C", "Semantic Extraction Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Semantic Extraction", lines)


def render_investigation_analysis_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Investigation Analysis",
                     "Bounded interpretive hypothesis generation over the structural substrate with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Investigation Analysis  <available>"),
                    ("L", "Review Latest Investigation Analysis Run  <available>"),
                    ("V", "View Saved Investigation Analysis Runs  <available>"),
                    ("E", "Evaluate Investigation Analysis Runs  <planned>"),
                    ("D", "Debug / Replay Investigation Analysis  <planned>"),
                    ("C", "Investigation Analysis Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Investigation Analysis", lines)


def render_hypothesis_ranking_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Hypothesis Ranking",
                     "Bounded round-level hypothesis allocation with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Hypothesis Ranking  <available>"),
                    ("L", "Review Latest Hypothesis Ranking Run  <available>"),
                    ("V", "View Saved Hypothesis Ranking Runs  <available>"),
                    ("E", "Evaluate Hypothesis Ranking Runs  <planned>"),
                    ("D", "Debug / Replay Hypothesis Ranking  <planned>"),
                    ("C", "Hypothesis Ranking Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Hypothesis Ranking", lines)


def render_planner_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Planner",
                     "Bounded strategic investigation design over the selected hypothesis set with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Planner  <available>"),
                    ("L", "Review Latest Planner Run  <available>"),
                    ("V", "View Saved Planner Runs  <available>"),
                    ("E", "Evaluate Planner Runs  <planned>"),
                    ("D", "Debug / Replay Planner  <planned>"),
                    ("C", "Planner Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Planner", lines)


def render_router_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Router",
                     "Bounded operational decomposition over one planner strategy with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Router  <available>"),
                    ("L", "Review Latest Router Run  <available>"),
                    ("V", "View Saved Router Runs  <available>"),
                    ("E", "Evaluate Router Runs  <planned>"),
                    ("D", "Debug / Replay Router  <planned>"),
                    ("C", "Router Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Router", lines)


def render_worker_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Worker",
                     "Bounded local execution over one routed worker task with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Worker  <available>"),
                    ("L", "Review Latest Worker Run  <available>"),
                    ("V", "View Saved Worker Runs  <available>"),
                    ("E", "Evaluate Worker Runs  <planned>"),
                    ("D", "Debug / Replay Worker  <planned>"),
                    ("C", "Worker Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Worker", lines)


def render_aggregation_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Aggregation",
                     "Hypothesis-local structured consolidation over committed Worker results with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Aggregation  <available>"),
                    ("L", "Review Latest Aggregation Run  <available>"),
                    ("V", "View Saved Aggregation Runs  <available>"),
                    ("H", "Browse Latest Phase3A Hypotheses  <available>"),
                    ("E", "Evaluate Aggregation Runs  <planned>"),
                    ("D", "Debug / Replay Aggregation  <planned>"),
                    ("C", "Aggregation Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Aggregation", lines)


def render_state_manager_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / State Manager",
                     "Canonical batch-state revision over one committed Aggregation handoff with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run State Manager  <available>"),
                    ("L", "Review Latest State Manager Run  <available>"),
                    ("V", "View Saved State Manager Runs  <available>"),
                    ("E", "Evaluate State Manager Runs  <planned>"),
                    ("D", "Debug / Replay State Manager  <planned>"),
                    ("C", "State Manager Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("State Manager", lines)


def render_critic_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Critic",
                     "Bounded reflective process supervision over one committed State Manager run with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Critic  <available>"),
                    ("L", "Review Latest Critic Run  <available>"),
                    ("V", "View Saved Critic Runs  <available>"),
                    ("E", "Evaluate Critic Runs  <planned>"),
                    ("D", "Debug / Replay Critic  <planned>"),
                    ("C", "Critic Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Critic", lines)


def render_final_batch_auditor_menu(*, dataset_name: str, model_name: str, latest_run_name: str | None) -> str:
    lines = [
        *_meta_lines("Home / Phase 3A Components / Final Batch Auditor",
                     "Terminal debugging-oriented batch inspection over one committed final State Manager state with artifact-first review. Run, latest-run review, and saved-run browsing are available; evaluate/debug/config remain planned."),
        *(_section(
            "Session",
            _kv_lines(
                [
                    ("dataset", dataset_name),
                    ("model", model_name),
                    ("latest_run", latest_run_name or "none"),
                ]
            ),
        )),
        *(_section(
            "Actions",
            _menu_lines(
                [
                    ("R", "Run Final Batch Auditor  <available>"),
                    ("L", "Review Latest Final Batch Audit  <available>"),
                    ("V", "View Saved Final Batch Audits  <available>"),
                    ("E", "Evaluate Final Batch Audits  <planned>"),
                    ("D", "Debug / Replay Final Batch Audit  <planned>"),
                    ("C", "Final Batch Auditor Config  <planned>"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ]
            ),
        )),
    ]
    return _block("Final Batch Auditor", lines)


def render_tool_inventory(records: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        *_meta_lines("Phase 3A Components / Tools / Inventory",
                     "Capability-oriented inventory for the admitted deterministic stack."),
    ]
    if not records:
        lines.append("No tool capability records are available.")
        return _block("Tools Inventory", lines)

    for record in records:
        lines.append(_rule("-"))
        lines.append(str(record.get("tool_name") or "unknown"))
        lines.extend(_wrap_field("Role", str(
            record.get("epistemic_role") or "unknown")))
        lines.extend(_wrap_field("Scopes", ", ".join(
            record.get("supported_scopes") or []) or "none"))
        lines.extend(_wrap_field("Inputs", ", ".join(
            record.get("required_inputs") or []) or "none"))
        lines.extend(_wrap_field("Result", str(
            record.get("result_shape") or "unknown")))
        lines.extend(_wrap_field("Bounds", str(
            record.get("boundedness_notes") or "n/a")))
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    return _block("Tools Inventory", lines)


def render_recent_tool_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Tool Runs",
            [
                *_meta_lines("Phase 3A Components / Tools / Saved Runs",
                             "Select a saved tool run directory."),
                "No tool run artifacts were found in logs/tool_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Tools / Saved Runs",
                     "Select a saved tool run directory."),
        f"Showing latest {len(paths)} tool run(s) out of limit {limit}.",
        "",
        *(_section("Available Tool Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Tool Runs", lines)


def render_recent_semantic_extraction_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Semantic Extraction Runs",
            [
                *_meta_lines("Phase 3A Components / Semantic Extraction / Saved Runs",
                             "Select a saved Semantic Extraction run directory."),
                "No Semantic Extraction run artifacts were found in logs/semantic_extraction_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Semantic Extraction / Saved Runs",
                     "Select a saved Semantic Extraction run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Semantic Extraction Runs", lines)


def render_recent_investigation_analysis_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Investigation Analysis Runs",
            [
                *_meta_lines("Phase 3A Components / Investigation Analysis / Saved Runs",
                             "Select a saved Investigation Analysis run directory."),
                "No Investigation Analysis run artifacts were found in logs/investigation_analysis_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Investigation Analysis / Saved Runs",
                     "Select a saved Investigation Analysis run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Investigation Analysis Runs", lines)


def render_recent_hypothesis_ranking_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Hypothesis Ranking Runs",
            [
                *_meta_lines("Phase 3A Components / Hypothesis Ranking / Saved Runs",
                             "Select a saved Hypothesis Ranking run directory."),
                "No Hypothesis Ranking run artifacts were found in logs/hypothesis_ranking_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Hypothesis Ranking / Saved Runs",
                     "Select a saved Hypothesis Ranking run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Hypothesis Ranking Runs", lines)


def render_recent_planner_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Planner Runs",
            [
                *_meta_lines("Phase 3A Components / Planner / Saved Runs",
                             "Select a saved Planner run directory."),
                "No Planner run artifacts were found in logs/planner_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Planner / Saved Runs",
                     "Select a saved Planner run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Planner Runs", lines)


def render_recent_router_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Router Runs",
            [
                *_meta_lines("Phase 3A Components / Router / Saved Runs",
                             "Select a saved Router run directory."),
                "No Router run artifacts were found in logs/router_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Router / Saved Runs",
                     "Select a saved Router run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Router Runs", lines)


def render_recent_worker_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Worker Runs",
            [
                *_meta_lines("Phase 3A Components / Worker / Saved Runs",
                             "Select a saved Worker run directory."),
                "No Worker run artifacts were found in logs/worker_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Worker / Saved Runs",
                     "Select a saved Worker run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Worker Runs", lines)


def render_recent_aggregation_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Aggregation Runs",
            [
                *_meta_lines("Phase 3A Components / Aggregation / Saved Runs",
                             "Select a saved Aggregation run directory."),
                "No Aggregation run artifacts were found in logs/aggregation_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Aggregation / Saved Runs",
                     "Select a saved Aggregation run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Aggregation Runs", lines)


def render_recent_state_manager_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved State Manager Runs",
            [
                *_meta_lines("Phase 3A Components / State Manager / Saved Runs",
                             "Select a saved State Manager run directory."),
                "No State Manager run artifacts were found in logs/state_manager_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / State Manager / Saved Runs",
                     "Select a saved State Manager run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved State Manager Runs", lines)


def render_recent_critic_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Critic Runs",
            [
                *_meta_lines("Phase 3A Components / Critic / Saved Runs",
                             "Select a saved Critic run directory."),
                "No Critic run artifacts were found in logs/critic_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Critic / Saved Runs",
                     "Select a saved Critic run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Critic Runs", lines)


def render_recent_final_batch_auditor_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Final Batch Audits",
            [
                *_meta_lines("Phase 3A Components / Final Batch Auditor / Saved Runs",
                             "Select a saved Final Batch Auditor run directory."),
                "No Final Batch Auditor run artifacts were found in logs/final_batch_auditor_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Final Batch Auditor / Saved Runs",
                     "Select a saved Final Batch Auditor run directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Final Batch Audits", lines)


def render_recent_phase3a_runtime_runs(paths: list[Path], limit: int) -> str:
    if not paths:
        return _block(
            "Saved Phase 3A Batch Runs",
            [
                *_meta_lines("Phase 3A Components / Batch Runtime / Saved Runs",
                             "Select a saved Phase 3A batch runtime directory."),
                "No Phase 3A batch runtime artifacts were found in logs/phase3a_runtime_runs.",
                "",
                *(_section("Actions",
                  _menu_lines([("B", "Back"), ("Q", "Quit")]))),
            ],
        )

    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Saved Runs",
                     "Select a saved Phase 3A batch runtime directory."),
        f"Showing latest {len(paths)} run(s) out of limit {limit}.",
        "",
        *(_section("Available Runs",
          [f"[{index}] {path.name}" for index, path in enumerate(paths, start=1)])),
        *(_section("Actions",
          _menu_lines([("N", "Change number of visible runs"), ("B", "Back"), ("Q", "Quit")]))),
    ]
    return _block("Saved Phase 3A Batch Runs", lines)


def render_tool_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Tools / Review",
                     "Inspect normalized inputs, raw output, parsed output, validation, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("request", artifact_paths.get(
                        "tool_call_request_path", "unavailable")),
                    ("parsed_output", artifact_paths.get(
                        "parsed_output_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Tool Run Review", lines)


def render_semantic_extraction_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Semantic Extraction / Review",
                     "Inspect inputs, substrate, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("overview_input", artifact_paths.get(
                        "overview_summary_min_path", "unavailable")),
                    ("parsed_output", artifact_paths.get(
                        "parsed_output_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Semantic Extraction Review", lines)


def render_investigation_analysis_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Investigation Analysis / Review",
                     "Inspect substrate inputs, hypothesis outputs, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("semantic_substrate", artifact_paths.get(
                        "semantic_substrate_path", "unavailable")),
                    ("parsed_output", artifact_paths.get(
                        "parsed_output_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Investigation Analysis Review", lines)


def render_hypothesis_ranking_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Hypothesis Ranking / Review",
                     "Inspect candidate inputs, selection decision, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("candidate_hypotheses", artifact_paths.get(
                        "candidate_hypotheses_path", "unavailable")),
                    ("parsed_output", artifact_paths.get(
                        "parsed_output_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Hypothesis Ranking Review", lines)


def render_planner_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Planner / Review",
                     "Inspect planning inputs, strategy bundle, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("ranking_decision_min", artifact_paths.get(
                        "ranking_decision_min_path", "unavailable")),
                    ("parsed_output", artifact_paths.get(
                        "parsed_output_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Planner Review", lines)


def render_router_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Router / Review",
                     "Inspect planner strategy input, reduced context, task bundle, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("planner_strategy", artifact_paths.get(
                        "planner_strategy_path", "unavailable")),
                    ("parsed_output", artifact_paths.get(
                        "parsed_output_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Router Review", lines)


def render_worker_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    latest_step_lines: list[str] | None = None,
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Worker / Review",
                     "Inspect worker task inputs, step trace, validation, prompt-response history, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section("Latest Step (Default)",
          latest_step_lines or ["No persisted Worker step timeline is available."])),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("worker_task", artifact_paths.get(
                        "worker_task_path", "unavailable")),
                    ("worker_result", artifact_paths.get(
                        "worker_result_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Worker Review", lines)


def render_aggregation_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Aggregation / Review",
                     "Inspect worker-result inputs, overlap diagnostics, merged handoff, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("worker_result_set", artifact_paths.get(
                        "worker_result_set_path", "unavailable")),
                    ("aggregation_handoff", artifact_paths.get(
                        "aggregation_handoff_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Aggregation Review", lines)


def render_state_manager_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / State Manager / Review",
                     "Inspect prior state, state delta, updated canonical state, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("prior_state", artifact_paths.get(
                        "prior_state_path", "unavailable")),
                    ("updated_batch_state", artifact_paths.get(
                        "updated_batch_state_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("State Manager Review", lines)


def render_critic_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Critic / Review",
                     "Inspect critic input summaries, observations payload, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("critic_input_bundle", artifact_paths.get(
                        "critic_input_bundle_path", "unavailable")),
                    ("critic_observations", artifact_paths.get(
                        "critic_observations_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Critic Review", lines)


def render_final_batch_auditor_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Final Batch Auditor / Review",
                     "Inspect final audit input refs, debugging report, validation, prompt-response text, and artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("final_audit_input", artifact_paths.get(
                        "final_audit_input_path", "unavailable")),
                    ("debugging_audit_report", artifact_paths.get(
                        "debugging_audit_report_path", "unavailable")),
                    ("validation", artifact_paths.get(
                        "validation_report_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Final Batch Auditor Review", lines)


def render_phase3a_runtime_run_review(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    artifact_paths: dict[str, str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Debugger",
                     "Inspect the persisted execution tree for this batch run, then drill into semantic extraction, rounds, hypotheses, statement, critic, and technical artifacts."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section(
            "Artifacts",
            _kv_lines(
                [
                    ("component_run", artifact_paths.get(
                        "component_run_path", "unavailable")),
                    ("batch_ledger", artifact_paths.get(
                        "batch_ledger_path", "unavailable")),
                    ("initial_state", artifact_paths.get(
                        "initial_state_path", "unavailable")),
                    ("finalization", artifact_paths.get(
                        "finalization_summary_path", "unavailable")),
                ]
            ),
        )),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Runtime Execution Tree", lines)


def render_phase3a_runtime_rounds_index(
    *,
    run_name: str,
    round_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Review / Rounds",
                     "Select a persisted round manifest to inspect its frozen snapshot and execution lineage."),
        run_name,
        "",
        *(_section("Rounds", round_lines or ["No round manifests are available."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Runtime Rounds", lines)


def render_phase3a_runtime_round_review(
    *,
    round_id: str,
    summary_pairs: list[tuple[str, str]],
    artifact_pairs: list[tuple[str, str]],
    default_hypothesis_lines: list[str] | None = None,
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Review / Round",
                     "Inspect the frozen snapshot and persisted component lineage for one round."),
        round_id,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section("Default Hypothesis", default_hypothesis_lines or [
          "No persisted hypothesis execution is available for this round."])),
        *(_section("Artifacts", _kv_lines(artifact_pairs))),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Round Review", lines)


def render_phase3a_runtime_inter_hypothesis_aggregation_review(
    *,
    round_id: str,
    summary_pairs: list[tuple[str, str]],
    synthesis_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Review / Round / Inter-Hypothesis Aggregation",
                     "Inspect the persisted round-level cross-hypothesis aggregation record before any state updates are committed."),
        round_id,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section("Hypothesis Syntheses",
          synthesis_lines or ["No persisted inter-hypothesis synthesis records are available."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Inter-Hypothesis Aggregation", lines)


def render_phase3a_runtime_hypothesis_index(
    *,
    round_id: str,
    hypothesis_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Review / Hypotheses",
                     "Select a hypothesis execution lineage to inspect Router, Worker, Aggregation, and State Manager artifacts."),
        round_id,
        "",
        *(_section("Hypothesis Lineage",
          hypothesis_lines or ["No hypothesis executions were recorded for this round."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Hypothesis Lineage", lines)


def render_phase3a_runtime_hypothesis_review(
    *,
    hypothesis_id: str,
    summary_pairs: list[tuple[str, str]],
    artifact_pairs: list[tuple[str, str]],
    default_worker_lines: list[str] | None = None,
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Review / Hypothesis",
                     "Inspect the persisted execution lineage for one hypothesis within a round."),
        hypothesis_id,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section("Default Worker Task", default_worker_lines or [
          "No persisted Worker task is available for this hypothesis."])),
        *(_section("Artifacts", _kv_lines(artifact_pairs))),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Hypothesis Review", lines)


def render_phase3a_runtime_worker_index(
    *,
    hypothesis_id: str,
    worker_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Review / Hypothesis / Workers",
                     "Select a Worker task execution to inspect bounded task inputs, step timeline, and final result."),
        hypothesis_id,
        "",
        *(_section("Worker Tasks",
          worker_lines or ["No Worker executions were recorded for this hypothesis."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Worker Tasks", lines)


def render_phase3a_runtime_event_stream_index(
    *,
    run_name: str,
    summary_pairs: list[tuple[str, str]],
    event_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Debugger / Event Stream",
                     "Select a persisted runtime event to inspect structured metadata and captured terminal lines."),
        run_name,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section("Events",
          event_lines or ["No persisted runtime events are available."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Runtime Event Stream", lines)


def render_phase3a_runtime_event_review(
    *,
    event_label: str,
    summary_pairs: list[tuple[str, str]],
    focus_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Batch Runtime / Debugger / Event",
                     "Inspect one persisted runtime event with its structured payload and captured terminal replay lines."),
        event_label,
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section("Focus",
          focus_lines or ["No additional event context is available."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Phase 3A Runtime Event Review", lines)


def render_worker_step_index(
    *,
    task_id: str,
    step_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Worker / Review / Steps",
                     "Select a persisted Worker step to inspect prompt, response, parsed output, actions, retries, and flags."),
        task_id,
        "",
        *(_section("Step Timeline",
          step_lines or ["No persisted Worker steps are available."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Worker Step Timeline", lines)


def render_worker_step_review(
    *,
    task_id: str,
    step_label: str,
    summary_pairs: list[tuple[str, str]],
    focus_lines: list[str],
    options: list[tuple[str, str]],
) -> str:
    lines = [
        *_meta_lines("Phase 3A Components / Worker / Review / Step",
                     "Inspect one Worker step across attempts, prompt-response text, parser output, execution history, and local action results."),
        f"{task_id} / {step_label}",
        "",
        *(_section("Summary", _kv_lines(summary_pairs))),
        *(_section("Focus",
          focus_lines or ["No additional step context is available."])),
        *(_section("Actions", _menu_lines(options))),
    ]
    return _block("Worker Step Review", lines)


def render_tool_json_view(*, title: str, path_label: str, payload: Any, hint: str | None = None) -> str:
    import json

    lines = [*_meta_lines(path_label, hint)]
    lines.extend(json.dumps(payload, indent=2, ensure_ascii=True).splitlines())
    return _block(title, lines)


def render_text_view(*, title: str, path_label: str, content: str, hint: str | None = None) -> str:
    lines = [*_meta_lines(path_label, hint)]
    lines.extend(str(content or "").splitlines() or [""])
    return _block(title, lines)


def render_session_config(
    *,
    model_name: str,
    planning_model_name: str,
    worker_model_name: str,
    synthesis_model_name: str,
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
                    ("default_model", model_name),
                    ("planning_model", planning_model_name),
                    ("worker_model", worker_model_name),
                    ("synthesis_model", synthesis_model_name),
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
                    ("1", "Change Default Model"),
                    ("2", "Change Planning Model"),
                    ("3", "Change Worker Model"),
                    ("4", "Change Synthesis Model"),
                    ("5", "Change Judge Model"),
                    ("6", "Select Partition"),
                    ("7", "Toggle Live Trace"),
                    ("8", "Change Max Steps"),
                    ("9", "Change Evaluation Window"),
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
            "Partitions",
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


def render_model_selection(
    models: list[tuple[str, str]],
    current_name: str,
    *,
    description: str = "Choose one of the models or enter a custom model ID.",
    section_title: str = "Models",
    extra_actions: list[tuple[str, str]] | None = None,
) -> str:
    actions = list(extra_actions or [])
    actions.extend([
        ("C", "Custom model ID"),
        ("B", "Back"),
        ("Q", "Quit"),
    ])
    lines = [
        *_meta_lines("Home / Session Config / Model",
                     description),
        *(_section(
            section_title,
            [
                f"[{index}] {label}{'  <current>' if model == current_name else ''}"
                for index, (label, model) in enumerate(models, start=1)
            ]
        )),
        *(_section(
            "Actions",
            _menu_lines(actions)
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
