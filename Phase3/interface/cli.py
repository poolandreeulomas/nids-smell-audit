"""Interactive CLI for the NIDS agent project."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
import re
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
from data.dataset_config import get_default_dataset_config
from data.loader import load_dataset
from experiments.compare_runs import compare_runs
from experiments.evaluate_runs import (
    evaluate_runs,
    render_evaluation_report,
    save_evaluation_artifacts,
)
from experiments.export_jif import export_jif
from aggregation.input_resolver import load_worker_result_set
from aggregation.runner import run_aggregation
from aggregation.runtime_artifacts import list_aggregation_run_dirs, load_aggregation_bundle
from critic.runner import run_critic
from critic.runtime_artifacts import list_critic_run_dirs, load_critic_bundle
from final_batch_auditor.runner import run_final_batch_auditor
from final_batch_auditor.runtime_artifacts import (
    list_final_batch_auditor_run_dirs,
    load_final_batch_auditor_bundle,
)
from final_batch_report.runner import run_final_batch_report
from final_batch_report.runtime_artifacts import (
    list_final_batch_report_run_dirs,
    load_final_batch_report_bundle,
)
from state.schema import CanonicalBatchState
from phase3_runtime.context_builder import build_round_snapshot
from phase3_runtime.inter_hypothesis_aggregation import (
    DEFAULT_INTER_HYPOTHESIS_DIR,
    load_inter_hypothesis_bundle,
)
from phase3_runtime.orchestrator import run_phase3a_batch
from phase3_runtime.runtime_artifacts import (
    list_phase3a_runtime_run_dirs,
    load_phase3a_runtime_bundle,
)
from interface.phase3a_observability import WorkerStepTrace, build_worker_step_traces
from interface.terminal_ui import (
    render_aggregation_menu,
    render_aggregation_run_review,
    render_critic_menu,
    render_critic_run_review,
    render_final_batch_auditor_menu,
    render_final_batch_auditor_run_review,
    render_final_batch_report_config_menu,
    render_final_batch_report_menu,
    render_final_batch_report_run_review,
    render_final_batch_report_post_run,
    render_recent_final_batch_report_runs,
    render_phase3a_runtime_event_review,
    render_phase3a_runtime_event_stream_index,
    render_phase3a_runtime_menu,
    render_phase3a_runtime_hypothesis_index,
    render_phase3a_runtime_hypothesis_review,
    render_phase3a_runtime_inter_hypothesis_aggregation_review,
    render_phase3a_runtime_round_review,
    render_phase3a_runtime_rounds_index,
    render_phase3a_runtime_run_review,
    render_phase3a_runtime_worker_index,
    render_hypothesis_ranking_menu,
    render_hypothesis_ranking_run_review,
    render_investigation_analysis_menu,
    render_investigation_analysis_run_review,
    render_planner_menu,
    render_planner_run_review,
    render_recent_aggregation_runs,
    render_recent_router_runs,
    render_phase3a_components_menu,
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
    render_recent_critic_runs,
    render_recent_final_batch_auditor_runs,
    render_recent_phase3a_runtime_runs,
    render_recent_planner_runs,
    render_recent_hypothesis_ranking_runs,
    render_recent_investigation_analysis_runs,
    render_router_menu,
    render_router_run_review,
    render_recent_state_manager_runs,
    render_recent_worker_runs,
    render_reasoning_trace,
    render_recent_runs,
    render_recent_semantic_extraction_runs,
    render_recent_tool_runs,
    render_run_review,
    render_run_summary,
    render_saved_judge_report,
    render_saved_report,
    render_semantic_extraction_menu,
    render_semantic_extraction_run_review,
    render_session_config,
    render_state_manager_menu,
    render_state_manager_run_review,
    render_technical_details,
    render_text_view,
    render_tool_inventory,
    render_tool_json_view,
    render_tool_run_review,
    render_tools_menu,
    render_worker_menu,
    render_worker_run_review,
    render_worker_step_index,
    render_worker_step_review,
)
from hypothesis_ranking.context_resolver import build_ranking_state_min
from hypothesis_ranking.runner import run_hypothesis_ranking
from hypothesis_ranking.runtime_artifacts import (
    list_hypothesis_ranking_run_dirs,
    load_hypothesis_ranking_bundle,
)
from investigation_analysis.input_builder import build_analysis_context_min
from investigation_analysis.runner import run_investigation_analysis
from investigation_analysis.runtime_artifacts import (
    list_investigation_analysis_run_dirs,
    load_investigation_analysis_bundle,
)
from planner.context_resolver import (
    build_planner_round_context,
    collect_related_substrate_refs,
    resolve_selected_hypothesis_context,
)
from planner.runner import run_planner
from planner.runtime_artifacts import list_planner_run_dirs, load_planner_bundle
from judge.judge_runner import load_jif_payloads, merge_jif_payloads, run_judge
from main import build_phase3a_llm_callables, main as run_main
from router.context_reducer import build_router_context_min
from router.runner import run_router
from router.runtime_artifacts import list_router_run_dirs, load_router_bundle
from semantic_extraction.input_builder import build_overview_summary_min, build_partition_context
from semantic_extraction.runner import run_semantic_extraction
from semantic_extraction.runtime_artifacts import (
    list_semantic_extraction_run_dirs,
    load_semantic_extraction_bundle,
)
from state.store import init_canonical_batch_state
from state_manager.runner import run_state_manager
from state_manager.runtime_artifacts import (
    list_state_manager_run_dirs,
    load_state_manager_bundle,
)
from tools.contracts import build_tool_call_request
from tools.execution import execute_tool_call
from tools.registry import get_tool_capability_record, get_tool_capability_records
from tools.runtime_artifacts import list_tool_run_dirs, load_tool_run_bundle
from utils.human_readable import first_metric_text, split_bullet_lines
from utils.metrics import state_metrics_payload
from utils.openai_response import extract_response_text
from utils.run_logging import DEFAULT_RUNS_DIR, build_session_run_basename, get_next_run_index, load_json, save_run_artifacts
from worker.contracts import DEFAULT_MAX_RETRIES, DEFAULT_MAX_WORKER_STEPS
from worker.runner import run_worker
from worker.runtime_artifacts import list_worker_run_dirs, load_worker_bundle

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
    planning_model_name: str | None = None
    worker_model_name: str | None = None
    synthesis_model_name: str | None = None
    critic_model_name: str | None = None
    judge_model_name: str = "gpt-4.1"
    dataset_name: str | None = None
    trace_enabled: bool = False
    enable_neighborhood_consistency_analysis: bool = True
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


@dataclass
class ToolRunContext:
    """Cached direct tool execution context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    tool_call_request: dict[str, Any]
    tool_capability_record: dict[str, Any]
    normalized_inputs: dict[str, Any]
    raw_tool_output: dict[str, Any]
    parsed_output: dict[str, Any]
    validation_report: dict[str, Any]
    tool_metrics: dict[str, Any]
    cache_record: dict[str, Any] | None = None


@dataclass
class SemanticExtractionRunContext:
    """Cached Semantic Extraction component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    overview_summary_min: dict[str, Any]
    partition_context: dict[str, Any]
    projected_evidence: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    parsed_output: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class InvestigationAnalysisRunContext:
    """Cached Investigation Analysis component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    semantic_substrate_input: dict[str, Any]
    analysis_context_min: dict[str, Any]
    analysis_iteration_context_min: dict[str, Any]
    projected_substrate: dict[str, Any]
    projected_analysis_context: dict[str, Any]
    projected_iteration_context: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    parsed_output: dict[str, Any]
    hypothesis_index: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class HypothesisRankingRunContext:
    """Cached Hypothesis Ranking component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    candidate_hypotheses: dict[str, Any]
    ranking_state_snapshot: dict[str, Any]
    projected_candidate_context: dict[str, Any]
    projected_ranking_state: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    parsed_output: dict[str, Any]
    selection_index: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class PlannerRunContext:
    """Cached Planner component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    ranking_decision_min: dict[str, Any]
    selected_hypothesis_context: dict[str, Any]
    planner_round_context: dict[str, Any]
    projected_selected_context: dict[str, Any]
    projected_planner_round_context: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    parsed_output: dict[str, Any]
    strategy_index: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class RouterRunContext:
    """Cached Router component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    planner_strategy: dict[str, Any]
    router_context_min: dict[str, Any]
    reduced_context: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    parsed_output: dict[str, Any]
    task_bundle_index: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class WorkerRunContext:
    """Cached Worker component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    worker_task: dict[str, Any]
    worker_runtime_refs: dict[str, Any]
    prompt_snapshots: list[dict[str, Any]]
    raw_model_responses: list[dict[str, Any]]
    parsed_steps: list[dict[str, Any]]
    tool_events: list[dict[str, Any]]
    retry_events: list[dict[str, Any]]
    failure_events: list[dict[str, Any]]
    worker_result: dict[str, Any]
    worker_output: dict[str, Any]
    operational_trace: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class AggregationRunContext:
    """Cached Aggregation component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    worker_result_set: dict[str, Any]
    normalized_inputs: dict[str, Any]
    overlap_diagnostics: list[dict[str, Any]]
    prompt_text: str
    raw_response_text: str
    parsed_output: dict[str, Any]
    aggregation_handoff: dict[str, Any]
    repair_attempts: list[dict[str, Any]]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class StateManagerRunContext:
    """Cached State Manager component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    prior_state: dict[str, Any]
    aggregation_handoff: dict[str, Any]
    state_manager_context: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    state_delta_record: dict[str, Any]
    updated_batch_state: dict[str, Any]
    state_update_result: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class CriticRunContext:
    """Cached Critic component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    critic_input_min: dict[str, Any]
    refined_state_summary: dict[str, Any]
    module_behavior_summaries: list[dict[str, Any]]
    process_signal_summary: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    critic_observations_payload: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class FinalBatchAuditorRunContext:
    """Cached Final Batch Auditor component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    final_audit_input: dict[str, Any]
    final_state_summary: dict[str, Any]
    round_history_summary: list[dict[str, Any]]
    process_signal_summary: dict[str, Any]
    prompt_text: str
    raw_response_text: str
    debugging_audit_report: dict[str, Any]
    validation_report: dict[str, Any]
    runtime_metrics: dict[str, Any]
    replay_metadata: dict[str, Any] | None = None


@dataclass
class FinalBatchReportRunContext:
    """Cached Final Batch Report Generator component run context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    report_markdown: str
    rendered_prompt: str
    raw_response: str
    runtime_metrics: dict[str, Any]


@dataclass
class Phase3ARuntimeRunContext:
    """Cached Phase 3A batch runtime context for CLI inspection."""

    artifact_paths: dict[str, str]
    component_run: dict[str, Any]
    batch_ledger: dict[str, Any]
    initial_runtime_context: dict[str, Any]
    initial_state: dict[str, Any]
    finalization_summary: dict[str, Any]
    runtime_metrics: dict[str, Any]
    runtime_summary: dict[str, Any] | None = None
    run_manifest: dict[str, Any] | None = None
    event_stream: list[dict[str, Any]] | None = None
    terminal_log_text: str = ""
    semantic_extraction_run: SemanticExtractionRunContext | None = None
    final_batch_auditor_run: FinalBatchAuditorRunContext | None = None
    replay_metadata: dict[str, Any] | None = None


@dataclass
class Phase3ARuntimeRoundContext:
    """Resolved round-level runtime context for CLI inspection."""

    round_manifest: dict[str, Any]
    frozen_snapshot: dict[str, Any]
    global_aggregation_summary: dict[str, Any]
    analysis_run: InvestigationAnalysisRunContext | None
    ranking_run: HypothesisRankingRunContext | None
    planner_run: PlannerRunContext | None
    critic_run: CriticRunContext | None


@dataclass
class Phase3AHypothesisLineageContext:
    """Resolved hypothesis-local execution lineage for CLI inspection."""

    hypothesis_record: dict[str, Any]
    router_run: RouterRunContext | None
    worker_runs: list[WorkerRunContext]
    aggregation_run: AggregationRunContext | None
    state_manager_run: StateManagerRunContext | None


ScreenHandler = Callable[[], str | None]

OPENAI_MODEL_OPTIONS = [
    ("Lowest cost    | gpt-4.1-nano", "gpt-4.1-nano"),
    ("Best value     | gpt-4.1-mini", "gpt-4.1-mini"),
    ("Stable full    | gpt-4.1", "gpt-4.1"),
    ("New reasoning  | gpt-5-mini", "gpt-5-mini"),
    ("Max reasoning  | gpt-5.4", "gpt-5.4"),
    ("Top tier       | gpt-5.5", "gpt-5.5"),
]

OPENAI_FULL_MODEL_IDS = [
    "gpt-4.1-nano",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-5-mini",
    "gpt-5.3",
    "gpt-5.4-nano",
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.5",
]

OPENAI_FULL_MODEL_OPTIONS = [
    (model_name, model_name)
    for model_name in OPENAI_FULL_MODEL_IDS
]

PHASE3A_PLANNING_COMPONENTS = {
    "investigation_analysis",
    "hypothesis_ranking",
    "planner",
    "router",
}
PHASE3A_WORKER_COMPONENTS = {"worker"}
PHASE3A_SYNTHESIS_COMPONENTS = {
    "aggregation",
    "state_manager",
    "critic",
    "final_batch_auditor",
}
PHASE3A_RUNTIME_MODE_LABELS = {
    "cognitive_only": "Cognitive Chain",
    "cognitive_workers": "Hypothesis Execution",
    "full_round": "Full Round",
    "full_batch": "Full Batch",
}


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
        self._view_tool_runs_limit = 5
        self._view_semantic_extraction_runs_limit = 5
        self._view_investigation_analysis_runs_limit = 5
        self._view_hypothesis_ranking_runs_limit = 5
        self._view_planner_runs_limit = 5
        self._view_router_runs_limit = 5
        self._view_worker_runs_limit = 5
        self._view_aggregation_runs_limit = 5
        self._view_state_manager_runs_limit = 5
        self._view_critic_runs_limit = 5
        self._view_final_batch_auditor_runs_limit = 5
        self._view_final_batch_report_runs_limit = 5
        self._view_phase3a_runtime_runs_limit = 5
        self._selected_view_run: RunContext | None = None
        self._last_tool_run: ToolRunContext | None = None
        self._selected_tool_run: ToolRunContext | None = None
        self._last_semantic_extraction_run: SemanticExtractionRunContext | None = None
        self._selected_semantic_extraction_run: SemanticExtractionRunContext | None = None
        self._last_investigation_analysis_run: InvestigationAnalysisRunContext | None = None
        self._selected_investigation_analysis_run: InvestigationAnalysisRunContext | None = None
        self._last_hypothesis_ranking_run: HypothesisRankingRunContext | None = None
        self._selected_hypothesis_ranking_run: HypothesisRankingRunContext | None = None
        self._last_planner_run: PlannerRunContext | None = None
        self._selected_planner_run: PlannerRunContext | None = None
        self._last_router_run: RouterRunContext | None = None
        self._selected_router_run: RouterRunContext | None = None
        self._last_worker_run: WorkerRunContext | None = None
        self._selected_worker_run: WorkerRunContext | None = None
        self._last_aggregation_run: AggregationRunContext | None = None
        self._selected_aggregation_run: AggregationRunContext | None = None
        self._last_state_manager_run: StateManagerRunContext | None = None
        self._selected_state_manager_run: StateManagerRunContext | None = None
        self._last_critic_run: CriticRunContext | None = None
        self._selected_critic_run: CriticRunContext | None = None
        self._last_final_batch_auditor_run: FinalBatchAuditorRunContext | None = None
        self._selected_final_batch_auditor_run: FinalBatchAuditorRunContext | None = None
        self._last_final_batch_report_run: FinalBatchReportRunContext | None = None
        self._selected_final_batch_report_run: FinalBatchReportRunContext | None = None
        self._last_phase3a_runtime_run: Phase3ARuntimeRunContext | None = None
        self._selected_phase3a_runtime_run: Phase3ARuntimeRunContext | None = None
        self._selected_tool_name: str | None = None
        self._session_run_counter = get_next_run_index(LOG_DIR) - 1
        self._running = True
        self._current_screen = "main"
        self._screen_handlers: dict[str, ScreenHandler] = {
            "main": self._main_menu,
            "phase3a": self._phase3a_components_menu,
            "phase3a_runtime": self._phase3a_runtime_menu,
            "semantic_extraction": self._semantic_extraction_menu,
            "investigation_analysis": self._investigation_analysis_menu,
            "hypothesis_ranking": self._hypothesis_ranking_menu,
            "planner": self._planner_menu,
            "router": self._router_menu,
            "worker": self._worker_menu,
            "aggregation": self._aggregation_menu,
            "state_manager": self._state_manager_menu,
            "critic": self._critic_menu,
            "final_batch_auditor": self._final_batch_auditor_menu,
            "final_batch_report": self._final_batch_report_menu,
            "tools": self._tools_menu,
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

        choice = self._read_letter_choice(
            {"R", "P", "J", "L", "V", "E", "M", "Q"})
        routes = {
            "P": "phase3a",
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

    def _phase3a_components_menu(self) -> str:
        self._render(render_phase3a_components_menu())
        choice = self._read_menu_choice(
            {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "B", "Q"})
        # For the Phase 3A Batch Runtime flow we prefer a cleaner menu view
        # without availability noise; re-render without the marker when the
        # user explicitly requests the batch runtime route. This preserves
        # the default detailed menu (with availability markers) for other
        # component flows and keeps backward-compatible behavior for tests.
        if choice == "12":
            sanitized = render_phase3a_components_menu().replace("  <available>", "")
            self._render(sanitized)
        if choice == "Q":
            self._quit()
            return "phase3a"
        if choice == "B":
            return "main"
        if choice == "1":
            return "semantic_extraction"
        if choice == "2":
            return "investigation_analysis"
        if choice == "3":
            return "hypothesis_ranking"
        if choice == "4":
            return "planner"
        if choice == "5":
            return "router"
        if choice == "6":
            return "worker"
        if choice == "7":
            return "aggregation"
        if choice == "8":
            return "state_manager"
        if choice == "9":
            return "critic"
        if choice == "10":
            return "final_batch_auditor"
        if choice == "12":
            return "phase3a_runtime"
        if choice == "13":
            return "final_batch_report"
        return "tools"

    def _phase3a_runtime_menu(self) -> str:
        latest_run_context = self._last_phase3a_runtime_run or self._get_latest_phase3a_runtime_run_context()
        latest_run_name = None
        if latest_run_context is not None:
            latest_run_name = Path(
                latest_run_context.artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_phase3a_runtime_menu(
                dataset_name=self._get_selected_dataset_label(),
                default_model_name=self.session_config.model_name,
                planning_model_name=self._resolve_phase3a_model_name(
                    "planner"),
                worker_model_name=self._resolve_phase3a_model_name("worker"),
                synthesis_model_name=self._resolve_phase3a_model_name(
                    "aggregation"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_menu_choice(
            {"1", "2", "3", "4", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "phase3a_runtime"
        if choice == "B":
            return "phase3a"
        if choice == "1":
            return self._run_phase3a_runtime_flow("cognitive_only")
        if choice == "2":
            return self._run_phase3a_runtime_flow("cognitive_workers")
        if choice == "3":
            return self._run_phase3a_runtime_flow("full_round")
        if choice == "4":
            return self._run_phase3a_runtime_flow("full_batch")
        if choice == "L":
            return self._latest_phase3a_runtime_run_menu()
        if choice == "C":
            return "session"
        if choice in {"E", "D"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
            }
            self._show_component_action_pending(
                component_name="Phase 3A Runtime",
                action_name=pending_actions[choice],
                implemented_summary="grouped execution, latest-run review, and saved-run browsing are available",
            )
            return "phase3a_runtime"
        return self._view_phase3a_runtime_runs_menu()

    def _semantic_extraction_menu(self) -> str:
        latest_run_name = None
        if self._last_semantic_extraction_run is not None:
            latest_run_name = Path(
                self._last_semantic_extraction_run.artifact_paths.get(
                    "component_run_path", "")
            ).parent.name or None

        self._render(
            render_semantic_extraction_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name(
                    "semantic_extraction"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "semantic_extraction"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_semantic_extraction_flow()
        if choice == "L":
            return self._latest_semantic_extraction_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Semantic Extraction",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "semantic_extraction"
        return self._view_semantic_extraction_runs_menu()

    def _tools_menu(self) -> str:
        latest_tool_run_name = None
        if self._last_tool_run is not None:
            latest_tool_run_name = Path(self._last_tool_run.artifact_paths.get(
                "component_run_path", "")).parent.name or None

        self._render(
            render_tools_menu(
                dataset_name=self._get_selected_dataset_label(),
                latest_run_name=latest_tool_run_name,
                selected_tool_name=self._selected_tool_name,
            )
        )
        choice = self._read_letter_choice(
            {"R", "I", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "tools"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_tool_flow()
        if choice == "I":
            self._print_tool_inventory()
            return "tools"
        if choice == "L":
            return self._latest_tool_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Tools",
                action_name=pending_actions[choice],
                implemented_summary="run, inventory inspection, latest-run review, and saved-run browsing are available",
            )
            return "tools"
        return self._view_tool_runs_menu()

    def _investigation_analysis_menu(self) -> str:
        latest_run_name = None
        if self._last_investigation_analysis_run is not None:
            latest_run_name = Path(
                self._last_investigation_analysis_run.artifact_paths.get(
                    "component_run_path", "")
            ).parent.name or None

        self._render(
            render_investigation_analysis_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name(
                    "investigation_analysis"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "investigation_analysis"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_investigation_analysis_flow()
        if choice == "L":
            return self._latest_investigation_analysis_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Investigation Analysis",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "investigation_analysis"
        return self._view_investigation_analysis_runs_menu()

    def _hypothesis_ranking_menu(self) -> str:
        latest_run_name = None
        if self._last_hypothesis_ranking_run is not None:
            latest_run_name = Path(
                self._last_hypothesis_ranking_run.artifact_paths.get(
                    "component_run_path", "")
            ).parent.name or None
        elif self._get_latest_hypothesis_ranking_run_context() is not None:
            latest_run_name = Path(
                self._get_latest_hypothesis_ranking_run_context(
                ).artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_hypothesis_ranking_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name(
                    "hypothesis_ranking"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "hypothesis_ranking"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_hypothesis_ranking_flow()
        if choice == "L":
            return self._latest_hypothesis_ranking_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Hypothesis Ranking",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "hypothesis_ranking"
        return self._view_hypothesis_ranking_runs_menu()

    def _planner_menu(self) -> str:
        latest_run_name = None
        if self._last_planner_run is not None:
            latest_run_name = Path(
                self._last_planner_run.artifact_paths.get(
                    "component_run_path", "")
            ).parent.name or None
        elif self._get_latest_planner_run_context() is not None:
            latest_run_name = Path(
                self._get_latest_planner_run_context().artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_planner_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name("planner"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "planner"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_planner_flow()
        if choice == "L":
            return self._latest_planner_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Planner",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "planner"
        return self._view_planner_runs_menu()

    def _router_menu(self) -> str:
        latest_run_name = None
        if self._last_router_run is not None:
            latest_run_name = Path(
                self._last_router_run.artifact_paths.get(
                    "component_run_path", "")
            ).parent.name or None
        elif self._get_latest_router_run_context() is not None:
            latest_run_name = Path(
                self._get_latest_router_run_context().artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_router_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name("router"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "router"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_router_flow()
        if choice == "L":
            return self._latest_router_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Router",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "router"
        return self._view_router_runs_menu()

    def _worker_menu(self) -> str:
        latest_run_name = None
        if self._last_worker_run is not None:
            latest_run_name = Path(
                self._last_worker_run.artifact_paths.get(
                    "component_run_path", "")
            ).parent.name or None
        elif self._get_latest_worker_run_context() is not None:
            latest_run_name = Path(
                self._get_latest_worker_run_context().artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_worker_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name("worker"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "H", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "worker"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_worker_flow()
        if choice == "L":
            return self._latest_worker_run_menu()
        if choice == "H":
            run_context = self._get_latest_phase3a_runtime_run_context()
            if run_context is None:
                self._show_error(
                    "No Phase3A batch runtime run artifacts are available.")
                return "worker"
            self._view_phase3a_runtime_rounds_menu(run_context)
            return "worker"
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Worker",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "worker"
        return self._view_worker_runs_menu()

    def _aggregation_menu(self) -> str:
        latest_run_context = self._last_aggregation_run or self._get_latest_aggregation_run_context()
        latest_run_name = None
        if latest_run_context is not None:
            latest_run_name = Path(
                latest_run_context.artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_aggregation_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name("aggregation"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "H", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "aggregation"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_aggregation_flow()
        if choice == "L":
            return self._latest_aggregation_run_menu()
        if choice == "H":
            run_context = self._get_latest_phase3a_runtime_run_context()
            if run_context is None:
                self._show_error(
                    "No Phase3A batch runtime run artifacts are available.")
                return "aggregation"
            self._view_phase3a_runtime_rounds_menu(run_context)
            return "aggregation"
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Aggregation",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "aggregation"
        return self._view_aggregation_runs_menu()

    def _state_manager_menu(self) -> str:
        latest_run_context = self._last_state_manager_run or self._get_latest_state_manager_run_context()
        latest_run_name = None
        if latest_run_context is not None:
            latest_run_name = Path(
                latest_run_context.artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_state_manager_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name("state_manager"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "state_manager"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_state_manager_flow()
        if choice == "L":
            return self._latest_state_manager_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="State Manager",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "state_manager"
        return self._view_state_manager_runs_menu()

    def _critic_menu(self) -> str:
        latest_run_context = self._last_critic_run or self._get_latest_critic_run_context()
        latest_run_name = None
        if latest_run_context is not None:
            latest_run_name = Path(
                latest_run_context.artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_critic_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name("critic"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "critic"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_critic_flow()
        if choice == "L":
            return self._latest_critic_run_menu()
        if choice in {"E", "D"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
            }
            self._show_component_action_pending(
                component_name="Critic",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "critic"
        if choice == "C":
            return self._critic_config_flow()
        return self._view_critic_runs_menu()

    def _final_batch_auditor_menu(self) -> str:
        latest_run_context = (
            self._last_final_batch_auditor_run or self._get_latest_final_batch_auditor_run_context()
        )
        latest_run_name = None
        if latest_run_context is not None:
            latest_run_name = Path(
                latest_run_context.artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_final_batch_auditor_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name(
                    "final_batch_auditor"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "E", "D", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "final_batch_auditor"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_final_batch_auditor_flow()
        if choice == "L":
            return self._latest_final_batch_auditor_run_menu()
        if choice in {"E", "D", "C"}:
            pending_actions = {
                "E": "evaluation",
                "D": "debug / replay",
                "C": "config",
            }
            self._show_component_action_pending(
                component_name="Final Batch Auditor",
                action_name=pending_actions[choice],
                implemented_summary="run, latest-run review, and saved-run browsing are available",
            )
            return "final_batch_auditor"
        return self._view_final_batch_auditor_runs_menu()

    def _final_batch_report_menu(self) -> str:
        latest_run_context = (
            self._last_final_batch_report_run or self._get_latest_final_batch_report_run_context()
        )
        latest_run_name = None
        if latest_run_context is not None:
            latest_run_name = Path(
                latest_run_context.artifact_paths.get("component_run_path", "")
            ).parent.name or None

        self._render(
            render_final_batch_report_menu(
                dataset_name=self._get_selected_dataset_label(),
                model_name=self._resolve_phase3a_model_name(
                    "final_batch_report"),
                latest_run_name=latest_run_name,
            )
        )

        choice = self._read_letter_choice(
            {"R", "L", "V", "C", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "final_batch_report"
        if choice == "B":
            return "phase3a"
        if choice == "R":
            return self._run_final_batch_report_flow()
        if choice == "L":
            return self._latest_final_batch_report_run_menu()
        if choice == "C":
            return self._final_batch_report_config_flow()
        return self._view_final_batch_report_runs_menu()

    def _final_batch_report_config_flow(self) -> str:
        """Inline config flow for the Final Batch Report Generator."""
        current_name = self._resolve_phase3a_model_name("final_batch_report")
        self._render(render_final_batch_report_config_menu(current_model_name=current_name))
        choice = self._read_menu_choice({"1", "B", "Q"})
        if choice == "Q":
            self._quit()
            return "final_batch_report"
        if choice == "B":
            return "final_batch_report"
        if choice == "1":
            selected = self._select_model_name(
                current_name=current_name,
                custom_label="final batch report model",
            )
            if selected is not None:
                self.session_config.synthesis_model_name = selected
                self._show_info(f"Final Batch Report model updated to: {selected}")
        return "final_batch_report"

    def _run_final_batch_report_flow(self) -> str:
        source_run = self._prompt_final_batch_report_source()
        if source_run is None:
            return "final_batch_report"
        if not source_run.updated_batch_state:
            print("\n[DEV FALLBACK ACTIVE] Using hardcoded updated_batch_state.json\n")

            source_run.updated_batch_state = load_json(
                r"C:\Users\Uni\Desktop\TFG\nids-smell-audit\Phase3\logs\state_manager_runs"
                r"\state_manager_run_098_09-06_hyp_8_distributional_divergence_destinat"
                r"\updated_batch_state.json"
            )
        try:
            final_state = CanonicalBatchState.from_dict(source_run.updated_batch_state)
            partition_name = self._get_selected_dataset_label()
            bundle = run_final_batch_report(
                final_state,
                partition_name,
                model_name=self._resolve_phase3a_model_name("final_batch_report"),
                log_dir=None,
            )
        except Exception as exc:
            self._show_error(f"final batch report failed: {exc}")
            return "final_batch_report"
        self._last_final_batch_report_run = FinalBatchReportRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("runtime_metrics", {})),
            report_markdown=str(bundle.get("report_markdown", "")),
            rendered_prompt=str(bundle.get("prompt_text", "")),
            raw_response=str(bundle.get("raw_response_text", "")),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
        )
        self._selected_final_batch_report_run = self._last_final_batch_report_run
        while True:
            self._render_final_batch_report_run_review(
                self._last_final_batch_report_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "final_batch_report"
            if choice == "B":
                return "final_batch_report"
            self._handle_final_batch_report_review_choice(
                choice, self._last_final_batch_report_run)

    def _render_final_batch_report_run_review(self, run_context: FinalBatchReportRunContext) -> None:
        run_name = Path(
            run_context.artifact_paths.get("component_run_path", "")
        ).parent.name or "final_batch_report_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("state_version", str(run_context.component_run.get("state_version", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("report_generated", str(bool(run_context.report_markdown))),
            ("runtime_seconds", str(run_context.runtime_metrics.get("duration_ms", 0.0) / 1000.0)),
        ]
        self._render(
            render_final_batch_report_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "View Report"),
                    ("2", "View Prompt"),
                    ("3", "View Raw Response"),
                    ("4", "View Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _handle_final_batch_report_review_choice(self, choice: str, run_context: FinalBatchReportRunContext) -> None:
        if choice == "1":
            self._render(
                render_text_view(
                    title="Final Batch Report",
                    path_label="Phase 3A Components / Final Batch Report / Review / Report",
                    content=run_context.report_markdown or "No report was generated.",
                    hint="Human-facing audit report generated from the Final Updated State.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_text_view(
                    title="Rendered Prompt",
                    path_label="Phase 3A Components / Final Batch Report / Review / Prompt",
                    content=run_context.rendered_prompt or "No prompt was recorded.",
                    hint="Exact prompt sent to the model.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_text_view(
                    title="Raw Response",
                    path_label="Phase 3A Components / Final Batch Report / Review / Raw Response",
                    content=run_context.raw_response or "No raw response was recorded.",
                    hint="Raw LLM response before parsing.",
                )
            )
            self._wait_for_enter()
            return
        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("report_length_chars", str(run_context.runtime_metrics.get("report_length_chars", 0))),
            ("investigated_findings", str(run_context.runtime_metrics.get("investigated_findings_count", 0))),
            ("additional_findings", str(run_context.runtime_metrics.get("additional_findings_count", 0))),
            ("schema_version", str(run_context.runtime_metrics.get("schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Final Batch Report Technical Details",
                run_name=Path(run_context.artifact_paths.get("component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["final_batch_report"],
                artifact_paths=run_context.artifact_paths,
                path_label="Phase 3A Components / Final Batch Report / Review / Technical Details",
                hint="Metrics and artifact paths for the report run.",
            )
        )
        self._wait_for_enter()

    def _get_latest_final_batch_report_run_context(self) -> FinalBatchReportRunContext | None:
        latest_runs = list_final_batch_report_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_final_batch_report_run_context(latest_runs[0])

    def _load_final_batch_report_run_context(self, run_dir: Path) -> FinalBatchReportRunContext:
        bundle = load_final_batch_report_bundle(run_dir)
        return FinalBatchReportRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            report_markdown=str(bundle.get("report_markdown", "")),
            rendered_prompt=str(bundle.get("rendered_prompt", "")),
            raw_response=str(bundle.get("raw_response", "")),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
        )

    def _latest_final_batch_report_run_menu(self) -> str:
        run_context = self._get_latest_final_batch_report_run_context()
        if run_context is None:
            self._show_error("No persisted Final Batch Report runs are available yet.")
            return "final_batch_report"
        self._selected_final_batch_report_run = run_context
        while True:
            self._render_final_batch_report_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "final_batch_report"
            if choice == "B":
                return "final_batch_report"
            self._handle_final_batch_report_review_choice(choice, run_context)

    def _view_final_batch_report_runs_menu(self) -> str:
        while True:
            recent_runs = list_final_batch_report_run_dirs(
                limit=self._view_final_batch_report_runs_limit
            )
            self._render(
                render_recent_final_batch_report_runs(
                    recent_runs,
                    self._view_final_batch_report_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "final_batch_report"
                return "final_batch_report"
            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "final_batch_report"
            if choice == "B":
                return "final_batch_report"
            if choice == "N":
                self._change_view_final_batch_report_runs_limit()
                continue
            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_final_batch_report_run_context(selected_dir)
            except Exception as exc:
                self._show_error(f"failed to load Final Batch Report run: {exc}")
                continue
            while True:
                self._render_final_batch_report_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "final_batch_report"
                if review_choice == "B":
                    break
                self._handle_final_batch_report_review_choice(review_choice, run_context)

    def _change_view_final_batch_report_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Final Batch Report runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_final_batch_report_runs_limit = limit
            return

    def _prompt_final_batch_report_source(self) -> StateManagerRunContext | None:
        session_run = self._last_state_manager_run
        saved_run = self._get_latest_state_manager_run_context()
        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get("component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")
        if session_run is None and saved_run is None:
            self._show_error("No State Manager run is available yet. Run State Manager first.")
            return None
        self._clear_screen()
        print("Choose Final Batch Report source State Manager run:")
        print()
        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(session_path).parent.name or "latest_session_state_manager"
            print(f"[1] Use latest session State Manager run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(saved_path).parent.name or "latest_saved_state_manager"
            print(f"[2] Use latest saved State Manager run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")
        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

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

    def _prompt_yes_no(self, prompt: str, *, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        print(f"{prompt} {suffix}")
        while True:
            raw_value = input("> ").strip().lower()
            if not raw_value:
                return default
            if raw_value in {"y", "yes"}:
                return True
            if raw_value in {"n", "no"}:
                return False
            print("Enter y or n.")

    def _read_menu_choice(self, valid_choices: set[str]) -> str:
        while True:
            raw_value = input("> ").strip().upper()
            if raw_value not in valid_choices:
                options = ", ".join(sorted(valid_choices))
                print(f"Invalid option. Choose one of: {options}")
                continue
            return raw_value

    def _read_non_empty_input(self, prompt: str) -> str:
        self._clear_screen()
        print(prompt)
        while True:
            raw_value = input("> ").strip()
            if raw_value:
                return raw_value
            print("Enter a non-empty value.")

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

    def _run_tool_flow(self) -> str:
        tool_name = self._prompt_tool_name()
        if tool_name is None:
            return "tools"

        target_scope, input_refs = self._prompt_tool_scope_and_inputs(
            tool_name)
        if target_scope is None:
            return "tools"

        self._selected_tool_name = tool_name
        dataset_path = self._get_selected_dataset_path()
        try:
            dataset_frame, valid_numeric_features = load_dataset(
                dataset_path,
                get_default_dataset_config(),
            )
            request = build_tool_call_request(
                call_id=self._next_tool_call_id(tool_name),
                tool_name=tool_name,
                target_scope=target_scope,
                input_refs=input_refs,
                preprocessing_profile_ref="default",
                execution_constraints={
                    "cache_policy": "reuse",
                    "validation_mode": "strict",
                    "save_raw_output": True,
                },
            )
            bundle = execute_tool_call(
                request,
                dataset_path=dataset_path,
                config=get_default_dataset_config(),
                dataset_frame=dataset_frame,
                valid_numeric_features=valid_numeric_features,
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"tool execution failed: {exc}")
            return "tools"

        self._last_tool_run = self._build_tool_run_context(bundle)
        self._selected_tool_run = self._last_tool_run

        while True:
            self._render_tool_run_review(self._last_tool_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "tools"
            if choice == "B":
                return "tools"
            self._handle_tool_review_choice(choice, self._last_tool_run)

    def _run_semantic_extraction_flow(self) -> str:
        dataset_path = self._get_selected_dataset_path()
        batch_id = self._next_semantic_extraction_batch_id(dataset_path)

        try:
            overview_summary_min = build_overview_summary_min(
                dataset_path, batch_id=batch_id)
            partition_context = build_partition_context(dataset_path.name)
            bundle = run_semantic_extraction(
                overview_summary_min,
                partition_context,
                model_name=self._resolve_phase3a_model_name(
                    "semantic_extraction"),
                caller_mode="cli",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"semantic extraction failed: {exc}")
            return "semantic_extraction"

        self._last_semantic_extraction_run = self._build_semantic_extraction_run_context(
            bundle)
        self._selected_semantic_extraction_run = self._last_semantic_extraction_run

        while True:
            self._render_semantic_extraction_run_review(
                self._last_semantic_extraction_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "semantic_extraction"
            if choice == "B":
                return "semantic_extraction"
            self._handle_semantic_extraction_review_choice(
                choice, self._last_semantic_extraction_run)

    def _run_investigation_analysis_flow(self) -> str:
        dataset_path = self._get_selected_dataset_path()
        substrate_source = self._prompt_investigation_substrate_source(
            dataset_path)
        if substrate_source is None:
            return "investigation_analysis"

        try:
            semantic_run_context = self._resolve_investigation_semantic_substrate_context(
                dataset_path,
                substrate_source,
            )
            analysis_context = build_analysis_context_min(
                build_partition_context(dataset_path.name),
                self._default_investigation_artifact_framing_refs(),
            )
            bundle = run_investigation_analysis(
                semantic_run_context.parsed_output,
                analysis_context,
                model_name=self._resolve_phase3a_model_name(
                    "investigation_analysis"),
                caller_mode="cli",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"investigation analysis failed: {exc}")
            return "investigation_analysis"

        self._last_investigation_analysis_run = self._build_investigation_analysis_run_context(
            bundle)
        self._selected_investigation_analysis_run = self._last_investigation_analysis_run

        while True:
            self._render_investigation_analysis_run_review(
                self._last_investigation_analysis_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "investigation_analysis"
            if choice == "B":
                return "investigation_analysis"
            self._handle_investigation_analysis_review_choice(
                choice,
                self._last_investigation_analysis_run,
            )

    def _run_hypothesis_ranking_flow(self) -> str:
        source_run = self._prompt_hypothesis_ranking_source()
        if source_run is None:
            return "hypothesis_ranking"

        try:
            batch_id = str(source_run.component_run.get(
                "batch_id") or source_run.parsed_output.get("batch_id") or "batch")
            round_id = self._next_hypothesis_ranking_round_id(batch_id)
            ranking_state = self._build_default_ranking_state_min(
                source_run, round_id)
            bundle = run_hypothesis_ranking(
                source_run.parsed_output,
                ranking_state,
                model_name=self._resolve_phase3a_model_name(
                    "hypothesis_ranking"),
                caller_mode="cli",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"hypothesis ranking failed: {exc}")
            return "hypothesis_ranking"

        self._last_hypothesis_ranking_run = self._build_hypothesis_ranking_run_context(
            bundle)
        self._selected_hypothesis_ranking_run = self._last_hypothesis_ranking_run

        while True:
            self._render_hypothesis_ranking_run_review(
                self._last_hypothesis_ranking_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "hypothesis_ranking"
            if choice == "B":
                return "hypothesis_ranking"
            self._handle_hypothesis_ranking_review_choice(
                choice, self._last_hypothesis_ranking_run)

    def _run_planner_flow(self) -> str:
        source_run = self._prompt_planner_source()
        if source_run is None:
            return "planner"

        try:
            ranking_decision_min = self._build_planner_ranking_decision_min(
                source_run)
            selected_hypothesis_context = resolve_selected_hypothesis_context(
                ranking_decision_min=ranking_decision_min,
                investigation_hypothesis_set=source_run.candidate_hypotheses,
            )
            planner_round_context = self._build_default_planner_round_context(
                selected_hypothesis_context,
                str(ranking_decision_min.get("round_id", "")),
            )
            bundle = run_planner(
                ranking_decision_min,
                selected_hypothesis_context,
                planner_round_context,
                model_name=self._resolve_phase3a_model_name("planner"),
                caller_mode="cli",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"planner failed: {exc}")
            return "planner"

        self._last_planner_run = self._build_planner_run_context(bundle)
        self._selected_planner_run = self._last_planner_run

        while True:
            self._render_planner_run_review(self._last_planner_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "planner"
            if choice == "B":
                return "planner"
            self._handle_planner_review_choice(choice, self._last_planner_run)

    def _run_router_flow(self) -> str:
        source_run = self._prompt_router_source()
        if source_run is None:
            return "router"

        selected_strategy = self._prompt_router_strategy(source_run)
        if selected_strategy is None:
            return "router"

        try:
            batch_id = str(
                source_run.component_run.get("batch_id")
                or source_run.parsed_output.get("batch_id")
                or "unknown_batch"
            )
            round_id = str(
                source_run.component_run.get("round_id")
                or source_run.parsed_output.get("round_id")
                or "unknown_round"
            )
            router_context_min = self._build_default_router_context_min(
                source_run,
                selected_strategy,
            )
            bundle = run_router(
                selected_strategy,
                router_context_min,
                batch_id=batch_id,
                round_id=round_id,
                model_name=self._resolve_phase3a_model_name("router"),
                caller_mode="cli",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"router failed: {exc}")
            return "router"

        self._last_router_run = self._build_router_run_context(bundle)
        self._selected_router_run = self._last_router_run

        while True:
            self._render_router_run_review(self._last_router_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "router"
            if choice == "B":
                return "router"
            self._handle_router_review_choice(choice, self._last_router_run)

    def _run_worker_flow(self) -> str:
        source_run = self._prompt_worker_source()
        if source_run is None:
            return "worker"

        selected_task = self._prompt_worker_task(source_run)
        if selected_task is None:
            return "worker"

        batch_id = str(
            source_run.component_run.get("batch_id")
            or source_run.parsed_output.get("batch_id")
            or "unknown_batch"
        )
        round_id = str(
            source_run.component_run.get("round_id")
            or source_run.parsed_output.get("round_id")
            or "unknown_round"
        )
        investigation_run = self._prompt_worker_investigation_source(batch_id)
        if investigation_run is None:
            return "worker"

        try:
            dataset_path = self._get_selected_dataset_path()
            worker_runtime_refs = self._build_worker_runtime_refs(
                source_run,
                selected_task,
                investigation_run,
                dataset_path,
            )
            bundle = run_worker(
                selected_task,
                worker_runtime_refs,
                batch_id=batch_id,
                round_id=round_id,
                model_name=self._resolve_phase3a_model_name("worker"),
                caller_mode="cli",
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"worker failed: {exc}")
            return "worker"

        self._last_worker_run = self._build_worker_run_context(bundle)
        self._selected_worker_run = self._last_worker_run

        while True:
            self._render_worker_run_review(self._last_worker_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "worker"
            if choice == "B":
                return "worker"
            self._handle_worker_review_choice(choice, self._last_worker_run)

    def _run_aggregation_flow(self) -> str:
        source_run = self._prompt_worker_source()
        if source_run is None:
            return "aggregation"

        expected_task_ids = [
            str(worker_task.get("task_id") or "").strip()
            for worker_task in (source_run.parsed_output.get("worker_tasks", []) or [])
            if isinstance(worker_task, dict) and str(worker_task.get("task_id") or "").strip()
        ]
        if not expected_task_ids:
            self._show_error(
                "Selected Router run does not contain any worker tasks for Aggregation.")
            return "aggregation"

        batch_id = str(
            source_run.component_run.get("batch_id")
            or source_run.parsed_output.get("batch_id")
            or "unknown_batch"
        )
        round_id = str(
            source_run.component_run.get("round_id")
            or source_run.parsed_output.get("round_id")
            or "unknown_round"
        )
        hypothesis_id = str(
            source_run.component_run.get("hypothesis_id")
            or source_run.parsed_output.get("hypothesis_id")
            or "unknown_hypothesis"
        )

        try:
            resolved = load_worker_result_set(
                batch_id=batch_id,
                round_id=round_id,
                hypothesis_id=hypothesis_id,
                expected_task_ids=expected_task_ids,
            )
            missing_task_ids = list(
                resolved["normalized_inputs"].get("missing_task_ids", []))
            if missing_task_ids:
                self._show_error(
                    "Aggregation cannot run yet. Missing committed Worker results for tasks: "
                    + ", ".join(missing_task_ids)
                    + "."
                )
                return "aggregation"
            bundle = run_aggregation(
                resolved["worker_result_set"],
                expected_task_ids=expected_task_ids,
                model_name=self._resolve_phase3a_model_name("aggregation"),
                caller_mode="cli",
                source_run_dirs=resolved["selected_run_dirs"],
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"aggregation failed: {exc}")
            return "aggregation"

        self._last_aggregation_run = self._build_aggregation_run_context(
            bundle)
        self._selected_aggregation_run = self._last_aggregation_run

        while True:
            self._render_aggregation_run_review(self._last_aggregation_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "aggregation"
            if choice == "B":
                return "aggregation"
            self._handle_aggregation_review_choice(
                choice, self._last_aggregation_run)

    def _run_state_manager_flow(self) -> str:
        source_run = self._prompt_state_manager_source()
        if source_run is None:
            return "state_manager"

        aggregation_handoff = dict(source_run.aggregation_handoff or {})
        if not aggregation_handoff or not source_run.component_run.get("handoff_committed", False):
            self._show_error(
                "Selected Aggregation run does not contain a committed aggregation handoff.")
            return "state_manager"

        try:
            prior_state, prior_state_source = self._resolve_state_manager_prior_state(
                source_run)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"state manager setup failed: {exc}")
            return "state_manager"

        if prior_state is None or prior_state_source is None:
            return "state_manager"

        try:
            bundle = run_state_manager(
                prior_state,
                aggregation_handoff,
                model_name=self._resolve_phase3a_model_name("state_manager"),
                caller_mode="cli",
                expected_prior_state_version=int(
                    prior_state_source.get("state_version")
                    or prior_state.get("state_version")
                    or 0
                ),
                prior_state_origin=str(
                    prior_state_source.get("origin") or "unknown"),
                prior_state_source=prior_state_source,
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"state manager failed: {exc}")
            return "state_manager"

        self._last_state_manager_run = self._build_state_manager_run_context(
            bundle)
        self._selected_state_manager_run = self._last_state_manager_run

        while True:
            self._render_state_manager_run_review(self._last_state_manager_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "state_manager"
            if choice == "B":
                return "state_manager"
            self._handle_state_manager_review_choice(
                choice, self._last_state_manager_run)

    def _run_critic_flow(self) -> str:
        source_run = self._prompt_critic_source()
        if source_run is None:
            return "critic"

        if not source_run.updated_batch_state or not source_run.component_run.get("state_committed", False):
            self._show_error(
                "Selected State Manager run does not contain a committed canonical state.")
            return "critic"

        is_final_round = self._prompt_critic_final_round_flag()
        if is_final_round is None:
            return "critic"

        try:
            bundle = run_critic(
                {
                    "artifact_paths": dict(source_run.artifact_paths),
                    "component_run": dict(source_run.component_run),
                    "prior_state": dict(source_run.prior_state),
                    "aggregation_handoff": dict(source_run.aggregation_handoff),
                    "state_manager_context": dict(source_run.state_manager_context),
                    "state_delta_record": dict(source_run.state_delta_record),
                    "updated_batch_state": dict(source_run.updated_batch_state),
                    "state_update_result": dict(source_run.state_update_result),
                    "validation_report": dict(source_run.validation_report),
                    "runtime_metrics": dict(source_run.runtime_metrics),
                },
                model_name=self._resolve_phase3a_model_name("critic"),
                caller_mode="cli",
                is_final_round=is_final_round,
                round_component_bundles=self._build_critic_round_component_bundles(
                    source_run),
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"critic failed: {exc}")
            return "critic"

        self._last_critic_run = self._build_critic_run_context(bundle)
        self._selected_critic_run = self._last_critic_run

        while True:
            self._render_critic_run_review(self._last_critic_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "critic"
            if choice == "B":
                return "critic"
            self._handle_critic_review_choice(choice, self._last_critic_run)

    def _run_final_batch_auditor_flow(self) -> str:
        source_run = self._prompt_final_batch_auditor_source()
        if source_run is None:
            return "final_batch_auditor"

        if not source_run.updated_batch_state or not source_run.component_run.get("state_committed", False):
            self._show_error(
                "Selected State Manager run does not contain a committed canonical state.")
            return "final_batch_auditor"

        is_final_batch = self._prompt_final_batch_terminal_flag()
        if is_final_batch is None:
            return "final_batch_auditor"

        try:
            bundle = run_final_batch_auditor(
                {
                    "artifact_paths": dict(source_run.artifact_paths),
                    "component_run": dict(source_run.component_run),
                    "prior_state": dict(source_run.prior_state),
                    "aggregation_handoff": dict(source_run.aggregation_handoff),
                    "state_manager_context": dict(source_run.state_manager_context),
                    "state_delta_record": dict(source_run.state_delta_record),
                    "updated_batch_state": dict(source_run.updated_batch_state),
                    "state_update_result": dict(source_run.state_update_result),
                    "validation_report": dict(source_run.validation_report),
                    "runtime_metrics": dict(source_run.runtime_metrics),
                },
                model_name=self._resolve_phase3a_model_name(
                    "final_batch_auditor"),
                caller_mode="cli",
                is_final_batch=is_final_batch,
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"final batch auditor failed: {exc}")
            return "final_batch_auditor"

        self._last_final_batch_auditor_run = self._build_final_batch_auditor_run_context(
            bundle)
        self._selected_final_batch_auditor_run = self._last_final_batch_auditor_run

        while True:
            self._render_final_batch_auditor_run_review(
                self._last_final_batch_auditor_run)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "final_batch_auditor"
            if choice == "B":
                return "final_batch_auditor"
            self._handle_final_batch_auditor_review_choice(
                choice,
                self._last_final_batch_auditor_run,
            )

    def _run_phase3a_runtime_flow(self, execution_mode: str = "full_batch") -> str:
        dataset_path = self._get_selected_dataset_path()
        component_model_names = self._build_phase3a_component_model_names()
        max_rounds = 3 if execution_mode == "full_batch" else 1
        enable_critic = execution_mode in {"full_round", "full_batch"}
        disable_neighborhood_consistency_analysis = self._prompt_yes_no(
            "Disable neighborhood consistency analysis?",
            default=False,
        )
        enable_neighborhood_consistency_analysis = not disable_neighborhood_consistency_analysis
        previous_neighborhood_consistency_analysis = os.environ.get(
            "PHASE3A_ENABLE_NEIGHBORHOOD_CONSISTENCY_ANALYSIS"
        )
        self.session_config.enable_neighborhood_consistency_analysis = enable_neighborhood_consistency_analysis
        os.environ[
            "PHASE3A_ENABLE_NEIGHBORHOOD_CONSISTENCY_ANALYSIS"
        ] = "1" if enable_neighborhood_consistency_analysis else "0"

        try:
            bundle = run_phase3a_batch(
                dataset_path,
                model_name=self.session_config.model_name,
                max_rounds=max_rounds,
                execution_mode=execution_mode,
                enable_critic=enable_critic,
                caller_mode="cli",
                llm_callables=build_phase3a_llm_callables(
                    self.session_config.model_name,
                    0.0,
                    component_model_names,
                ),
                component_model_names=component_model_names,
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(
                f"{PHASE3A_RUNTIME_MODE_LABELS.get(execution_mode, 'Phase 3A Runtime')} failed: {exc}"
            )
            return "phase3a_runtime"
        finally:
            self._restore_env_var(
                "PHASE3A_ENABLE_NEIGHBORHOOD_CONSISTENCY_ANALYSIS",
                previous_neighborhood_consistency_analysis,
            )

        run_context = self._build_phase3a_runtime_run_context(bundle)
        component_run_path = str(
            bundle.get("artifact_paths", {}).get(
                "component_run_path", "") or ""
        ).strip()
        run_dir = self._resolve_component_run_dir(component_run_path)
        if run_dir is not None:
            try:
                run_context = self._load_phase3a_runtime_run_context(run_dir)
            except Exception:
                pass

        self._last_phase3a_runtime_run = run_context
        self._selected_phase3a_runtime_run = self._last_phase3a_runtime_run

        while True:
            self._render_phase3a_runtime_run_review(
                run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "6", "7", "8", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "phase3a_runtime"
            if choice == "B":
                return "phase3a_runtime"
            self._handle_phase3a_runtime_review_choice(
                choice, run_context)
            if not self._running:
                return "phase3a_runtime"

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

    def _resolve_phase3a_model_name(self, component_name: str) -> str:
        normalized_name = str(component_name or "").strip()
        if normalized_name == "critic":
            return str(self.session_config.critic_model_name or self.session_config.synthesis_model_name or self.session_config.model_name)
        if normalized_name in PHASE3A_PLANNING_COMPONENTS:
            return str(self.session_config.planning_model_name or self.session_config.model_name)
        if normalized_name in PHASE3A_WORKER_COMPONENTS:
            return str(self.session_config.worker_model_name or self.session_config.model_name)
        if normalized_name in PHASE3A_SYNTHESIS_COMPONENTS:
            return str(self.session_config.synthesis_model_name or self.session_config.model_name)
        return self.session_config.model_name

    def _render_session_model_name(self, role_name: str) -> str:
        if role_name == "default":
            return self.session_config.model_name
        if role_name == "planning":
            configured_value = self.session_config.planning_model_name
        elif role_name == "worker":
            configured_value = self.session_config.worker_model_name
        elif role_name == "critic":
            configured_value = self.session_config.critic_model_name
        else:
            configured_value = self.session_config.synthesis_model_name
        if configured_value:
            return configured_value
        return f"{self.session_config.model_name} (inherits default)"

    def _build_phase3a_component_model_names(self) -> dict[str, str]:
        return {
            "semantic_extraction": self._resolve_phase3a_model_name("semantic_extraction"),
            "investigation_analysis": self._resolve_phase3a_model_name("investigation_analysis"),
            "hypothesis_ranking": self._resolve_phase3a_model_name("hypothesis_ranking"),
            "planner": self._resolve_phase3a_model_name("planner"),
            "router": self._resolve_phase3a_model_name("router"),
            "worker": self._resolve_phase3a_model_name("worker"),
            "aggregation": self._resolve_phase3a_model_name("aggregation"),
            "state_manager": self._resolve_phase3a_model_name("state_manager"),
            "critic": self._resolve_phase3a_model_name("critic"),
            "final_batch_auditor": self._resolve_phase3a_model_name("final_batch_auditor"),
        }

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

    def _prompt_tool_name(self) -> str | None:
        records = get_tool_capability_records()
        ordered_records = [records[name] for name in sorted(records.keys())]
        self._render(render_tool_inventory(ordered_records))
        print()
        print("Enter the tool name to run, or B to go back.")
        while True:
            raw_value = input("> ").strip()
            if not raw_value:
                print("Enter a tool name or B.")
                continue
            if raw_value.upper() == "B":
                return None
            if raw_value not in records:
                print("Unknown tool. Enter one of the inventory tool names exactly.")
                continue
            return raw_value

    def _prompt_tool_scope_and_inputs(self, tool_name: str) -> tuple[str | None, dict[str, Any]]:
        record = get_tool_capability_record(tool_name) or {}
        supported_scopes = list(record.get("supported_scopes") or [])
        if not supported_scopes:
            self._show_error(
                f"tool '{tool_name}' has no supported scopes configured")
            return None, {}

        if len(supported_scopes) == 1:
            target_scope = supported_scopes[0]
        else:
            target_scope = self._read_non_empty_input(
                "Enter target scope ({}) or B to go back.".format(
                    ", ".join(supported_scopes))
            )
            if target_scope.upper() == "B":
                return None, {}
            if target_scope not in supported_scopes:
                self._show_error(
                    f"target scope must be one of: {', '.join(supported_scopes)}")
                return None, {}

        input_refs: dict[str, Any] = {}
        if tool_name != "duplication_analysis":
            feature_name = self._read_non_empty_input(
                "Enter feature name, or B to go back.")
            if feature_name.upper() == "B":
                return None, {}
            input_refs["feature_name"] = feature_name

        if tool_name == "feature_relation" and target_scope == "feature_pair":
            related_feature_name = self._read_non_empty_input(
                "Enter related feature name, or B to go back.")
            if related_feature_name.upper() == "B":
                return None, {}
            input_refs["related_feature_name"] = related_feature_name

        return target_scope, input_refs

    def _next_tool_call_id(self, tool_name: str) -> str:
        self._session_run_counter += 1
        return f"tool_call_{self._session_run_counter:03d}_{tool_name}"

    def _next_semantic_extraction_batch_id(self, dataset_path: Path) -> str:
        self._session_run_counter += 1
        dataset_stem = dataset_path.stem.lower().replace(" ", "_")
        return f"semantic_batch_{self._session_run_counter:03d}_{dataset_stem}"

    def _next_hypothesis_ranking_round_id(self, batch_id: str) -> str:
        self._session_run_counter += 1
        batch_tag = str(batch_id or "batch").strip().lower().replace(" ", "_")
        return f"round_{self._session_run_counter:03d}_{batch_tag}"

    def _default_investigation_artifact_framing_refs(self) -> list[dict[str, str]]:
        return [
            {
                "framing_id": "dependency_backed_regularity",
                "label": "dependency-backed regularity",
                "description": "Broad paired or dependency-backed structure may reflect a stable regularity rather than a single narrow handle.",
            },
            {
                "framing_id": "localized_representation_sensitive_handle",
                "label": "localized representation-sensitive handle",
                "description": "A narrow or representation-sensitive signal may remain locally meaningful even when it does not explain the full substrate.",
            },
            {
                "framing_id": "overlap_preserving_competing_framings",
                "label": "overlap-preserving competing framing",
                "description": "Contradictions and tensions may justify multiple partially compatible hypotheses that should remain alive together.",
            },
        ]

    def _prompt_hypothesis_ranking_source(self) -> InvestigationAnalysisRunContext | None:
        session_run = self._last_investigation_analysis_run
        saved_run = self._get_latest_investigation_analysis_run_context()

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                "No Investigation Analysis hypothesis set is available yet. Run Investigation Analysis first.")
            return None

        self._clear_screen()
        print("Choose Hypothesis Ranking source hypothesis set:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_investigation_analysis"
            print(
                f"[1] Use latest session Investigation Analysis run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(
                saved_path).parent.name or "latest_saved_investigation_analysis"
            print(
                f"[2] Use latest saved Investigation Analysis run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _prompt_planner_source(self) -> HypothesisRankingRunContext | None:
        session_run = self._last_hypothesis_ranking_run
        saved_run = self._get_latest_hypothesis_ranking_run_context()

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                "No Hypothesis Ranking selection set is available yet. Run Hypothesis Ranking first.")
            return None

        self._clear_screen()
        print("Choose Planner source ranking decision:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_hypothesis_ranking"
            print(
                f"[1] Use latest session Hypothesis Ranking run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(
                saved_path).parent.name or "latest_saved_hypothesis_ranking"
            print(
                f"[2] Use latest saved Hypothesis Ranking run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _prompt_router_source(self) -> PlannerRunContext | None:
        session_run = self._last_planner_run
        saved_run = self._get_latest_planner_run_context()

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                "No Planner strategy bundle is available yet. Run Planner first.")
            return None

        self._clear_screen()
        print("Choose Router source planner strategy bundle:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_planner"
            print(f"[1] Use latest session Planner run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(saved_path).parent.name or "latest_saved_planner"
            print(f"[2] Use latest saved Planner run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _prompt_worker_source(self) -> RouterRunContext | None:
        session_run = self._last_router_run
        saved_run = self._get_latest_router_run_context()

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                "No Router task bundle is available yet. Run Router first.")
            return None

        self._clear_screen()
        print("Choose Worker source routed task bundle:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_router"
            print(f"[1] Use latest session Router run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(saved_path).parent.name or "latest_saved_router"
            print(f"[2] Use latest saved Router run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _prompt_state_manager_source(self) -> AggregationRunContext | None:
        session_run = self._last_aggregation_run
        saved_run = self._get_latest_aggregation_run_context()

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                "No Aggregation handoff is available yet. Run Aggregation first.")
            return None

        self._clear_screen()
        print("Choose State Manager source aggregation handoff:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_aggregation"
            print(f"[1] Use latest session Aggregation run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(
                saved_path).parent.name or "latest_saved_aggregation"
            print(f"[2] Use latest saved Aggregation run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _prompt_critic_source(self) -> StateManagerRunContext | None:
        session_run = self._last_state_manager_run
        saved_run = self._get_latest_state_manager_run_context()

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                "No State Manager run is available yet. Run State Manager first.")
            return None

        self._clear_screen()
        print("Choose Critic source State Manager run:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_state_manager"
            print(f"[1] Use latest session State Manager run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(
                saved_path).parent.name or "latest_saved_state_manager"
            print(f"[2] Use latest saved State Manager run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _prompt_final_batch_auditor_source(self) -> StateManagerRunContext | None:
        session_run = self._last_state_manager_run
        saved_run = self._get_latest_state_manager_run_context()

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                "No State Manager run is available yet. Run State Manager first.")
            return None

        self._clear_screen()
        print("Choose Final Batch Auditor source State Manager run:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_state_manager"
            print(f"[1] Use latest session State Manager run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(
                saved_path).parent.name or "latest_saved_state_manager"
            print(f"[2] Use latest saved State Manager run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _prompt_critic_final_round_flag(self) -> bool | None:
        self._clear_screen()
        print("Should Critic treat the selected round as final?")
        print()
        print("[1] No, run Critic normally")
        print("[2] Yes, record a final-round skip bundle")
        print("[B] Back")
        print("[Q] Quit")

        while True:
            choice = self._read_menu_choice({"1", "2", "B", "Q"})
            if choice == "Q":
                self._quit()
                return None
            if choice == "B":
                return None
            if choice == "1":
                return False
            if choice == "2":
                return True

    def _prompt_final_batch_terminal_flag(self) -> bool | None:
        self._clear_screen()
        print("Treat the selected State Manager run as the terminal batch state?")
        print()
        print("[1] Yes, run the authoritative Final Batch Auditor")
        print("[2] No, cancel")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice({"1", "2", "B"})
            if choice == "B":
                return None
            if choice == "1":
                return True
            if choice == "2":
                return None

    def _is_component_bundle_ready(
        self,
        component_name: str,
        bundle: dict[str, Any],
    ) -> bool:
        component_run = dict(bundle.get("component_run", {}) or {})
        if not bool(component_run.get("validation_ok", False)):
            return False
        if component_name == "worker":
            return bool(component_run.get("result_committed", False))
        if component_name == "aggregation":
            return bool(component_run.get("handoff_committed", False))
        if component_name == "state_manager":
            return bool(component_run.get("state_committed", False))
        return True

    def _bundle_matches_critic_anchor(
        self,
        bundle: dict[str, Any],
        *,
        batch_id: str,
        round_id: str | None = None,
        hypothesis_id: str | None = None,
    ) -> bool:
        component_run = dict(bundle.get("component_run", {}) or {})
        normalized_batch_id = str(component_run.get("batch_id") or "").strip()
        if normalized_batch_id != batch_id:
            return False

        if round_id is not None:
            normalized_round_id = str(
                component_run.get("round_id") or "").strip()
            if normalized_round_id != round_id:
                return False

        if hypothesis_id is not None:
            normalized_hypothesis_id = str(
                component_run.get("hypothesis_id") or "").strip()
            if normalized_hypothesis_id and normalized_hypothesis_id != hypothesis_id:
                return False

        return True

    def _find_latest_matching_component_bundle(
        self,
        *,
        component_name: str,
        list_dirs_fn: Callable[..., list[Path]],
        load_bundle_fn: Callable[[Path], dict[str, Any]],
        batch_id: str,
        round_id: str | None = None,
        hypothesis_id: str | None = None,
    ) -> dict[str, Any] | None:
        for run_dir in list_dirs_fn():
            try:
                bundle = load_bundle_fn(run_dir)
            except Exception:  # noqa: BLE001
                continue
            if not self._is_component_bundle_ready(component_name, bundle):
                continue
            if self._bundle_matches_critic_anchor(
                bundle,
                batch_id=batch_id,
                round_id=round_id,
                hypothesis_id=hypothesis_id,
            ):
                return bundle
        return None

    def _find_matching_worker_bundles(
        self,
        *,
        batch_id: str,
        round_id: str,
        hypothesis_id: str,
        task_ids: set[str],
    ) -> list[dict[str, Any]]:
        bundles: list[dict[str, Any]] = []
        for run_dir in list_worker_run_dirs():
            try:
                bundle = load_worker_bundle(run_dir)
            except Exception:  # noqa: BLE001
                continue
            if not self._is_component_bundle_ready("worker", bundle):
                continue
            if not self._bundle_matches_critic_anchor(
                bundle,
                batch_id=batch_id,
                round_id=round_id,
                hypothesis_id=hypothesis_id,
            ):
                continue
            task_id = str(bundle.get("component_run", {}
                                     ).get("task_id") or "").strip()
            if task_ids and task_id not in task_ids:
                continue
            bundles.append(bundle)
            if task_ids and len(bundles) >= len(task_ids):
                break
        bundles.sort(
            key=lambda bundle: str(bundle.get(
                "component_run", {}).get("task_id") or "")
        )
        return bundles

    def _build_critic_round_component_bundles(
        self,
        source_run: StateManagerRunContext,
    ) -> dict[str, Any]:
        component_run = dict(source_run.component_run or {})
        batch_id = str(component_run.get("batch_id") or "").strip()
        round_id = str(component_run.get("round_id") or "").strip()
        hypothesis_id = str(component_run.get("hypothesis_id") or "").strip()
        bundles: dict[str, Any] = {}

        if not batch_id:
            return bundles

        semantic_extraction_bundle = self._find_latest_matching_component_bundle(
            component_name="semantic_extraction",
            list_dirs_fn=list_semantic_extraction_run_dirs,
            load_bundle_fn=load_semantic_extraction_bundle,
            batch_id=batch_id,
        )
        if semantic_extraction_bundle is not None:
            bundles["semantic_extraction"] = semantic_extraction_bundle

        investigation_analysis_bundle = self._find_latest_matching_component_bundle(
            component_name="investigation_analysis",
            list_dirs_fn=list_investigation_analysis_run_dirs,
            load_bundle_fn=load_investigation_analysis_bundle,
            batch_id=batch_id,
        )
        if investigation_analysis_bundle is not None:
            bundles["investigation_analysis"] = investigation_analysis_bundle

        if round_id:
            hypothesis_ranking_bundle = self._find_latest_matching_component_bundle(
                component_name="hypothesis_ranking",
                list_dirs_fn=list_hypothesis_ranking_run_dirs,
                load_bundle_fn=load_hypothesis_ranking_bundle,
                batch_id=batch_id,
                round_id=round_id,
            )
            if hypothesis_ranking_bundle is not None:
                bundles["hypothesis_ranking"] = hypothesis_ranking_bundle

            planner_bundle = self._find_latest_matching_component_bundle(
                component_name="planner",
                list_dirs_fn=list_planner_run_dirs,
                load_bundle_fn=load_planner_bundle,
                batch_id=batch_id,
                round_id=round_id,
            )
            if planner_bundle is not None:
                bundles["planner"] = planner_bundle

            router_bundle = self._find_latest_matching_component_bundle(
                component_name="router",
                list_dirs_fn=list_router_run_dirs,
                load_bundle_fn=load_router_bundle,
                batch_id=batch_id,
                round_id=round_id,
                hypothesis_id=hypothesis_id or None,
            )
            if router_bundle is not None:
                bundles["router"] = router_bundle

            aggregation_bundle = self._find_latest_matching_component_bundle(
                component_name="aggregation",
                list_dirs_fn=list_aggregation_run_dirs,
                load_bundle_fn=load_aggregation_bundle,
                batch_id=batch_id,
                round_id=round_id,
                hypothesis_id=hypothesis_id or None,
            )
            if aggregation_bundle is not None:
                bundles["aggregation"] = aggregation_bundle

            worker_task_ids = {
                str(item.get("task_id") or "").strip()
                for item in bundles.get("aggregation", {}).get("worker_result_set", {}).get("worker_results", [])
                if isinstance(item, dict) and str(item.get("task_id") or "").strip()
            }
            worker_bundles = self._find_matching_worker_bundles(
                batch_id=batch_id,
                round_id=round_id,
                hypothesis_id=hypothesis_id,
                task_ids=worker_task_ids,
            )
            if worker_bundles:
                bundles["worker"] = worker_bundles

        return bundles

    def _resolve_state_manager_prior_state(
        self,
        aggregation_run: AggregationRunContext,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        batch_id = str(
            aggregation_run.component_run.get("batch_id")
            or aggregation_run.aggregation_handoff.get("batch_id")
            or ""
        ).strip()
        if not batch_id:
            raise RuntimeError("Aggregation run is missing a batch_id.")

        candidate_sources: list[dict[str, Any]] = []

        session_run = self._last_state_manager_run
        if session_run is not None:
            if str(session_run.component_run.get("batch_id") or "") != batch_id:
                session_run = None
            elif not session_run.updated_batch_state:
                session_run = None

        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
            session_name = Path(
                session_path).parent.name or "latest_session_state_manager"
            candidate_sources.append(
                {
                    "choice": "1",
                    "label": f"latest session State Manager run ({session_name})",
                    "origin": "session_state_manager_run",
                    "source_run_path": session_path,
                    "state_version": int(session_run.updated_batch_state.get("state_version") or 0),
                    "state": dict(session_run.updated_batch_state),
                }
            )

        saved_run = self._get_latest_matching_state_manager_run_context(
            batch_id)
        session_path = candidate_sources[0]["source_run_path"] if candidate_sources else ""
        if saved_run is not None and saved_run.updated_batch_state:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")
            if saved_path != session_path:
                saved_name = Path(
                    saved_path).parent.name or "latest_saved_state_manager"
                candidate_sources.append(
                    {
                        "choice": str(len(candidate_sources) + 1),
                        "label": f"latest saved State Manager run ({saved_name})",
                        "origin": "saved_state_manager_run",
                        "source_run_path": saved_path,
                        "state_version": int(saved_run.updated_batch_state.get("state_version") or 0),
                        "state": dict(saved_run.updated_batch_state),
                    }
                )

        investigation_run = self._get_latest_matching_investigation_analysis_run_context(
            batch_id)
        if investigation_run is None and not candidate_sources:
            self._show_error(
                f"No canonical state seed is available for batch_id={batch_id}. Run Investigation Analysis first."
            )
            return None, None

        if investigation_run is not None:
            canonical_state = init_canonical_batch_state(
                batch_id=batch_id,
                structural_substrate=dict(
                    investigation_run.semantic_substrate_input),
                hypothesis_set=dict(investigation_run.parsed_output),
            )
            investigation_path = investigation_run.artifact_paths.get(
                "component_run_path", "")
            investigation_name = (
                Path(investigation_path).parent.name or "latest_investigation_analysis"
            )
            candidate_sources.append(
                {
                    "choice": str(len(candidate_sources) + 1),
                    "label": f"initialize from Investigation Analysis ({investigation_name})",
                    "origin": "investigation_analysis_seed",
                    "source_run_path": investigation_path,
                    "state_version": canonical_state.state_version,
                    "state": canonical_state.to_dict(),
                }
            )

        if not candidate_sources:
            return None, None

        selected_source = candidate_sources[0]
        if len(candidate_sources) > 1:
            self._clear_screen()
            print("Choose State Manager prior-state snapshot:")
            print()
            valid_choices: set[str] = {"B"}
            for candidate_source in candidate_sources:
                print(
                    f"[{candidate_source['choice']}] Use {candidate_source['label']} "
                    f"(state_version={candidate_source['state_version']})"
                )
                valid_choices.add(str(candidate_source["choice"]))
            print("[B] Back")

            while True:
                choice = self._read_menu_choice(valid_choices)
                if choice == "B":
                    return None, None
                for candidate_source in candidate_sources:
                    if choice == candidate_source["choice"]:
                        selected_source = candidate_source
                        break
                else:
                    continue
                break

        if selected_source.get("origin") == "investigation_analysis_seed":
            self._show_info(
                "State Manager is initializing canonical state from the selected Investigation Analysis run because no prior committed State Manager revision was chosen."
            )

        selected_state = dict(selected_source.get("state", {}))
        selected_metadata = {
            "origin": str(selected_source.get("origin") or "unknown"),
            "source_run_path": str(selected_source.get("source_run_path") or ""),
            "state_version": int(selected_source.get("state_version") or 0),
            "batch_id": batch_id,
        }
        return selected_state, selected_metadata

    def _prompt_worker_task(self, router_run: RouterRunContext) -> dict[str, Any] | None:
        worker_tasks = [
            worker_task
            for worker_task in (router_run.parsed_output.get("worker_tasks", []) or [])
            if isinstance(worker_task, dict) and str(worker_task.get("task_id") or "").strip()
        ]
        if not worker_tasks:
            self._show_error(
                "Selected Router run does not contain any worker tasks.")
            return None

        self._clear_screen()
        print("Choose Worker target task:")
        print()
        for index, worker_task in enumerate(worker_tasks, start=1):
            task_id = str(worker_task.get("task_id", "unknown_task"))
            scope = str(worker_task.get("task_scope", ""))
            display_scope = scope[:72] + "..." if len(scope) > 75 else scope
            print(f"[{index}] {task_id}  |  {display_scope}")
        print("[B] Back")

        valid_choices = {str(index)
                         for index in range(1, len(worker_tasks) + 1)} | {"B"}
        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            return worker_tasks[int(choice) - 1]

    def _prompt_worker_investigation_source(
        self,
        batch_id: str,
    ) -> InvestigationAnalysisRunContext | None:
        session_run = self._last_investigation_analysis_run
        if session_run is not None and str(session_run.component_run.get("batch_id") or "") != batch_id:
            session_run = None
        saved_run = self._get_latest_matching_investigation_analysis_run_context(
            batch_id)

        session_path = ""
        saved_path = ""
        if session_run is not None:
            session_path = session_run.artifact_paths.get(
                "component_run_path", "")
        if saved_run is not None:
            saved_path = saved_run.artifact_paths.get("component_run_path", "")

        if session_run is None and saved_run is None:
            self._show_error(
                f"No Investigation Analysis substrate with batch_id={batch_id} is available yet. Run Investigation Analysis first."
            )
            return None

        self._clear_screen()
        print("Choose Worker local-context source:")
        print()

        valid_choices: set[str] = {"B"}
        if session_run is not None:
            session_name = Path(
                session_path).parent.name or "latest_session_investigation_analysis"
            print(
                f"[1] Use latest session Investigation Analysis run ({session_name})")
            valid_choices.add("1")
        if saved_run is not None and saved_path != session_path:
            saved_name = Path(
                saved_path).parent.name or "latest_saved_investigation_analysis"
            print(
                f"[2] Use latest saved Investigation Analysis run ({saved_name})")
            valid_choices.add("2")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "1" and session_run is not None:
                return session_run
            if choice == "2" and saved_run is not None:
                return saved_run

    def _build_worker_runtime_refs(
        self,
        router_run: RouterRunContext,
        worker_task: dict[str, Any],
        investigation_run: InvestigationAnalysisRunContext,
        dataset_path: Path,
    ) -> dict[str, Any]:
        execution_budget = {}
        if isinstance(router_run.router_context_min.get("execution_budget"), dict):
            execution_budget = dict(
                router_run.router_context_min.get("execution_budget") or {})
        elif isinstance(router_run.reduced_context.get("execution_budget"), dict):
            execution_budget = dict(
                router_run.reduced_context.get("execution_budget") or {})

        return {
            "tool_handles": {},
            "dataset_handles": {
                "dataset_path": str(dataset_path),
                "semantic_substrate": dict(investigation_run.semantic_substrate_input),
            },
            "budget_rules": {
                "max_steps": int(execution_budget.get("max_worker_steps") or DEFAULT_MAX_WORKER_STEPS),
                "max_retries": int(execution_budget.get("max_retries") or DEFAULT_MAX_RETRIES),
            },
        }

    def _prompt_router_strategy(
        self,
        planner_run: PlannerRunContext,
    ) -> dict[str, Any] | None:
        strategies = [
            strategy
            for strategy in (planner_run.parsed_output.get("planner_strategies", []) or [])
            if isinstance(strategy, dict) and str(strategy.get("strategy_id", "")).strip()
        ]
        if not strategies:
            self._show_error(
                "Selected Planner run does not contain any planner strategies.")
            return None

        self._clear_screen()
        print("Choose Router target planner strategy:")
        print()
        for index, strategy in enumerate(strategies, start=1):
            strategy_id = str(strategy.get("strategy_id", "unknown_strategy"))
            hypothesis_id = str(strategy.get(
                "hypothesis_id", "unknown_hypothesis"))
            print(f"[{index}] {strategy_id}  |  {hypothesis_id}")
        print("[B] Back")

        valid_choices = {str(index)
                         for index in range(1, len(strategies) + 1)} | {"B"}
        while True:
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            return strategies[int(choice) - 1]

    def _build_default_ranking_state_min(
        self,
        investigation_run: InvestigationAnalysisRunContext,
        round_id: str,
    ) -> dict[str, Any]:
        hypothesis_state_refs = [
            {
                "hypothesis_id": str(hypothesis.get("hypothesis_id", "")),
                "state_notes": [],
            }
            for hypothesis in (investigation_run.parsed_output.get("hypotheses", []) or [])
            if isinstance(hypothesis, dict) and str(hypothesis.get("hypothesis_id", "")).strip()
        ]

        return build_ranking_state_min(
            round_id=round_id,
            selection_budget=3,
            hypothesis_state_refs=hypothesis_state_refs,
            round_constraints=[
                "selection_budget=3",
                "allocation_only",
                "preserve_deferred_hypotheses",
                "no_committed_round_state_available_yet",
            ],
        )

    def _build_planner_ranking_decision_min(
        self,
        ranking_run: HypothesisRankingRunContext,
    ) -> dict[str, Any]:
        parsed_output = ranking_run.parsed_output
        return {
            "batch_id": str(parsed_output.get("batch_id") or ranking_run.component_run.get("batch_id") or "unknown_batch"),
            "round_id": str(parsed_output.get("round_id") or ranking_run.component_run.get("round_id") or "unknown_round"),
            "selected_hypothesis_ids": list(parsed_output.get("selected_hypothesis_ids") or []),
        }

    def _build_default_planner_round_context(
        self,
        selected_hypothesis_context: dict[str, Any],
        round_id: str,
    ) -> dict[str, Any]:
        tool_capability_records = get_tool_capability_records()
        return build_planner_round_context(
            round_id=round_id,
            related_substrate_refs=collect_related_substrate_refs(
                selected_hypothesis_context),
            tool_capability_refs=sorted(tool_capability_records.keys()),
            round_constraints=[
                "strategic_only",
                "no_exact_tool_calls",
                "preserve_selected_scope",
                "router_ready_handoff",
            ],
        )

    def _build_default_router_context_min(
        self,
        planner_run: PlannerRunContext,
        planner_strategy: dict[str, Any],
    ) -> dict[str, Any]:
        hypothesis_id = str(planner_strategy.get(
            "hypothesis_id") or "").strip()
        selected_hypotheses = planner_run.selected_hypothesis_context.get(
            "selected_hypotheses", [])
        selected_hypothesis = next(
            (
                item
                for item in selected_hypotheses
                if isinstance(item, dict) and str(item.get("hypothesis_id") or "").strip() == hypothesis_id
            ),
            {},
        )
        related_substrate_refs = list(
            selected_hypothesis.get("evidence_refs") or [])
        if not related_substrate_refs:
            related_substrate_refs = list(
                planner_run.planner_round_context.get("related_substrate_refs") or [])

        round_constraints = [
            str(item).strip()
            for item in (planner_run.planner_round_context.get("round_constraints") or [])
            if str(item).strip()
        ]
        guardrails = list(dict.fromkeys([
            "bounded_local_scope",
            "no_exact_tool_calls",
            "no_hidden_replanning",
            *round_constraints,
        ]))
        max_tasks = min(
            4, max(1, len(planner_strategy.get("key_checks") or [])))

        return build_router_context_min(
            related_substrate_refs=related_substrate_refs,
            tool_capability_refs=list(
                planner_run.planner_round_context.get("tool_capability_refs") or []),
            execution_budget={
                "max_worker_steps": 8,
                "max_tasks": max_tasks,
                "max_retries": 1,
            },
            guardrails=guardrails,
        )

    def _prompt_investigation_substrate_source(self, dataset_path: Path) -> str | None:
        reusable_run = self._get_reusable_semantic_extraction_run_context(
            dataset_path)
        self._clear_screen()
        print("Choose Investigation Analysis substrate source:")
        print()
        if reusable_run is not None:
            reusable_name = Path(
                reusable_run.artifact_paths.get("component_run_path", "")
            ).parent.name or "latest_semantic_extraction_run"
            print(
                f"[1] Reuse latest Semantic Extraction substrate ({reusable_name})")
        else:
            print("[1] Reuse latest Semantic Extraction substrate  <unavailable>")
        print(
            f"[2] Build fresh Semantic Extraction substrate for {dataset_path.name}")
        print("[B] Back")

        while True:
            choice = self._read_menu_choice({"1", "2", "B"})
            if choice == "B":
                return None
            if choice == "1" and reusable_run is None:
                print("No reusable Semantic Extraction run matches the current dataset.")
                continue
            return "reuse" if choice == "1" else "fresh"

    def _get_reusable_semantic_extraction_run_context(
        self,
        dataset_path: Path,
    ) -> SemanticExtractionRunContext | None:
        if self._last_semantic_extraction_run is not None:
            if self._last_semantic_extraction_run.overview_summary_min.get("dataset_name") == dataset_path.name:
                return self._last_semantic_extraction_run

        latest_persisted = self._get_latest_semantic_extraction_run_context()
        if latest_persisted is None:
            return None
        if latest_persisted.overview_summary_min.get("dataset_name") != dataset_path.name:
            return None
        return latest_persisted

    def _resolve_investigation_semantic_substrate_context(
        self,
        dataset_path: Path,
        substrate_source: str,
    ) -> SemanticExtractionRunContext:
        if substrate_source == "reuse":
            reusable_run = self._get_reusable_semantic_extraction_run_context(
                dataset_path)
            if reusable_run is None:
                raise RuntimeError(
                    "no reusable Semantic Extraction run is available for the selected dataset")
            self._last_semantic_extraction_run = reusable_run
            return reusable_run

        batch_id = self._next_semantic_extraction_batch_id(dataset_path)
        overview_summary_min = build_overview_summary_min(
            dataset_path, batch_id=batch_id)
        partition_context = build_partition_context(dataset_path.name)
        bundle = run_semantic_extraction(
            overview_summary_min,
            partition_context,
            model_name=self.session_config.model_name,
            caller_mode="cli",
        )
        run_context = self._build_semantic_extraction_run_context(bundle)
        self._last_semantic_extraction_run = run_context
        return run_context

    def _build_tool_run_context(self, bundle: dict[str, Any]) -> ToolRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and "artifact_paths" in bundle and bundle["artifact_paths"].get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return ToolRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            tool_call_request=dict(bundle.get("tool_call_request", {})),
            tool_capability_record=dict(
                bundle.get("tool_capability_record", {})),
            normalized_inputs=dict(bundle.get("normalized_inputs", {})),
            raw_tool_output=dict(bundle.get("raw_tool_output", {})),
            parsed_output=dict(bundle.get(
                "tool_result", bundle.get("parsed_output", {}))),
            validation_report=dict(bundle.get("validation_report", {})),
            tool_metrics=dict(bundle.get("tool_metrics", {})),
            cache_record=dict(bundle.get("cache_record", {})
                              ) if bundle.get("cache_record") else None,
        )

    def _build_semantic_extraction_run_context(self, bundle: dict[str, Any]) -> SemanticExtractionRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return SemanticExtractionRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            overview_summary_min=dict(bundle.get("overview_summary_min", {})),
            partition_context=dict(bundle.get("partition_context", {})),
            projected_evidence=dict(bundle.get("projected_evidence", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            parsed_output=dict(bundle.get(
                "semantic_substrate", bundle.get("parsed_output", {}))),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_investigation_analysis_run_context(
        self,
        bundle: dict[str, Any],
    ) -> InvestigationAnalysisRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return InvestigationAnalysisRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            semantic_substrate_input=dict(
                bundle.get("semantic_substrate_input", {})),
            analysis_context_min=dict(bundle.get("analysis_context_min", {})),
            analysis_iteration_context_min=dict(
                bundle.get("analysis_iteration_context_min", {})),
            projected_substrate=dict(bundle.get("projected_substrate", {})),
            projected_analysis_context=dict(
                bundle.get("projected_analysis_context", {})),
            projected_iteration_context=dict(
                bundle.get("projected_iteration_context", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            parsed_output=dict(bundle.get(
                "hypothesis_set", bundle.get("parsed_output", {}))),
            hypothesis_index=dict(bundle.get("hypothesis_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_hypothesis_ranking_run_context(
        self,
        bundle: dict[str, Any],
    ) -> HypothesisRankingRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return HypothesisRankingRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            candidate_hypotheses=dict(bundle.get(
                "investigation_hypothesis_set", {})),
            ranking_state_snapshot=dict(bundle.get("ranking_state_min", {})),
            projected_candidate_context=dict(
                bundle.get("projected_candidate_context", {})),
            projected_ranking_state=dict(
                bundle.get("projected_ranking_state", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            parsed_output=dict(bundle.get(
                "ranking_decision", bundle.get("parsed_output", {}))),
            selection_index=dict(bundle.get("selection_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_planner_run_context(
        self,
        bundle: dict[str, Any],
    ) -> PlannerRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return PlannerRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            ranking_decision_min=dict(bundle.get("ranking_decision_min", {})),
            selected_hypothesis_context=dict(
                bundle.get("selected_hypothesis_context", {})),
            planner_round_context=dict(
                bundle.get("planner_round_context", {})),
            projected_selected_context=dict(
                bundle.get("projected_selected_context", {})),
            projected_planner_round_context=dict(
                bundle.get("projected_planner_round_context", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            parsed_output=dict(bundle.get(
                "planner_round_output", bundle.get("parsed_output", {}))),
            strategy_index=dict(bundle.get("strategy_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_router_run_context(
        self,
        bundle: dict[str, Any],
    ) -> RouterRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return RouterRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            planner_strategy=dict(bundle.get("planner_strategy", {})),
            router_context_min=dict(bundle.get("router_context_min", {})),
            reduced_context=dict(bundle.get("reduced_context", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            parsed_output=dict(bundle.get(
                "router_output", bundle.get("parsed_output", {}))),
            task_bundle_index=dict(bundle.get("task_bundle_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _render_tool_run_review(self, run_context: ToolRunContext) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "tool_run"
        summary_pairs = [
            ("tool", str(run_context.component_run.get("tool_name", "unknown"))),
            ("target_scope", str(run_context.component_run.get("target_scope", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("duration_ms", str(run_context.tool_metrics.get("duration_ms", 0.0))),
        ]
        self._render(
            render_tool_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Normalized Inputs"),
                    ("2", "Inspect Raw Output"),
                    ("3", "Inspect Parsed Output"),
                    ("4", "Inspect Validation"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_semantic_extraction_run_review(self, run_context: SemanticExtractionRunContext) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "semantic_extraction_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("dataset", str(run_context.overview_summary_min.get(
                "dataset_name", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("regions", str(len(run_context.parsed_output.get("compressed_regions", [])))),
            ("weak_signals", str(
                len(run_context.parsed_output.get("preserved_weak_signals", [])))),
        ]
        self._render(
            render_semantic_extraction_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Inputs"),
                    ("2", "Inspect Parsed Substrate"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_investigation_analysis_run_review(
        self,
        run_context: InvestigationAnalysisRunContext,
    ) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "investigation_analysis_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("source_substrate_id", str(run_context.component_run.get(
                "source_substrate_id", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("hypotheses", str(len(run_context.parsed_output.get("hypotheses", [])))),
            ("overlap_pairs", str(
                len(run_context.hypothesis_index.get("overlap_pairs", [])))),
        ]
        self._render(
            render_investigation_analysis_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Inputs"),
                    ("2", "Inspect Hypothesis Set"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_hypothesis_ranking_run_review(
        self,
        run_context: HypothesisRankingRunContext,
    ) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "hypothesis_ranking_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("analysis_id", str(run_context.component_run.get("analysis_id", "unknown"))),
            ("round_id", str(run_context.component_run.get("round_id", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("selected", str(len(run_context.parsed_output.get(
                "selected_hypothesis_ids", [])))),
            ("deferred", str(len(run_context.parsed_output.get(
                "deferred_hypothesis_ids", [])))),
        ]
        self._render(
            render_hypothesis_ranking_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Inputs"),
                    ("2", "Inspect Selection Decision"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_planner_run_review(
        self,
        run_context: PlannerRunContext,
    ) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "planner_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("round_id", str(run_context.component_run.get("round_id", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("selected", str(len(run_context.ranking_decision_min.get(
                "selected_hypothesis_ids", [])))),
            ("strategies", str(len(run_context.parsed_output.get("planner_strategies", [])))),
        ]
        self._render(
            render_planner_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Inputs"),
                    ("2", "Inspect Strategy Bundle"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_router_run_review(
        self,
        run_context: RouterRunContext,
    ) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "router_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("round_id", str(run_context.component_run.get("round_id", "unknown"))),
            ("hypothesis_id", str(run_context.component_run.get(
                "hypothesis_id", "unknown"))),
            ("strategy_id", str(run_context.component_run.get(
                "planner_strategy_id", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("tasks", str(len(run_context.parsed_output.get("worker_tasks", [])))),
        ]
        self._render(
            render_router_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Planner Input / Reduced Context"),
                    ("2", "Inspect Task Bundle"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_worker_run_review(
        self,
        run_context: WorkerRunContext,
    ) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "worker_run"
        worker_result = self._get_worker_result_payload(run_context)
        allowed_actions = ", ".join(
            list(run_context.worker_task.get("allowed_actions", []))[:3]) or "none"
        local_context_refs = ", ".join(
            list(run_context.worker_task.get("local_context_refs", []))[:4]) or "none"
        step_traces = self._build_worker_step_traces(run_context)
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("round_id", str(run_context.component_run.get("round_id", "unknown"))),
            ("task_id", str(run_context.component_run.get("task_id", "unknown"))),
            ("hypothesis_id", str(run_context.component_run.get(
                "hypothesis_id", "unknown"))),
            ("task_scope", self._preview_text(
                run_context.worker_task.get("task_scope"), limit=110)),
            ("allowed_actions", self._preview_text(allowed_actions, limit=110)),
            ("local_context_refs", self._preview_text(
                local_context_refs, limit=110)),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("worker_status", str(run_context.component_run.get(
                "worker_status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("steps", str(len(step_traces))),
            ("tool_events", str(len(run_context.tool_events))),
            ("findings", str(len(worker_result.get("findings", [])))),
            ("contradictions", str(len(worker_result.get("contradictions", [])))),
            ("limitations", str(len(worker_result.get("limitations", [])))),
        ]
        self._render(
            render_worker_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                latest_step_lines=self._build_worker_latest_step_lines(
                    run_context),
                options=[
                    ("1", "Inspect Task / Runtime Context"),
                    ("2", "Browse Step Timeline"),
                    ("3", "Inspect Latest Step"),
                    ("4", "Inspect Validation"),
                    ("5", "Inspect Prompt / Response"),
                    ("6", "Inspect Trace And Result"),
                    ("7", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_aggregation_run_review(
        self,
        run_context: AggregationRunContext,
    ) -> None:
        run_name = Path(
            run_context.artifact_paths.get("component_run_path", "")
        ).parent.name or "aggregation_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("round_id", str(run_context.component_run.get("round_id", "unknown"))),
            ("hypothesis_id", str(run_context.component_run.get(
                "hypothesis_id", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("handoff_committed", str(
                run_context.component_run.get("handoff_committed", False))),
            ("repair_attempts", str(len(
                run_context.repair_attempts or run_context.validation_report.get("repair_attempts", [])))),
            ("worker_results", str(
                len(run_context.worker_result_set.get("worker_results", [])))),
        ]
        self._render(
            render_aggregation_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Source Worker Results"),
                    ("2", "Inspect Merge Output"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_state_manager_run_review(
        self,
        run_context: StateManagerRunContext,
    ) -> None:
        run_name = Path(
            run_context.artifact_paths.get("component_run_path", "")
        ).parent.name or "state_manager_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("round_id", str(run_context.component_run.get("round_id", "unknown"))),
            ("hypothesis_id", str(run_context.component_run.get(
                "hypothesis_id", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("state_committed", str(
                run_context.component_run.get("state_committed", False))),
            (
                "state_versions",
                f"{run_context.component_run.get('previous_state_version', 'unknown')} -> {run_context.component_run.get('new_state_version', 'unknown')}",
            ),
        ]
        self._render(
            render_state_manager_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Prior State / Context"),
                    ("2", "Inspect State Delta And Updated State"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _handle_tool_review_choice(self, choice: str, run_context: ToolRunContext) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Normalized Inputs",
                    path_label="Phase 3A Components / Tools / Review / Normalized Inputs",
                    payload=run_context.normalized_inputs,
                    hint="Exact resolved input surface used for deterministic execution.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Raw Tool Output",
                    path_label="Phase 3A Components / Tools / Review / Raw Output",
                    payload=run_context.raw_tool_output,
                    hint="Legacy raw output before Phase 3A normalization.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Parsed Tool Output",
                    path_label="Phase 3A Components / Tools / Review / Parsed Output",
                    payload=run_context.parsed_output,
                    hint="Phase 3A normalized tool_result contract.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Tools / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Request, inventory, and result validation outcome.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.tool_metrics.get("duration_ms", 0.0))),
            ("cache_status", str(run_context.tool_metrics.get("cache_status", "unknown"))),
            ("cache_event_count", str(
                run_context.tool_metrics.get("cache_event_count", 0))),
            ("fresh_execution", str(run_context.tool_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.tool_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Tool Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=[
                    str(run_context.component_run.get("tool_name", "unknown"))],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("tool_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Tools / Review / Technical Details",
                hint="Artifact-first debugging surface for direct tool execution.",
            )
        )
        self._wait_for_enter()

    def _handle_semantic_extraction_review_choice(
        self,
        choice: str,
        run_context: SemanticExtractionRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Semantic Extraction Inputs",
                    path_label="Phase 3A Components / Semantic Extraction / Review / Inputs",
                    payload={
                        "overview_summary_min": run_context.overview_summary_min,
                        "partition_context": run_context.partition_context,
                        "projected_evidence": run_context.projected_evidence,
                    },
                    hint="Current overview input, normalized partition context, and projected evidence payload.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Parsed Semantic Substrate",
                    path_label="Phase 3A Components / Semantic Extraction / Review / Parsed Output",
                    payload=run_context.parsed_output,
                    hint="Structured substrate handed off for downstream Investigation Analysis.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Semantic Extraction / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Overview, context, parse, and substrate validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Prompt And Raw Response",
                    path_label="Phase 3A Components / Semantic Extraction / Review / Prompt Response",
                    content="=== PROMPT ===\n\n"
                    + run_context.prompt_text
                    + "\n\n=== RAW RESPONSE ===\n\n"
                    + run_context.raw_response_text,
                    hint="Rendered prompt and raw model response for artifact-first debugging.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("prompt_chars", str(run_context.runtime_metrics.get("prompt_chars", 0))),
            ("raw_response_chars", str(
                run_context.runtime_metrics.get("raw_response_chars", 0))),
            ("evidence_count", str(run_context.runtime_metrics.get("evidence_count", 0))),
            ("region_count", str(run_context.runtime_metrics.get("region_count", 0))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Semantic Extraction Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["semantic_extraction"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Semantic Extraction / Review / Technical Details",
                hint="Artifact-first debugging surface for Semantic Extraction runs.",
            )
        )
        self._wait_for_enter()

    def _handle_investigation_analysis_review_choice(
        self,
        choice: str,
        run_context: InvestigationAnalysisRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Investigation Analysis Inputs",
                    path_label="Phase 3A Components / Investigation Analysis / Review / Inputs",
                    payload={
                        "semantic_substrate_input": run_context.semantic_substrate_input,
                        "analysis_context_min": run_context.analysis_context_min,
                        "analysis_iteration_context_min": run_context.analysis_iteration_context_min,
                        "projected_substrate": run_context.projected_substrate,
                        "projected_analysis_context": run_context.projected_analysis_context,
                        "projected_iteration_context": run_context.projected_iteration_context,
                    },
                    hint="Exact substrate, context refs, and prompt-ready projections used by Investigation Analysis.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Hypothesis Set",
                    path_label="Phase 3A Components / Investigation Analysis / Review / Hypothesis Set",
                    payload={
                        "hypothesis_set": run_context.parsed_output,
                        "hypothesis_index": run_context.hypothesis_index,
                    },
                    hint="Structured hypotheses plus overlap and evidence coverage index.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Investigation Analysis / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Input, parse, and anti-planning validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Prompt And Raw Response",
                    path_label="Phase 3A Components / Investigation Analysis / Review / Prompt Response",
                    content="=== PROMPT ===\n\n"
                    + run_context.prompt_text
                    + "\n\n=== RAW RESPONSE ===\n\n"
                    + run_context.raw_response_text,
                    hint="Rendered prompt and raw model response for artifact-first debugging.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("prompt_chars", str(run_context.runtime_metrics.get("prompt_chars", 0))),
            ("raw_response_chars", str(
                run_context.runtime_metrics.get("raw_response_chars", 0))),
            ("hypothesis_count", str(
                run_context.runtime_metrics.get("hypothesis_count", 0))),
            ("overlap_count", str(run_context.runtime_metrics.get("overlap_count", 0))),
            ("open_question_count", str(
                run_context.runtime_metrics.get("open_question_count", 0))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Investigation Analysis Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["investigation_analysis"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Investigation Analysis / Review / Technical Details",
                hint="Artifact-first debugging surface for Investigation Analysis runs.",
            )
        )
        self._wait_for_enter()

    def _handle_hypothesis_ranking_review_choice(
        self,
        choice: str,
        run_context: HypothesisRankingRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Hypothesis Ranking Inputs",
                    path_label="Phase 3A Components / Hypothesis Ranking / Review / Inputs",
                    payload={
                        "candidate_hypotheses": run_context.candidate_hypotheses,
                        "ranking_state_snapshot": run_context.ranking_state_snapshot,
                        "projected_candidate_context": run_context.projected_candidate_context,
                        "projected_ranking_state": run_context.projected_ranking_state,
                    },
                    hint="Exact candidate hypothesis set, ranking snapshot, and prompt-ready projections used by Hypothesis Ranking.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Selection Decision",
                    path_label="Phase 3A Components / Hypothesis Ranking / Review / Selection Decision",
                    payload={
                        "ranking_decision": run_context.parsed_output,
                        "selection_index": run_context.selection_index,
                    },
                    hint="Structured ranking decision plus selected-versus-deferred inspection index.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Hypothesis Ranking / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Input, parse, and allocation-only validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Prompt And Raw Response",
                    path_label="Phase 3A Components / Hypothesis Ranking / Review / Prompt Response",
                    content="=== PROMPT ===\n\n"
                    + run_context.prompt_text
                    + "\n\n=== RAW RESPONSE ===\n\n"
                    + run_context.raw_response_text,
                    hint="Rendered prompt and raw model response for artifact-first debugging.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("prompt_chars", str(run_context.runtime_metrics.get("prompt_chars", 0))),
            ("raw_response_chars", str(
                run_context.runtime_metrics.get("raw_response_chars", 0))),
            ("candidate_count", str(run_context.runtime_metrics.get("candidate_count", 0))),
            ("selected_count", str(run_context.runtime_metrics.get("selected_count", 0))),
            ("deferred_count", str(run_context.runtime_metrics.get("deferred_count", 0))),
            ("selection_budget", str(
                run_context.runtime_metrics.get("selection_budget", 0))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Hypothesis Ranking Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["hypothesis_ranking"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Hypothesis Ranking / Review / Technical Details",
                hint="Artifact-first debugging surface for Hypothesis Ranking runs.",
            )
        )
        self._wait_for_enter()

    def _handle_planner_review_choice(
        self,
        choice: str,
        run_context: PlannerRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Planner Inputs",
                    path_label="Phase 3A Components / Planner / Review / Inputs",
                    payload={
                        "ranking_decision_min": run_context.ranking_decision_min,
                        "selected_hypothesis_context": run_context.selected_hypothesis_context,
                        "planner_round_context": run_context.planner_round_context,
                        "projected_selected_context": run_context.projected_selected_context,
                        "projected_planner_round_context": run_context.projected_planner_round_context,
                    },
                    hint="Exact selected-set, round context, and prompt-ready projections used by Planner.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Planner Strategy Bundle",
                    path_label="Phase 3A Components / Planner / Review / Strategy Bundle",
                    payload={
                        "planner_round_output": run_context.parsed_output,
                        "strategy_index": run_context.strategy_index,
                    },
                    hint="Structured planner strategies plus per-hypothesis planning index.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Planner / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Input, parse, and strategic-boundary validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Prompt And Raw Response",
                    path_label="Phase 3A Components / Planner / Review / Prompt Response",
                    content="=== PROMPT ===\n\n"
                    + run_context.prompt_text
                    + "\n\n=== RAW RESPONSE ===\n\n"
                    + run_context.raw_response_text,
                    hint="Rendered prompt and raw model response for artifact-first debugging.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("prompt_chars", str(run_context.runtime_metrics.get("prompt_chars", 0))),
            ("raw_response_chars", str(
                run_context.runtime_metrics.get("raw_response_chars", 0))),
            ("selected_count", str(run_context.runtime_metrics.get("selected_count", 0))),
            ("strategy_count", str(run_context.runtime_metrics.get("strategy_count", 0))),
            ("tool_capability_ref_count", str(
                run_context.runtime_metrics.get("tool_capability_ref_count", 0))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Planner Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=list(run_context.planner_round_context.get(
                    "tool_capability_refs", [])) or ["planner"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Planner / Review / Technical Details",
                hint="Artifact-first debugging surface for Planner runs.",
            )
        )
        self._wait_for_enter()

    def _handle_router_review_choice(
        self,
        choice: str,
        run_context: RouterRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Router Inputs And Reduced Context",
                    path_label="Phase 3A Components / Router / Review / Inputs Context",
                    payload={
                        "planner_strategy": run_context.planner_strategy,
                        "router_context_min": run_context.router_context_min,
                        "reduced_context": run_context.reduced_context,
                    },
                    hint="Exact planner strategy, minimal routing context, and reduced prompt-ready context used by Router.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Router Task Bundle",
                    path_label="Phase 3A Components / Router / Review / Task Bundle",
                    payload={
                        "router_output": run_context.parsed_output,
                        "task_bundle_index": run_context.task_bundle_index,
                    },
                    hint="Structured worker-task bundle plus summary index for manual routing review.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Router / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Input, parse, and task-boundary validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Prompt And Raw Response",
                    path_label="Phase 3A Components / Router / Review / Prompt Response",
                    content="=== PROMPT ===\n\n"
                    + run_context.prompt_text
                    + "\n\n=== RAW RESPONSE ===\n\n"
                    + run_context.raw_response_text,
                    hint="Rendered prompt and raw model response for artifact-first debugging.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("prompt_chars", str(run_context.runtime_metrics.get("prompt_chars", 0))),
            ("raw_response_chars", str(
                run_context.runtime_metrics.get("raw_response_chars", 0))),
            ("task_count", str(run_context.runtime_metrics.get("task_count", 0))),
            ("allowed_action_class_count", str(
                run_context.runtime_metrics.get("allowed_action_class_count", 0))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Router Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=list(run_context.router_context_min.get(
                    "tool_capability_refs", [])) or ["router"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Router / Review / Technical Details",
                hint="Artifact-first debugging surface for Router runs.",
            )
        )
        self._wait_for_enter()

    def _render_worker_step_review_screen(
        self,
        run_context: WorkerRunContext,
        step_trace: WorkerStepTrace,
    ) -> None:
        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "worker_run"
        focus_lines = [
            f"reasoning: {self._preview_text(step_trace.reasoning_summary, limit=140)}",
            f"proposed_actions={len(step_trace.proposed_actions)} | executed_actions={len(step_trace.executed_actions)} | retries={len(step_trace.retry_events)} | failures={len(step_trace.failure_events)}",
        ]
        if step_trace.proposed_actions:
            action_preview = ", ".join(
                self._preview_text(action.get("action_class"), limit=40)
                for action in step_trace.proposed_actions[:3]
            )
            focus_lines.append(f"proposed: {action_preview}")
        if step_trace.flags:
            focus_lines.append(
                f"flags: {self._preview_text('; '.join(step_trace.flags), limit=140)}")

        self._render(
            render_worker_step_review(
                task_id=str(run_context.component_run.get(
                    "task_id", "unknown_task")),
                step_label=f"step={step_trace.step_index} | mode={step_trace.step_mode} | decision={step_trace.decision or 'unknown'}",
                summary_pairs=[
                    ("attempts", str(len(step_trace.attempts))),
                    ("latest_attempt", str(step_trace.latest_attempt.attempt_index)),
                    ("decision", step_trace.decision or "unknown"),
                    ("execution_history_before_step", str(
                        len(step_trace.execution_history_before_step))),
                    ("executed_actions", str(len(step_trace.executed_actions))),
                    ("flags", str(len(step_trace.flags))),
                ],
                focus_lines=focus_lines,
                options=[
                    ("1", "Inspect Prompt / Raw Response"),
                    ("2", "Inspect Parsed Output / Validation"),
                    ("3", "Inspect Execution History Before Step"),
                    ("4", "Inspect Actions / Results"),
                    ("5", "Inspect Retries / Failures / Flags"),
                    ("6", "Inspect Full Step Payload"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _view_worker_step_review_menu(
        self,
        run_context: WorkerRunContext,
        step_trace: WorkerStepTrace,
    ) -> None:
        while True:
            self._render_worker_step_review_screen(run_context, step_trace)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "6", "B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return
            if choice == "1":
                self._render(
                    render_text_view(
                        title="Worker Step Prompt / Raw Response",
                        path_label="Phase 3A Components / Worker / Review / Step / Prompt Response",
                        content="=== PROMPT ===\n\n"
                        + step_trace.latest_attempt.prompt_text
                        + "\n\n=== RAW RESPONSE ===\n\n"
                        + step_trace.latest_attempt.raw_response_text,
                        hint="Rendered prompt snapshot and raw model response for the selected Worker step.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "2":
                self._render(
                    render_tool_json_view(
                        title="Worker Step Parsed Output / Validation",
                        path_label="Phase 3A Components / Worker / Review / Step / Parsed Validation",
                        payload={
                            "parsed_output": step_trace.latest_attempt.parsed_output,
                            "validator_output": step_trace.latest_attempt.validator_output,
                            "attempts": [
                                {
                                    "attempt_index": attempt.attempt_index,
                                    "parsed_output": attempt.parsed_output,
                                    "validator_output": attempt.validator_output,
                                }
                                for attempt in step_trace.attempts
                            ],
                        },
                        hint="Latest parsed step output plus the full per-attempt parser and validator record.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "3":
                self._render(
                    render_tool_json_view(
                        title="Worker Step Execution History",
                        path_label="Phase 3A Components / Worker / Review / Step / Execution History",
                        payload=step_trace.execution_history_before_step,
                        hint="All executed tool actions before this step, used as the local execution history context.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "4":
                self._render(
                    render_tool_json_view(
                        title="Worker Step Actions And Results",
                        path_label="Phase 3A Components / Worker / Review / Step / Actions Results",
                        payload={
                            "proposed_actions": step_trace.proposed_actions,
                            "executed_actions": step_trace.executed_actions,
                            "action_results": step_trace.action_results,
                        },
                        hint="Step-local proposed actions, executed actions, and normalized action results.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "5":
                self._render(
                    render_tool_json_view(
                        title="Worker Step Retries / Failures / Flags",
                        path_label="Phase 3A Components / Worker / Review / Step / Flags",
                        payload={
                            "retry_events": step_trace.retry_events,
                            "failure_events": step_trace.failure_events,
                            "flags": step_trace.flags,
                        },
                        hint="Retry records, failure records, and normalized warnings or flags for the selected step.",
                    )
                )
                self._wait_for_enter()
                continue

            self._render(
                render_tool_json_view(
                    title="Worker Full Step Payload",
                    path_label="Phase 3A Components / Worker / Review / Step / Full Payload",
                    payload={
                        "step_index": step_trace.step_index,
                        "step_mode": step_trace.step_mode,
                        "attempts": [
                            {
                                "step_index": attempt.step_index,
                                "step_mode": attempt.step_mode,
                                "attempt_index": attempt.attempt_index,
                                "repair_note": attempt.repair_note,
                                "decision": attempt.decision,
                                "reasoning_summary": attempt.reasoning_summary,
                                "proposed_actions": attempt.proposed_actions,
                                "worker_result": attempt.worker_result,
                                "prompt_text": attempt.prompt_text,
                                "raw_response_text": attempt.raw_response_text,
                                "parsed_output": attempt.parsed_output,
                                "validator_output": attempt.validator_output,
                            }
                            for attempt in step_trace.attempts
                        ],
                        "execution_history_before_step": step_trace.execution_history_before_step,
                        "executed_actions": step_trace.executed_actions,
                        "action_results": step_trace.action_results,
                        "retry_events": step_trace.retry_events,
                        "failure_events": step_trace.failure_events,
                        "flags": step_trace.flags,
                    },
                    hint="Full normalized step payload for exhaustive Worker debugging.",
                )
            )
            self._wait_for_enter()

    def _view_worker_step_timeline_menu(
        self,
        run_context: WorkerRunContext,
    ) -> None:
        step_traces = self._build_worker_step_traces(run_context)
        if not step_traces:
            self._show_error(
                "No persisted Worker steps are available for this run.")
            return

        while True:
            self._render(
                render_worker_step_index(
                    task_id=str(run_context.component_run.get(
                        "task_id", "unknown_task")),
                    step_lines=self._build_worker_step_index_lines(
                        step_traces),
                    options=[("B", "Back"), ("Q", "Quit")],
                )
            )
            choice = self._read_menu_choice(
                {str(index) for index in range(1, len(step_traces) + 1)} | {"B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return
            self._view_worker_step_review_menu(
                run_context, step_traces[int(choice) - 1])
            if not self._running:
                return

    def _handle_worker_review_choice(
        self,
        choice: str,
        run_context: WorkerRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Worker Task And Runtime Context",
                    path_label="Phase 3A Components / Worker / Review / Inputs",
                    payload={
                        "worker_task": run_context.worker_task,
                        "worker_runtime_refs": run_context.worker_runtime_refs,
                    },
                    hint="Exact routed worker task and runtime-only local context surface used for execution.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._view_worker_step_timeline_menu(run_context)
            return
        if choice == "3":
            step_traces = self._build_worker_step_traces(run_context)
            if not step_traces:
                self._show_error(
                    "No persisted Worker steps are available for this run.")
                return
            self._view_worker_step_review_menu(run_context, step_traces[-1])
            return
        if choice == "4":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Worker / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Task, runtime, result, and output validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "5":
            self._render(
                render_text_view(
                    title="Prompt And Raw Responses",
                    path_label="Phase 3A Components / Worker / Review / Prompt Response",
                    content=self._build_worker_prompt_response_text(
                        run_context),
                    hint="Rendered prompt snapshots and raw model responses for artifact-first debugging.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "6":
            self._render(
                render_tool_json_view(
                    title="Worker Trace And Result",
                    path_label="Phase 3A Components / Worker / Review / Trace Result",
                    payload={
                        "parsed_steps": run_context.parsed_steps,
                        "tool_events": run_context.tool_events,
                        "retry_events": run_context.retry_events,
                        "failure_events": run_context.failure_events,
                        "worker_output": run_context.worker_output,
                        "operational_trace": run_context.operational_trace,
                    },
                    hint="Bounded local execution trace plus the final worker output.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("steps_used", str(run_context.runtime_metrics.get("steps_used", 0))),
            ("retries_used", str(run_context.runtime_metrics.get("retries_used", 0))),
            ("tool_event_count", str(
                run_context.runtime_metrics.get("tool_event_count", 0))),
            ("failure_event_count", str(
                run_context.runtime_metrics.get("failure_event_count", 0))),
            ("termination_cause", str(run_context.runtime_metrics.get(
                "termination_cause", "unknown"))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Worker Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=list(run_context.worker_task.get(
                    "allowed_actions", [])) or ["worker"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Worker / Review / Technical Details",
                hint="Artifact-first debugging surface for Worker runs.",
            )
        )
        self._wait_for_enter()

    def _handle_aggregation_review_choice(
        self,
        choice: str,
        run_context: AggregationRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Aggregation Source Worker Results",
                    path_label="Phase 3A Components / Aggregation / Review / Inputs",
                    payload={
                        "worker_result_set": run_context.worker_result_set,
                        "normalized_inputs": run_context.normalized_inputs,
                    },
                    hint="Exact hypothesis-local Worker results and normalized merge inputs.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Aggregation Merge Output",
                    path_label="Phase 3A Components / Aggregation / Review / Merge Output",
                    payload={
                        "overlap_diagnostics": run_context.overlap_diagnostics,
                        "parsed_output": run_context.parsed_output,
                        "aggregation_handoff": run_context.aggregation_handoff,
                    },
                    hint="Overlap diagnostics plus the parsed and committed merge handoff.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Aggregation / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Worker-result set, parse, and handoff validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Aggregation Prompt / Response",
                    path_label="Phase 3A Components / Aggregation / Review / Prompt Response",
                    content=self._build_aggregation_prompt_response_text(
                        run_context),
                    hint="Exact prompt sent to the model and the raw response returned.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("worker_result_count", str(
                run_context.runtime_metrics.get("worker_result_count", 0))),
            ("overlap_group_count", str(
                run_context.runtime_metrics.get("overlap_group_count", 0))),
            ("source_contradiction_count", str(
                run_context.runtime_metrics.get("source_contradiction_count", 0))),
            ("handoff_committed", str(
                run_context.runtime_metrics.get("handoff_committed", False))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Aggregation Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["aggregation"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Aggregation / Review / Technical Details",
                hint="Artifact-first debugging surface for Aggregation runs.",
            )
        )
        self._wait_for_enter()

    def _handle_state_manager_review_choice(
        self,
        choice: str,
        run_context: StateManagerRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="State Manager Prior State / Context",
                    path_label="Phase 3A Components / State Manager / Review / Prior State",
                    payload={
                        "prior_state": run_context.prior_state,
                        "state_manager_context": run_context.state_manager_context,
                        "aggregation_handoff": run_context.aggregation_handoff,
                    },
                    hint="Canonical state snapshot and bounded context used before the revision.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="State Manager Delta And Updated State",
                    path_label="Phase 3A Components / State Manager / Review / Delta",
                    payload={
                        "state_delta_record": run_context.state_delta_record,
                        "state_update_result": run_context.state_update_result,
                        "updated_batch_state": run_context.updated_batch_state,
                    },
                    hint="Committed patch result plus the resulting canonical batch state snapshot.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / State Manager / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Canonical state input, handoff, parse, and state-delta validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="State Manager Prompt / Response",
                    path_label="Phase 3A Components / State Manager / Review / Prompt Response",
                    content=self._build_state_manager_prompt_response_text(
                        run_context),
                    hint="Exact prompt sent to the model and the raw response returned.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("request_id", str(run_context.component_run.get("request_id", "unknown"))),
            ("prompt_version", str(run_context.component_run.get(
                "prompt_version", "unknown"))),
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("previous_state_version", str(run_context.runtime_metrics.get(
                "previous_state_version", "unknown"))),
            ("new_state_version", str(run_context.runtime_metrics.get(
                "new_state_version", "unknown"))),
            ("applied_update_count", str(
                run_context.runtime_metrics.get("applied_update_count", 0))),
            ("remaining_open_gap_count", str(
                run_context.runtime_metrics.get("remaining_open_gap_count", 0))),
            ("state_committed", str(
                run_context.runtime_metrics.get("state_committed", False))),
            ("prior_state_origin", str(run_context.runtime_metrics.get(
                "prior_state_origin", "unknown"))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="State Manager Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["state_manager"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / State Manager / Review / Technical Details",
                hint="Artifact-first debugging surface for State Manager runs.",
            )
        )
        self._wait_for_enter()

    def _handle_critic_review_choice(
        self,
        choice: str,
        run_context: CriticRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Critic Input Summary",
                    path_label="Phase 3A Components / Critic / Review / Input Summary",
                    payload={
                        "critic_input_min": run_context.critic_input_min,
                        "refined_state_summary": run_context.refined_state_summary,
                        "module_behavior_summaries": run_context.module_behavior_summaries,
                        "process_signal_summary": run_context.process_signal_summary,
                    },
                    hint="Bounded runtime summaries and references used for the reflective review.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Critic Observations",
                    path_label="Phase 3A Components / Critic / Review / Observations",
                    payload=run_context.critic_observations_payload,
                    hint="Bounded strategic observations emitted for the next round.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Critic / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Input, final-round gate, parse, and advisory-boundary validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Critic Prompt / Response",
                    path_label="Phase 3A Components / Critic / Review / Prompt Response",
                    content=self._build_critic_prompt_response_text(
                        run_context),
                    hint="Exact prompt sent to the model and the raw response returned.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("request_id", str(run_context.component_run.get("request_id", "unknown"))),
            ("prompt_version", str(run_context.component_run.get(
                "prompt_version", "unknown"))),
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("final_round_gate", str(run_context.runtime_metrics.get(
                "final_round_gate_status", "unknown"))),
            ("observation_count", str(
                run_context.runtime_metrics.get("observation_count", 0))),
            ("observations_committed", str(
                run_context.runtime_metrics.get("observations_committed", False))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Critic Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["critic"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Critic / Review / Technical Details",
                hint="Artifact-first debugging surface for Critic runs.",
            )
        )
        self._wait_for_enter()

    def _handle_final_batch_auditor_review_choice(
        self,
        choice: str,
        run_context: FinalBatchAuditorRunContext,
    ) -> None:
        if choice == "1":
            self._render(
                render_tool_json_view(
                    title="Final Batch Audit Input Summary",
                    path_label="Phase 3A Components / Final Batch Auditor / Review / Input Summary",
                    payload={
                        "final_audit_input": run_context.final_audit_input,
                        "final_state_summary": run_context.final_state_summary,
                        "round_history_summary": run_context.round_history_summary,
                        "process_signal_summary": run_context.process_signal_summary,
                    },
                    hint="Bounded terminal audit refs and summaries used for retrospective inspection.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "2":
            self._render(
                render_tool_json_view(
                    title="Debugging Audit Report",
                    path_label="Phase 3A Components / Final Batch Auditor / Review / Debugging Report",
                    payload=run_context.debugging_audit_report,
                    hint="Terminal debugging-oriented retrospective batch report.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "3":
            self._render(
                render_tool_json_view(
                    title="Validation Report",
                    path_label="Phase 3A Components / Final Batch Auditor / Review / Validation",
                    payload=run_context.validation_report,
                    hint="Terminal gate, input, parse, and report-boundary validation outcome.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "4":
            self._render(
                render_text_view(
                    title="Final Batch Auditor Prompt / Response",
                    path_label="Phase 3A Components / Final Batch Auditor / Review / Prompt Response",
                    content=self._build_final_batch_auditor_prompt_response_text(
                        run_context),
                    hint="Exact prompt sent to the model and the raw response returned.",
                )
            )
            self._wait_for_enter()
            return

        metrics = [
            ("request_id", str(run_context.component_run.get("request_id", "unknown"))),
            ("prompt_version", str(run_context.component_run.get(
                "prompt_version", "unknown"))),
            ("duration_ms", str(run_context.runtime_metrics.get("duration_ms", 0.0))),
            ("terminal_gate", str(run_context.runtime_metrics.get(
                "terminal_gate_status", "unknown"))),
            ("traceability_ref_count", str(
                run_context.runtime_metrics.get("traceability_ref_count", 0))),
            ("round_ref_count", str(run_context.runtime_metrics.get("round_ref_count", 0))),
            ("history_ref_count", str(
                run_context.runtime_metrics.get("history_ref_count", 0))),
            ("audit_mode", str(run_context.runtime_metrics.get(
                "audit_mode", "authoritative"))),
            ("fresh_execution", str(
                run_context.runtime_metrics.get("fresh_execution", True))),
            ("schema_version", str(run_context.runtime_metrics.get(
                "schema_version", "unknown"))),
        ]
        self._render(
            render_technical_details(
                title="Final Batch Auditor Technical Details",
                run_name=Path(run_context.artifact_paths.get(
                    "component_run_path", "")).parent.name or None,
                metrics=metrics,
                tools_used=["final_batch_auditor"],
                artifact_paths={
                    "run_log_path": run_context.artifact_paths.get("component_run_path", "unavailable"),
                    "metrics_log_path": run_context.artifact_paths.get("runtime_metrics_path", "unavailable"),
                },
                path_label="Phase 3A Components / Final Batch Auditor / Review / Technical Details",
                hint="Artifact-first debugging surface for terminal batch audits.",
            )
        )
        self._wait_for_enter()

    def _print_tool_inventory(self) -> None:
        records = get_tool_capability_records()
        ordered_records = [records[name] for name in sorted(records.keys())]
        self._render(render_tool_inventory(ordered_records))
        self._wait_for_enter()

    def _latest_tool_run_menu(self) -> str:
        run_context = self._get_latest_tool_run_context()
        if run_context is None:
            self._show_error("No persisted tool runs are available yet.")
            return "tools"

        while True:
            self._render_tool_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "tools"
            if choice == "B":
                return "tools"
            self._handle_tool_review_choice(choice, run_context)

    def _latest_semantic_extraction_run_menu(self) -> str:
        run_context = self._get_latest_semantic_extraction_run_context()
        if run_context is None:
            self._show_error(
                "No persisted Semantic Extraction runs are available yet.")
            return "semantic_extraction"

        while True:
            self._render_semantic_extraction_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "semantic_extraction"
            if choice == "B":
                return "semantic_extraction"
            self._handle_semantic_extraction_review_choice(choice, run_context)

    def _latest_investigation_analysis_run_menu(self) -> str:
        run_context = self._get_latest_investigation_analysis_run_context()
        if run_context is None:
            self._show_error(
                "No persisted Investigation Analysis runs are available yet.")
            return "investigation_analysis"

        while True:
            self._render_investigation_analysis_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "investigation_analysis"
            if choice == "B":
                return "investigation_analysis"
            self._handle_investigation_analysis_review_choice(
                choice, run_context)

    def _latest_hypothesis_ranking_run_menu(self) -> str:
        run_context = self._get_latest_hypothesis_ranking_run_context()
        if run_context is None:
            self._show_error(
                "No persisted Hypothesis Ranking runs are available yet.")
            return "hypothesis_ranking"

        while True:
            self._render_hypothesis_ranking_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "hypothesis_ranking"
            if choice == "B":
                return "hypothesis_ranking"
            self._handle_hypothesis_ranking_review_choice(choice, run_context)

    def _latest_planner_run_menu(self) -> str:
        run_context = self._get_latest_planner_run_context()
        if run_context is None:
            self._show_error("No persisted Planner runs are available yet.")
            return "planner"

        while True:
            self._render_planner_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "planner"
            if choice == "B":
                return "planner"
            self._handle_planner_review_choice(choice, run_context)

    def _latest_router_run_menu(self) -> str:
        run_context = self._get_latest_router_run_context()
        if run_context is None:
            self._show_error("No persisted Router runs are available yet.")
            return "router"

        while True:
            self._render_router_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "router"
            if choice == "B":
                return "router"
            self._handle_router_review_choice(choice, run_context)

    def _latest_worker_run_menu(self) -> str:
        run_context = self._get_latest_worker_run_context()
        if run_context is None:
            self._show_error("No persisted Worker runs are available yet.")
            return "worker"

        while True:
            self._render_worker_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "6", "7", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "worker"
            if choice == "B":
                return "worker"
            self._handle_worker_review_choice(choice, run_context)

    def _latest_aggregation_run_menu(self) -> str:
        run_context = self._get_latest_aggregation_run_context()
        if run_context is None:
            self._show_error(
                "No persisted Aggregation runs are available yet.")
            return "aggregation"

        while True:
            self._render_aggregation_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "aggregation"
            if choice == "B":
                return "aggregation"
            self._handle_aggregation_review_choice(choice, run_context)

    def _latest_state_manager_run_menu(self) -> str:
        run_context = self._get_latest_state_manager_run_context()
        if run_context is None:
            self._show_error(
                "No persisted State Manager runs are available yet.")
            return "state_manager"

        while True:
            self._render_state_manager_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "state_manager"
            if choice == "B":
                return "state_manager"
            self._handle_state_manager_review_choice(choice, run_context)

    def _latest_critic_run_menu(self) -> str:
        run_context = self._get_latest_critic_run_context()
        if run_context is None:
            self._show_error("No persisted Critic runs are available yet.")
            return "critic"

        while True:
            self._render_critic_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "critic"
            if choice == "B":
                return "critic"
            self._handle_critic_review_choice(choice, run_context)

    def _latest_final_batch_auditor_run_menu(self) -> str:
        run_context = self._get_latest_final_batch_auditor_run_context()
        if run_context is None:
            self._show_error(
                "No persisted Final Batch Auditor runs are available yet.")
            return "final_batch_auditor"

        while True:
            self._render_final_batch_auditor_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "final_batch_auditor"
            if choice == "B":
                return "final_batch_auditor"
            self._handle_final_batch_auditor_review_choice(choice, run_context)

    def _latest_phase3a_runtime_run_menu(self) -> str:
        run_context = self._get_latest_phase3a_runtime_run_context()
        if run_context is None:
            self._show_error(
                "No persisted Phase 3A runtime runs are available yet.")
            return "phase3a_runtime"

        while True:
            self._render_phase3a_runtime_run_review(run_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "B", "Q"})
            if choice == "Q":
                self._quit()
                return "phase3a_runtime"
            if choice == "B":
                return "phase3a_runtime"
            self._handle_phase3a_runtime_review_choice(choice, run_context)
            if not self._running:
                return "phase3a_runtime"

    def _view_tool_runs_menu(self) -> str:
        while True:
            recent_runs = list_tool_run_dirs(limit=self._view_tool_runs_limit)
            self._render(render_recent_tool_runs(
                recent_runs, self._view_tool_runs_limit))
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "tools"
                return "tools"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "tools"
            if choice == "B":
                return "tools"
            if choice == "N":
                self._change_view_tool_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_tool_run_context(selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"failed to load tool run: {exc}")
                continue

            while True:
                self._render_tool_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "tools"
                if review_choice == "B":
                    break
                self._handle_tool_review_choice(review_choice, run_context)

    def _view_semantic_extraction_runs_menu(self) -> str:
        while True:
            recent_runs = list_semantic_extraction_run_dirs(
                limit=self._view_semantic_extraction_runs_limit)
            self._render(
                render_recent_semantic_extraction_runs(
                    recent_runs,
                    self._view_semantic_extraction_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "semantic_extraction"
                return "semantic_extraction"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "semantic_extraction"
            if choice == "B":
                return "semantic_extraction"
            if choice == "N":
                self._change_view_semantic_extraction_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_semantic_extraction_run_context(
                    selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(
                    f"failed to load Semantic Extraction run: {exc}")
                continue

            while True:
                self._render_semantic_extraction_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "semantic_extraction"
                if review_choice == "B":
                    break
                self._handle_semantic_extraction_review_choice(
                    review_choice, run_context)

    def _view_investigation_analysis_runs_menu(self) -> str:
        while True:
            recent_runs = list_investigation_analysis_run_dirs(
                limit=self._view_investigation_analysis_runs_limit)
            self._render(
                render_recent_investigation_analysis_runs(
                    recent_runs,
                    self._view_investigation_analysis_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "investigation_analysis"
                return "investigation_analysis"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "investigation_analysis"
            if choice == "B":
                return "investigation_analysis"
            if choice == "N":
                self._change_view_investigation_analysis_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_investigation_analysis_run_context(
                    selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(
                    f"failed to load Investigation Analysis run: {exc}")
                continue

            while True:
                self._render_investigation_analysis_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "investigation_analysis"
                if review_choice == "B":
                    break
                self._handle_investigation_analysis_review_choice(
                    review_choice, run_context)

    def _view_hypothesis_ranking_runs_menu(self) -> str:
        while True:
            recent_runs = list_hypothesis_ranking_run_dirs(
                limit=self._view_hypothesis_ranking_runs_limit)
            self._render(
                render_recent_hypothesis_ranking_runs(
                    recent_runs,
                    self._view_hypothesis_ranking_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "hypothesis_ranking"
                return "hypothesis_ranking"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "hypothesis_ranking"
            if choice == "B":
                return "hypothesis_ranking"
            if choice == "N":
                self._change_view_hypothesis_ranking_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_hypothesis_ranking_run_context(
                    selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(
                    f"failed to load Hypothesis Ranking run: {exc}")
                continue

            while True:
                self._render_hypothesis_ranking_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "hypothesis_ranking"
                if review_choice == "B":
                    break
                self._handle_hypothesis_ranking_review_choice(
                    review_choice, run_context)

    def _view_planner_runs_menu(self) -> str:
        while True:
            recent_runs = list_planner_run_dirs(
                limit=self._view_planner_runs_limit)
            self._render(
                render_recent_planner_runs(
                    recent_runs,
                    self._view_planner_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "planner"
                return "planner"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "planner"
            if choice == "B":
                return "planner"
            if choice == "N":
                self._change_view_planner_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_planner_run_context(selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"failed to load Planner run: {exc}")
                continue

            while True:
                self._render_planner_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "planner"
                if review_choice == "B":
                    break
                self._handle_planner_review_choice(review_choice, run_context)

    def _view_router_runs_menu(self) -> str:
        while True:
            recent_runs = list_router_run_dirs(
                limit=self._view_router_runs_limit)
            self._render(
                render_recent_router_runs(
                    recent_runs,
                    self._view_router_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "router"
                return "router"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "router"
            if choice == "B":
                return "router"
            if choice == "N":
                self._change_view_router_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_router_run_context(selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"failed to load Router run: {exc}")
                continue

            while True:
                self._render_router_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "router"
                if review_choice == "B":
                    break
                self._handle_router_review_choice(review_choice, run_context)

    def _view_worker_runs_menu(self) -> str:
        while True:
            recent_runs = list_worker_run_dirs(
                limit=self._view_worker_runs_limit)
            self._render(
                render_recent_worker_runs(
                    recent_runs,
                    self._view_worker_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "worker"
                return "worker"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "worker"
            if choice == "B":
                return "worker"
            if choice == "N":
                self._change_view_worker_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_worker_run_context(selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"failed to load Worker run: {exc}")
                continue

            while True:
                self._render_worker_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "6", "7", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "worker"
                if review_choice == "B":
                    break
                self._handle_worker_review_choice(review_choice, run_context)

    def _view_aggregation_runs_menu(self) -> str:
        while True:
            recent_runs = list_aggregation_run_dirs(
                limit=self._view_aggregation_runs_limit)
            self._render(
                render_recent_aggregation_runs(
                    recent_runs,
                    self._view_aggregation_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "aggregation"
                return "aggregation"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "aggregation"
            if choice == "B":
                return "aggregation"
            if choice == "N":
                self._change_view_aggregation_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_aggregation_run_context(selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"failed to load Aggregation run: {exc}")
                continue

            while True:
                self._render_aggregation_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "aggregation"
                if review_choice == "B":
                    break
                self._handle_aggregation_review_choice(
                    review_choice, run_context)

    def _view_state_manager_runs_menu(self) -> str:
        while True:
            recent_runs = list_state_manager_run_dirs(
                limit=self._view_state_manager_runs_limit)
            self._render(
                render_recent_state_manager_runs(
                    recent_runs,
                    self._view_state_manager_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "state_manager"
                return "state_manager"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "state_manager"
            if choice == "B":
                return "state_manager"
            if choice == "N":
                self._change_view_state_manager_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_state_manager_run_context(
                    selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"failed to load State Manager run: {exc}")
                continue

            while True:
                self._render_state_manager_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "state_manager"
                if review_choice == "B":
                    break
                self._handle_state_manager_review_choice(
                    review_choice, run_context)

    def _view_critic_runs_menu(self) -> str:
        while True:
            recent_runs = list_critic_run_dirs(
                limit=self._view_critic_runs_limit)
            self._render(
                render_recent_critic_runs(
                    recent_runs,
                    self._view_critic_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "critic"
                return "critic"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "critic"
            if choice == "B":
                return "critic"
            if choice == "N":
                self._change_view_critic_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_critic_run_context(selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"failed to load Critic run: {exc}")
                continue

            while True:
                self._render_critic_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "critic"
                if review_choice == "B":
                    break
                self._handle_critic_review_choice(review_choice, run_context)

    def _view_final_batch_auditor_runs_menu(self) -> str:
        while True:
            recent_runs = list_final_batch_auditor_run_dirs(
                limit=self._view_final_batch_auditor_runs_limit
            )
            self._render(
                render_recent_final_batch_auditor_runs(
                    recent_runs,
                    self._view_final_batch_auditor_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "final_batch_auditor"
                return "final_batch_auditor"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "final_batch_auditor"
            if choice == "B":
                return "final_batch_auditor"
            if choice == "N":
                self._change_view_final_batch_auditor_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_final_batch_auditor_run_context(
                    selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(
                    f"failed to load Final Batch Auditor run: {exc}")
                continue

            while True:
                self._render_final_batch_auditor_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "final_batch_auditor"
                if review_choice == "B":
                    break
                self._handle_final_batch_auditor_review_choice(
                    review_choice, run_context)

    def _view_phase3a_runtime_runs_menu(self) -> str:
        while True:
            recent_runs = list_phase3a_runtime_run_dirs(
                limit=self._view_phase3a_runtime_runs_limit
            )
            self._render(
                render_recent_phase3a_runtime_runs(
                    recent_runs,
                    self._view_phase3a_runtime_runs_limit,
                )
            )
            if not recent_runs:
                choice = self._read_letter_choice({"B", "Q"})
                if choice == "Q":
                    self._quit()
                    return "phase3a_runtime"
                return "phase3a_runtime"

            valid_choices = {str(index) for index in range(
                1, len(recent_runs) + 1)} | {"N", "B", "Q"}
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return "phase3a_runtime"
            if choice == "B":
                return "phase3a_runtime"
            if choice == "N":
                self._change_view_phase3a_runtime_runs_limit()
                continue

            selected_dir = recent_runs[int(choice) - 1]
            try:
                run_context = self._load_phase3a_runtime_run_context(
                    selected_dir)
            except Exception as exc:  # noqa: BLE001
                self._show_error(
                    f"failed to load Phase 3A batch runtime run: {exc}")
                continue

            while True:
                self._render_phase3a_runtime_run_review(run_context)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return "phase3a_runtime"
                if review_choice == "B":
                    break
                self._handle_phase3a_runtime_review_choice(
                    review_choice, run_context)
                if not self._running:
                    return "phase3a_runtime"

    def _change_view_phase3a_runtime_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Phase 3A batch runtime runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            value = int(raw_value)
            if value <= 0:
                print("Enter a positive integer.")
                continue
            self._view_phase3a_runtime_runs_limit = value
            return

    def _change_view_tool_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of tool runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_tool_runs_limit = limit
            return

    def _change_view_semantic_extraction_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Semantic Extraction runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_semantic_extraction_runs_limit = limit
            return

    def _change_view_investigation_analysis_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Investigation Analysis runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_investigation_analysis_runs_limit = limit
            return

    def _change_view_hypothesis_ranking_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Hypothesis Ranking runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_hypothesis_ranking_runs_limit = limit
            return

    def _change_view_planner_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Planner runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_planner_runs_limit = limit
            return

    def _change_view_router_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Router runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_router_runs_limit = limit
            return

    def _change_view_worker_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Worker runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_worker_runs_limit = limit
            return

    def _change_view_aggregation_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Aggregation runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_aggregation_runs_limit = limit
            return

    def _change_view_state_manager_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of State Manager runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_state_manager_runs_limit = limit
            return

    def _change_view_critic_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Critic runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_critic_runs_limit = limit
            return

    def _change_view_final_batch_auditor_runs_limit(self) -> None:
        self._clear_screen()
        print("Enter number of Final Batch Auditor runs to show:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value.isdigit():
                print("Enter a positive integer.")
                continue
            limit = int(raw_value)
            if limit <= 0:
                print("Enter a positive integer.")
                continue
            self._view_final_batch_auditor_runs_limit = limit
            return

    def _get_latest_tool_run_context(self) -> ToolRunContext | None:
        latest_runs = list_tool_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_tool_run_context(latest_runs[0])

    def _get_latest_semantic_extraction_run_context(self) -> SemanticExtractionRunContext | None:
        latest_runs = list_semantic_extraction_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_semantic_extraction_run_context(latest_runs[0])

    def _get_latest_investigation_analysis_run_context(self) -> InvestigationAnalysisRunContext | None:
        latest_runs = list_investigation_analysis_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_investigation_analysis_run_context(latest_runs[0])

    def _get_latest_hypothesis_ranking_run_context(self) -> HypothesisRankingRunContext | None:
        latest_runs = list_hypothesis_ranking_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_hypothesis_ranking_run_context(latest_runs[0])

    def _get_latest_planner_run_context(self) -> PlannerRunContext | None:
        latest_runs = list_planner_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_planner_run_context(latest_runs[0])

    def _get_latest_router_run_context(self) -> RouterRunContext | None:
        latest_runs = list_router_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_router_run_context(latest_runs[0])

    def _get_latest_worker_run_context(self) -> WorkerRunContext | None:
        latest_runs = list_worker_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_worker_run_context(latest_runs[0])

    def _get_latest_aggregation_run_context(self) -> AggregationRunContext | None:
        latest_runs = list_aggregation_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_aggregation_run_context(latest_runs[0])

    def _get_latest_state_manager_run_context(self) -> StateManagerRunContext | None:
        latest_runs = list_state_manager_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_state_manager_run_context(latest_runs[0])

    def _get_latest_critic_run_context(self) -> CriticRunContext | None:
        latest_runs = list_critic_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_critic_run_context(latest_runs[0])

    def _get_latest_final_batch_auditor_run_context(self) -> FinalBatchAuditorRunContext | None:
        latest_runs = list_final_batch_auditor_run_dirs(limit=1)
        if not latest_runs:
            return None
        return self._load_final_batch_auditor_run_context(latest_runs[0])

    def _get_latest_phase3a_runtime_run_context(self) -> Phase3ARuntimeRunContext | None:
        latest_runs = list_phase3a_runtime_run_dirs()
        if not latest_runs:
            return None

        for run_dir in latest_runs:
            try:
                return self._load_phase3a_runtime_run_context(run_dir)
            except (FileNotFoundError, KeyError, OSError, ValueError):
                # Skip incomplete/invalid runtime dirs created by aborted runs.
                continue
        return None

    def _resolve_component_run_dir(self, component_run_path: str) -> Path | None:
        raw_path = str(component_run_path or "").strip()
        if not raw_path:
            return None

        path = Path(raw_path)
        if path.suffix.lower() == ".json":
            return path.parent
        return path

    def _load_json_if_available(self, artifact_path: str) -> dict[str, Any]:
        raw_path = str(artifact_path or "").strip()
        if not raw_path:
            return {}

        path = Path(raw_path)
        if not path.is_file():
            return {}

        payload = load_json(path)
        if isinstance(payload, dict):
            return payload
        return {"value": payload}

    def _load_optional_component_context(
        self,
        component_run_path: str,
        loader: Callable[[Path], Any],
    ) -> Any | None:
        run_dir = self._resolve_component_run_dir(component_run_path)
        if run_dir is None:
            return None
        try:
            return loader(run_dir)
        except Exception:
            return None

    def _build_phase3a_runtime_round_context(
        self,
        round_manifest: dict[str, Any],
    ) -> Phase3ARuntimeRoundContext:
        global_aggregation_summary = dict(
            round_manifest.get("global_aggregation_summary", {}) or {})
        global_aggregation_path = str(round_manifest.get(
            "global_aggregation_path", "") or "").strip()
        if global_aggregation_path:
            try:
                global_aggregation_summary = load_inter_hypothesis_bundle(
                    Path(global_aggregation_path).parent
                )
            except Exception:
                global_aggregation_summary = self._load_json_if_available(
                    global_aggregation_path
                )
        if not global_aggregation_summary:
            global_aggregation_summary = self._load_json_if_available(
                global_aggregation_path
            )
        frozen_snapshot = self._load_json_if_available(
            str(round_manifest.get("frozen_snapshot_path", "")))
        if not frozen_snapshot:
            frozen_snapshot = dict(
                round_manifest.get("frozen_snapshot", {}) or {})
        return Phase3ARuntimeRoundContext(
            round_manifest=dict(round_manifest),
            frozen_snapshot=frozen_snapshot,
            global_aggregation_summary=global_aggregation_summary,
            analysis_run=self._load_optional_component_context(
                str(round_manifest.get("analysis_run_path", "")),
                self._load_investigation_analysis_run_context,
            ),
            ranking_run=self._load_optional_component_context(
                str(round_manifest.get("ranking_run_path", "")),
                self._load_hypothesis_ranking_run_context,
            ),
            planner_run=self._load_optional_component_context(
                str(round_manifest.get("planner_run_path", "")),
                self._load_planner_run_context,
            ),
            critic_run=self._load_optional_component_context(
                str(round_manifest.get("critic_run_path", "")),
                self._load_critic_run_context,
            ),
        )

    def _build_phase3a_hypothesis_lineage_context(
        self,
        hypothesis_record: dict[str, Any],
    ) -> Phase3AHypothesisLineageContext:
        worker_runs: list[WorkerRunContext] = []
        for worker_run_path in list(hypothesis_record.get("worker_run_paths", [])):
            worker_context = self._load_optional_component_context(
                str(worker_run_path),
                self._load_worker_run_context,
            )
            if worker_context is not None:
                worker_runs.append(worker_context)

        return Phase3AHypothesisLineageContext(
            hypothesis_record=dict(hypothesis_record),
            router_run=self._load_optional_component_context(
                str(hypothesis_record.get("router_run_path", "")),
                self._load_router_run_context,
            ),
            worker_runs=worker_runs,
            aggregation_run=self._load_optional_component_context(
                str(hypothesis_record.get("aggregation_run_path", "")),
                self._load_aggregation_run_context,
            ),
            state_manager_run=self._load_optional_component_context(
                str(hypothesis_record.get("state_manager_run_path", "")),
                self._load_state_manager_run_context,
            ),
        )

    def _get_latest_matching_state_manager_run_context(
        self,
        batch_id: str,
    ) -> StateManagerRunContext | None:
        for run_dir in list_state_manager_run_dirs():
            try:
                run_context = self._load_state_manager_run_context(run_dir)
            except Exception:
                continue
            if str(run_context.component_run.get("batch_id") or "") == batch_id and run_context.updated_batch_state:
                return run_context
        return None

    def _get_latest_matching_investigation_analysis_run_context(
        self,
        batch_id: str,
    ) -> InvestigationAnalysisRunContext | None:
        for run_dir in list_investigation_analysis_run_dirs():
            try:
                run_context = self._load_investigation_analysis_run_context(
                    run_dir)
            except Exception:
                continue
            if str(run_context.component_run.get("batch_id") or "") == batch_id:
                return run_context
        return None

    def _load_tool_run_context(self, run_dir: Path) -> ToolRunContext:
        bundle = load_tool_run_bundle(run_dir)
        return ToolRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            tool_call_request=dict(bundle.get("tool_call_request", {})),
            tool_capability_record=dict(
                bundle.get("tool_capability_record", {})),
            normalized_inputs=dict(bundle.get("normalized_inputs", {})),
            raw_tool_output=dict(bundle.get("raw_tool_output", {})),
            parsed_output=dict(bundle.get("parsed_output", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            tool_metrics=dict(bundle.get("tool_metrics", {})),
            cache_record=dict(bundle.get("cache_record", {})
                              ) if bundle.get("cache_record") else None,
        )

    def _load_semantic_extraction_run_context(self, run_dir: Path) -> SemanticExtractionRunContext:
        bundle = load_semantic_extraction_bundle(run_dir)
        return SemanticExtractionRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            overview_summary_min=dict(bundle.get("overview_summary_min", {})),
            partition_context=dict(bundle.get("partition_context", {})),
            projected_evidence=dict(bundle.get("projected_evidence", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            parsed_output=dict(bundle.get("parsed_output", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_investigation_analysis_run_context(
        self,
        run_dir: Path,
    ) -> InvestigationAnalysisRunContext:
        bundle = load_investigation_analysis_bundle(run_dir)
        return InvestigationAnalysisRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            semantic_substrate_input=dict(
                bundle.get("semantic_substrate", {})),
            analysis_context_min=dict(bundle.get("analysis_context_min", {})),
            analysis_iteration_context_min=dict(
                bundle.get("analysis_iteration_context_min", {})),
            projected_substrate=dict(bundle.get("projected_substrate", {})),
            projected_analysis_context=dict(
                bundle.get("projected_analysis_context", {})),
            projected_iteration_context=dict(
                bundle.get("projected_iteration_context", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            parsed_output=dict(bundle.get("parsed_output", {})),
            hypothesis_index=dict(bundle.get("hypothesis_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_hypothesis_ranking_run_context(
        self,
        run_dir: Path,
    ) -> HypothesisRankingRunContext:
        bundle = load_hypothesis_ranking_bundle(run_dir)
        return HypothesisRankingRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            candidate_hypotheses=dict(bundle.get("candidate_hypotheses", {})),
            ranking_state_snapshot=dict(
                bundle.get("ranking_state_snapshot", {})),
            projected_candidate_context=dict(
                bundle.get("projected_candidate_context", {})),
            projected_ranking_state=dict(
                bundle.get("projected_ranking_state", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            parsed_output=dict(bundle.get("parsed_output", {})),
            selection_index=dict(bundle.get("selection_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_planner_run_context(
        self,
        run_dir: Path,
    ) -> PlannerRunContext:
        bundle = load_planner_bundle(run_dir)
        return PlannerRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            ranking_decision_min=dict(bundle.get("ranking_decision_min", {})),
            selected_hypothesis_context=dict(
                bundle.get("selected_hypothesis_context", {})),
            planner_round_context=dict(
                bundle.get("planner_round_context", {})),
            projected_selected_context=dict(
                bundle.get("projected_selected_context", {})),
            projected_planner_round_context=dict(
                bundle.get("projected_planner_round_context", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            parsed_output=dict(bundle.get("parsed_output", {})),
            strategy_index=dict(bundle.get("strategy_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_router_run_context(
        self,
        run_dir: Path,
    ) -> RouterRunContext:
        bundle = load_router_bundle(run_dir)
        return RouterRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            planner_strategy=dict(bundle.get("planner_strategy", {})),
            router_context_min=dict(bundle.get("router_context_min", {})),
            reduced_context=dict(bundle.get("reduced_context", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            parsed_output=dict(bundle.get("parsed_output", {})),
            task_bundle_index=dict(bundle.get("task_bundle_index", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_worker_run_context(
        self,
        run_dir: Path,
    ) -> WorkerRunContext:
        bundle = load_worker_bundle(run_dir)
        return WorkerRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            worker_task=dict(bundle.get("worker_task", {})),
            worker_runtime_refs=dict(bundle.get("worker_runtime_refs", {})),
            prompt_snapshots=list(bundle.get("prompt_snapshots", [])),
            raw_model_responses=list(bundle.get("raw_model_responses", [])),
            parsed_steps=list(bundle.get("parsed_steps", [])),
            tool_events=list(bundle.get("tool_events", [])),
            retry_events=list(bundle.get("retry_events", [])),
            failure_events=list(bundle.get("failure_events", [])),
            worker_result=dict(bundle.get("worker_result", {})),
            worker_output=dict(bundle.get("worker_output", {})),
            operational_trace=dict(bundle.get("operational_trace", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_aggregation_run_context(
        self,
        run_dir: Path,
    ) -> AggregationRunContext:
        bundle = load_aggregation_bundle(run_dir)
        return AggregationRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            worker_result_set=dict(bundle.get("worker_result_set", {})),
            normalized_inputs=dict(bundle.get("normalized_inputs", {})),
            overlap_diagnostics=list(bundle.get("overlap_diagnostics", [])),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            parsed_output=dict(bundle.get("parsed_output", {})),
            aggregation_handoff=dict(bundle.get("aggregation_handoff", {})),
            repair_attempts=list(bundle.get("repair_attempts", [])),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_state_manager_run_context(
        self,
        run_dir: Path,
    ) -> StateManagerRunContext:
        bundle = load_state_manager_bundle(run_dir)
        return StateManagerRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            prior_state=dict(bundle.get("prior_state", {})),
            aggregation_handoff=dict(bundle.get("aggregation_handoff", {})),
            state_manager_context=dict(
                bundle.get("state_manager_context", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            state_delta_record=dict(bundle.get("state_delta_record", {})),
            updated_batch_state=dict(bundle.get("updated_batch_state", {})),
            state_update_result=dict(bundle.get("state_update_result", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_critic_run_context(
        self,
        run_dir: Path,
    ) -> CriticRunContext:
        bundle = load_critic_bundle(run_dir)
        return CriticRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            critic_input_min=dict(bundle.get("critic_input_min", {})),
            refined_state_summary=dict(
                bundle.get("refined_state_summary", {})),
            module_behavior_summaries=list(
                bundle.get("module_behavior_summaries", [])),
            process_signal_summary=dict(
                bundle.get("process_signal_summary", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            critic_observations_payload=dict(
                bundle.get("critic_observations", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_final_batch_auditor_run_context(
        self,
        run_dir: Path,
    ) -> FinalBatchAuditorRunContext:
        bundle = load_final_batch_auditor_bundle(run_dir)
        return FinalBatchAuditorRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=dict(bundle.get("component_run", {})),
            final_audit_input=dict(bundle.get("final_audit_input", {})),
            final_state_summary=dict(bundle.get("final_state_summary", {})),
            round_history_summary=list(
                bundle.get("round_history_summary", [])),
            process_signal_summary=dict(
                bundle.get("process_signal_summary", {})),
            prompt_text=str(bundle.get("rendered_prompt", "")),
            raw_response_text=str(bundle.get("raw_response", "")),
            debugging_audit_report=dict(
                bundle.get("debugging_audit_report", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _load_phase3a_runtime_run_context(
        self,
        run_dir: Path,
    ) -> Phase3ARuntimeRunContext:
        bundle = load_phase3a_runtime_bundle(run_dir)
        batch_ledger = bundle.get("batch_ledger")
        batch_ledger_payload = batch_ledger.to_dict() if hasattr(
            batch_ledger, "to_dict") else dict(batch_ledger or {})
        synthesized_round_manifests = []
        if not list(batch_ledger_payload.get("round_manifests", []) or []):
            synthesized_round_manifests = self._synthesize_phase3a_runtime_round_manifests(
                bundle=bundle,
                batch_ledger_payload=batch_ledger_payload,
            )
            if synthesized_round_manifests:
                batch_ledger_payload["round_manifests"] = synthesized_round_manifests
        component_run = dict(bundle.get("component_run", {}))
        runtime_summary = dict(bundle.get("runtime_summary", {}))
        runtime_metrics = dict(bundle.get("runtime_metrics", {}))
        recovered_round_count = len(
            list(batch_ledger_payload.get("round_manifests", []) or []))
        if recovered_round_count and not int(component_run.get("round_count", 0) or 0):
            component_run["round_count"] = recovered_round_count
        if recovered_round_count and not int(runtime_summary.get("round_count", 0) or 0):
            runtime_summary["round_count"] = recovered_round_count
        if recovered_round_count and not int(runtime_metrics.get("round_count", 0) or 0):
            runtime_metrics["round_count"] = recovered_round_count
        finalization_summary = dict(bundle.get("finalization_summary", {}))
        finalization_payload = dict(
            batch_ledger_payload.get("finalization", {}))

        return Phase3ARuntimeRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            batch_ledger=batch_ledger_payload,
            initial_runtime_context=dict(
                bundle.get("initial_runtime_context", {})),
            initial_state=dict(bundle.get("initial_state", {})),
            finalization_summary=finalization_summary,
            runtime_metrics=runtime_metrics,
            runtime_summary=runtime_summary,
            run_manifest=dict(bundle.get("run_manifest", {})),
            event_stream=list(bundle.get("event_stream", [])),
            terminal_log_text=str(bundle.get("terminal_log_text", "")),
            semantic_extraction_run=self._load_optional_component_context(
                str(batch_ledger_payload.get("semantic_extraction_run_path", "")),
                self._load_semantic_extraction_run_context,
            ),
            final_batch_auditor_run=self._load_optional_component_context(
                str(
                    finalization_summary.get("final_batch_auditor_run_path")
                    or finalization_payload.get("final_batch_auditor_run_path", "")
                ),
                self._load_final_batch_auditor_run_context,
            ),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _collect_phase3a_runtime_round_ids(
        self,
        batch_id: str,
        event_stream: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        round_ids: set[str] = set()

        if event_stream:
            for event in event_stream:
                payload = dict(event.get("payload", {}) or {})
                ids = dict(payload.get("ids", {}) or {})
                normalized_round_id = str(
                    payload.get("round_id") or ids.get("round_id") or ""
                ).strip()
                if normalized_round_id:
                    round_ids.add(normalized_round_id)

        component_scans = [
            (list_router_run_dirs, load_router_bundle),
            (list_hypothesis_ranking_run_dirs, load_hypothesis_ranking_bundle),
            (list_planner_run_dirs, load_planner_bundle),
            (list_worker_run_dirs, load_worker_bundle),
            (list_aggregation_run_dirs, load_aggregation_bundle),
            (list_state_manager_run_dirs, load_state_manager_bundle),
            (list_critic_run_dirs, load_critic_bundle),
        ]

        for list_dirs_fn, load_bundle_fn in component_scans:
            for run_dir in list_dirs_fn():
                try:
                    bundle = load_bundle_fn(run_dir)
                except Exception:
                    continue
                component_run = dict(bundle.get("component_run", {}) or {})
                if str(component_run.get("batch_id") or "").strip() != batch_id:
                    continue
                normalized_round_id = str(
                    component_run.get("round_id") or "").strip()
                if normalized_round_id:
                    round_ids.add(normalized_round_id)

        return sorted(round_ids)

    def _synthesize_phase3a_runtime_round_manifests(
        self,
        *,
        bundle: dict[str, Any],
        batch_ledger_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        component_run = dict(bundle.get("component_run", {}) or {})
        batch_id = str(
            component_run.get("batch_id")
            or batch_ledger_payload.get("batch_id")
            or ""
        ).strip()
        if not batch_id:
            return []

        round_ids = self._collect_phase3a_runtime_round_ids(
            batch_id,
            list(bundle.get("event_stream", []) or []),
        )
        if not round_ids:
            return []

        artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
        run_dir_text = str(artifact_paths.get("run_dir", "") or "").strip()
        run_dir = Path(run_dir_text) if run_dir_text else None

        analysis_run_path = str(
            batch_ledger_payload.get(
                "initial_investigation_analysis_run_path", "") or ""
        ).strip()
        initial_hypothesis_set: dict[str, Any] = {}
        if analysis_run_path:
            try:
                analysis_bundle = load_investigation_analysis_bundle(
                    Path(analysis_run_path).parent
                )
                initial_hypothesis_set = dict(
                    analysis_bundle.get("parsed_output", {})
                    or analysis_bundle.get("hypothesis_set", {})
                    or {}
                )
            except Exception:
                initial_hypothesis_set = {}

        initial_state = dict(bundle.get("initial_state", {}) or {})
        initial_state_version = int(
            initial_state.get("state_version")
            or batch_ledger_payload.get("initial_state_version", 0)
            or 0
        )
        analysis_mode = str(
            component_run.get("analysis_mode")
            or batch_ledger_payload.get("analysis_mode")
            or "initial"
        )
        final_terminal_reason = str(
            batch_ledger_payload.get("finalization", {}).get(
                "terminal_reason", "")
            or component_run.get("terminal_reason", "")
            or ""
        ).strip()

        def _matching_inter_hypothesis_bundles(round_id: str) -> list[dict[str, Any]]:
            runs_dir = DEFAULT_INTER_HYPOTHESIS_DIR
            if not runs_dir.exists():
                return []

            matches: list[dict[str, Any]] = []
            run_dirs = [
                path for path in runs_dir.iterdir()
                if path.is_dir()
            ]
            run_dirs.sort(key=lambda path: path.name, reverse=True)
            for run_dir_candidate in run_dirs:
                try:
                    candidate_bundle = load_inter_hypothesis_bundle(
                        run_dir_candidate)
                except Exception:
                    continue
                candidate_run = dict(
                    candidate_bundle.get("component_run", {}) or {})
                if str(candidate_run.get("batch_id") or "").strip() != batch_id:
                    continue
                if str(candidate_run.get("round_id") or "").strip() != round_id:
                    continue
                matches.append(candidate_bundle)
            return matches

        def _matching_bundles(
            list_dirs_fn: Callable[..., list[Path]],
            load_bundle_fn: Callable[[Path], dict[str, Any]],
            *,
            round_id: str,
            hypothesis_id: str | None = None,
            task_id: str | None = None,
        ) -> list[dict[str, Any]]:
            matches: list[dict[str, Any]] = []
            for run_dir_candidate in list_dirs_fn():
                try:
                    candidate_bundle = load_bundle_fn(run_dir_candidate)
                except Exception:
                    continue
                candidate_run = dict(
                    candidate_bundle.get("component_run", {}) or {})
                if str(candidate_run.get("batch_id") or "").strip() != batch_id:
                    continue
                if str(candidate_run.get("round_id") or "").strip() != round_id:
                    continue
                if hypothesis_id is not None and str(candidate_run.get("hypothesis_id") or "").strip() != hypothesis_id:
                    continue
                if task_id is not None and str(candidate_run.get("task_id") or "").strip() != task_id:
                    continue
                matches.append(candidate_bundle)
            return matches

        def _bundle_path(candidate_bundle: dict[str, Any] | None, key: str) -> str:
            if not candidate_bundle:
                return ""
            artifact_path = dict(candidate_bundle.get(
                "artifact_paths", {}) or {})
            return str(artifact_path.get(key, "") or "").strip()

        recovered_round_manifests: list[dict[str, Any]] = []
        for fallback_index, round_id in enumerate(round_ids, start=1):
            round_index_match = re.search(r"(\d+)$", round_id)
            round_index = int(round_index_match.group(
                1)) if round_index_match else fallback_index

            ranking_bundles = _matching_bundles(
                list_hypothesis_ranking_run_dirs,
                load_hypothesis_ranking_bundle,
                round_id=round_id,
            )
            planner_bundles = _matching_bundles(
                list_planner_run_dirs,
                load_planner_bundle,
                round_id=round_id,
            )
            critic_bundles = _matching_bundles(
                list_critic_run_dirs,
                load_critic_bundle,
                round_id=round_id,
            )
            router_bundles = _matching_bundles(
                list_router_run_dirs,
                load_router_bundle,
                round_id=round_id,
            )
            aggregation_bundles = _matching_bundles(
                list_aggregation_run_dirs,
                load_aggregation_bundle,
                round_id=round_id,
            )
            state_manager_bundles = _matching_bundles(
                list_state_manager_run_dirs,
                load_state_manager_bundle,
                round_id=round_id,
            )
            worker_bundles = _matching_bundles(
                list_worker_run_dirs,
                load_worker_bundle,
                round_id=round_id,
            )

            ranking_bundle = ranking_bundles[0] if ranking_bundles else {}
            planner_bundle = planner_bundles[0] if planner_bundles else {}
            critic_bundle = critic_bundles[0] if critic_bundles else {}
            global_aggregation_bundles = _matching_inter_hypothesis_bundles(
                round_id)
            global_aggregation_bundle = (
                global_aggregation_bundles[0]
                if global_aggregation_bundles
                else {}
            )

            ranking_output = dict(
                ranking_bundle.get("parsed_output", {})
                or ranking_bundle.get("ranking_decision", {})
                or {}
            )
            selected_hypothesis_ids = [
                str(item).strip()
                for item in list(ranking_output.get("selected_hypothesis_ids", []) or [])
                if str(item).strip()
            ]
            deferred_hypothesis_ids = [
                str(item).strip()
                for item in list(ranking_output.get("deferred_hypothesis_ids", []) or [])
                if str(item).strip()
            ]

            planner_strategies = [
                dict(item)
                for item in list(dict(planner_bundle.get("parsed_output", {}) or {}).get("planner_strategies", []) or [])
                if isinstance(item, dict)
            ]
            ordered_hypothesis_ids = [
                str(item.get("hypothesis_id") or "").strip()
                for item in planner_strategies
                if str(item.get("hypothesis_id") or "").strip()
            ]

            router_by_hypothesis_id: dict[str, dict[str, Any]] = {}
            for router_bundle in router_bundles:
                router_run = dict(router_bundle.get("component_run", {}) or {})
                hypothesis_id = str(router_run.get(
                    "hypothesis_id") or "").strip()
                if hypothesis_id and hypothesis_id not in router_by_hypothesis_id:
                    router_by_hypothesis_id[hypothesis_id] = router_bundle
                if hypothesis_id and hypothesis_id not in ordered_hypothesis_ids:
                    ordered_hypothesis_ids.append(hypothesis_id)

            aggregation_by_hypothesis_id: dict[str, dict[str, Any]] = {}
            for aggregation_bundle in aggregation_bundles:
                aggregation_run = dict(
                    aggregation_bundle.get("component_run", {}) or {})
                hypothesis_id = str(aggregation_run.get(
                    "hypothesis_id") or "").strip()
                if hypothesis_id and hypothesis_id not in aggregation_by_hypothesis_id:
                    aggregation_by_hypothesis_id[hypothesis_id] = aggregation_bundle
                if hypothesis_id and hypothesis_id not in ordered_hypothesis_ids:
                    ordered_hypothesis_ids.append(hypothesis_id)

            state_manager_by_hypothesis_id: dict[str, dict[str, Any]] = {}
            for state_manager_bundle in state_manager_bundles:
                state_manager_run = dict(
                    state_manager_bundle.get("component_run", {}) or {})
                hypothesis_id = str(state_manager_run.get(
                    "hypothesis_id") or "").strip()
                if hypothesis_id and hypothesis_id not in state_manager_by_hypothesis_id:
                    state_manager_by_hypothesis_id[hypothesis_id] = state_manager_bundle
                if hypothesis_id and hypothesis_id not in ordered_hypothesis_ids:
                    ordered_hypothesis_ids.append(hypothesis_id)

            worker_bundle_index: dict[tuple[str, str], dict[str, Any]] = {}
            for worker_bundle in worker_bundles:
                worker_run = dict(worker_bundle.get("component_run", {}) or {})
                hypothesis_id = str(worker_run.get(
                    "hypothesis_id") or "").strip()
                task_id = str(worker_run.get("task_id") or "").strip()
                if hypothesis_id and task_id and (hypothesis_id, task_id) not in worker_bundle_index:
                    worker_bundle_index[(
                        hypothesis_id, task_id)] = worker_bundle

            if not ordered_hypothesis_ids:
                ordered_hypothesis_ids = sorted(set(
                    list(router_by_hypothesis_id.keys())
                    + list(aggregation_by_hypothesis_id.keys())
                    + list(state_manager_by_hypothesis_id.keys())
                ))

            round_hypothesis_runs: list[dict[str, Any]] = []
            for hypothesis_id in ordered_hypothesis_ids:
                router_bundle = router_by_hypothesis_id.get(hypothesis_id, {})
                router_run = dict(router_bundle.get("component_run", {}) or {})
                router_output = dict(
                    router_bundle.get("parsed_output", {}) or {})
                task_ids = [
                    str(item.get("task_id") or "").strip()
                    for item in list(router_output.get("worker_tasks", []) or [])
                    if isinstance(item, dict) and str(item.get("task_id") or "").strip()
                ]
                worker_run_paths: list[str] = []
                for task_id in task_ids:
                    worker_path = _bundle_path(
                        worker_bundle_index.get((hypothesis_id, task_id)),
                        "component_run_path",
                    )
                    if worker_path and worker_path not in worker_run_paths:
                        worker_run_paths.append(worker_path)

                aggregation_bundle = aggregation_by_hypothesis_id.get(
                    hypothesis_id, {})
                aggregation_run = dict(
                    aggregation_bundle.get("component_run", {}) or {})
                state_manager_bundle = state_manager_by_hypothesis_id.get(
                    hypothesis_id, {})
                state_manager_run = dict(
                    state_manager_bundle.get("component_run", {}) or {})
                prior_state = dict(
                    state_manager_bundle.get("prior_state", {}) or {})
                updated_batch_state = dict(
                    state_manager_bundle.get("updated_batch_state", {}) or {})
                state_delta_record = dict(
                    state_manager_bundle.get("state_delta_record", {}) or {})
                start_state_version = int(
                    prior_state.get("state_version")
                    or state_manager_run.get("expected_prior_state_version")
                    or initial_state_version
                    or 0
                )
                end_state_version = int(
                    updated_batch_state.get("state_version")
                    or state_delta_record.get("state_version")
                    or state_manager_run.get("state_version")
                    or start_state_version
                )
                planner_strategy_id = str(
                    router_run.get("planner_strategy_id")
                    or next(
                        (
                            str(item.get("strategy_id") or "").strip()
                            for item in planner_strategies
                            if str(item.get("hypothesis_id") or "").strip() == hypothesis_id
                        ),
                        "",
                    )
                ).strip()

                round_hypothesis_runs.append(
                    {
                        "hypothesis_id": hypothesis_id,
                        "planner_strategy_id": planner_strategy_id,
                        "router_run_path": _bundle_path(router_bundle, "component_run_path"),
                        "task_ids": task_ids,
                        "worker_run_paths": worker_run_paths,
                        "aggregation_run_path": _bundle_path(aggregation_bundle, "component_run_path"),
                        "state_manager_run_path": _bundle_path(state_manager_bundle, "component_run_path"),
                        "start_state_version": start_state_version,
                        "end_state_version": end_state_version,
                        "status": str(
                            state_manager_run.get("status")
                            or aggregation_run.get("status")
                            or router_run.get("status")
                            or component_run.get("status")
                            or "pending"
                        ),
                    }
                )

            frozen_snapshot = build_round_snapshot(
                batch_id=batch_id,
                round_id=round_id,
                round_index=round_index,
                analysis_mode=analysis_mode,
                canonical_batch_state=initial_state,
                initial_hypothesis_set=initial_hypothesis_set,
            )

            recovered_round_manifests.append(
                {
                    "round_id": round_id,
                    "round_index": round_index,
                    "analysis_mode": analysis_mode,
                    "analysis_run_path": analysis_run_path,
                    "frozen_snapshot_path": str(
                        run_dir / "round_manifests" /
                        f"{round_id}_snapshot.json"
                        if run_dir is not None
                        else ""
                    ),
                    "frozen_snapshot": frozen_snapshot,
                    "global_aggregation_path": _bundle_path(
                        global_aggregation_bundle,
                        "parsed_output_path",
                    ),
                    "ranking_run_path": _bundle_path(ranking_bundle, "component_run_path"),
                    "planner_run_path": _bundle_path(planner_bundle, "component_run_path"),
                    "selected_hypothesis_ids": selected_hypothesis_ids,
                    "deferred_hypothesis_ids": deferred_hypothesis_ids,
                    "start_state_version": initial_state_version,
                    "end_state_version": int(
                        round_hypothesis_runs[-1]["end_state_version"]
                        if round_hypothesis_runs
                        else initial_state_version
                    ),
                    "status": str(
                        state_manager_bundles[0].get(
                            "component_run", {}).get("status")
                        if state_manager_bundles
                        else component_run.get("status")
                        or batch_ledger_payload.get("status")
                        or "pending"
                    ),
                    "terminal_reason": final_terminal_reason,
                    "critic_run_path": _bundle_path(critic_bundle, "component_run_path"),
                    "hypothesis_runs": round_hypothesis_runs,
                }
            )

        return recovered_round_manifests

    def _build_worker_run_context(
        self,
        bundle: dict[str, Any],
    ) -> WorkerRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return WorkerRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            worker_task=dict(bundle.get("worker_task", {})),
            worker_runtime_refs=dict(bundle.get("worker_runtime_refs", {})),
            prompt_snapshots=list(bundle.get("prompt_snapshots", [])),
            raw_model_responses=list(bundle.get("raw_model_responses", [])),
            parsed_steps=list(bundle.get("parsed_steps", [])),
            tool_events=list(bundle.get("tool_events", [])),
            retry_events=list(bundle.get("retry_events", [])),
            failure_events=list(bundle.get("failure_events", [])),
            worker_result=dict(bundle.get("worker_result", {})),
            worker_output=dict(bundle.get("worker_output", {})),
            operational_trace=dict(bundle.get("operational_trace", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_aggregation_run_context(
        self,
        bundle: dict[str, Any],
    ) -> AggregationRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return AggregationRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            worker_result_set=dict(bundle.get("worker_result_set", {})),
            normalized_inputs=dict(bundle.get("normalized_inputs", {})),
            overlap_diagnostics=list(bundle.get("overlap_diagnostics", [])),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            parsed_output=dict(bundle.get("parsed_output", {})),
            aggregation_handoff=dict(bundle.get("aggregation_handoff", {})),
            repair_attempts=list(bundle.get("repair_attempts", [])),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_state_manager_run_context(
        self,
        bundle: dict[str, Any],
    ) -> StateManagerRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return StateManagerRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            prior_state=dict(bundle.get("prior_state", {})),
            aggregation_handoff=dict(bundle.get("aggregation_handoff", {})),
            state_manager_context=dict(
                bundle.get("state_manager_context", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            state_delta_record=dict(bundle.get("state_delta_record", {})),
            updated_batch_state=dict(bundle.get("updated_batch_state", {})),
            state_update_result=dict(bundle.get("state_update_result", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_critic_run_context(
        self,
        bundle: dict[str, Any],
    ) -> CriticRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return CriticRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            critic_input_min=dict(bundle.get("critic_input_min", {})),
            refined_state_summary=dict(
                bundle.get("refined_state_summary", {})),
            module_behavior_summaries=list(
                bundle.get("module_behavior_summaries", [])),
            process_signal_summary=dict(
                bundle.get("process_signal_summary", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            critic_observations_payload=dict(
                bundle.get("critic_observations", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_final_batch_auditor_run_context(
        self,
        bundle: dict[str, Any],
    ) -> FinalBatchAuditorRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        return FinalBatchAuditorRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            final_audit_input=dict(bundle.get("final_audit_input", {})),
            final_state_summary=dict(bundle.get("final_state_summary", {})),
            round_history_summary=list(
                bundle.get("round_history_summary", [])),
            process_signal_summary=dict(
                bundle.get("process_signal_summary", {})),
            prompt_text=str(bundle.get("prompt_text", "")),
            raw_response_text=str(bundle.get("raw_response_text", "")),
            debugging_audit_report=dict(
                bundle.get("debugging_audit_report", {})),
            validation_report=dict(bundle.get("validation_report", {})),
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_phase3a_runtime_run_context(
        self,
        bundle: dict[str, Any],
    ) -> Phase3ARuntimeRunContext:
        component_run = dict(bundle.get("component_run", {}))
        if not component_run and bundle.get("artifact_paths", {}).get("component_run_path"):
            component_run = load_json(
                bundle["artifact_paths"]["component_run_path"])

        batch_ledger = bundle.get("batch_ledger")
        batch_ledger_payload = batch_ledger.to_dict() if hasattr(
            batch_ledger, "to_dict") else dict(batch_ledger or {})
        finalization_summary = dict(bundle.get("finalization_summary", {}))
        finalization_payload = dict(
            batch_ledger_payload.get("finalization", {}))

        return Phase3ARuntimeRunContext(
            artifact_paths=dict(bundle.get("artifact_paths", {})),
            component_run=component_run,
            batch_ledger=batch_ledger_payload,
            initial_runtime_context=dict(
                bundle.get("initial_runtime_context", {})),
            initial_state=dict(bundle.get("initial_state", {})),
            finalization_summary=finalization_summary,
            runtime_metrics=dict(bundle.get("runtime_metrics", {})),
            runtime_summary=dict(bundle.get("runtime_summary", {})),
            semantic_extraction_run=self._load_optional_component_context(
                str(batch_ledger_payload.get("semantic_extraction_run_path", "")),
                self._load_semantic_extraction_run_context,
            ),
            final_batch_auditor_run=self._load_optional_component_context(
                str(
                    finalization_summary.get("final_batch_auditor_run_path")
                    or finalization_payload.get("final_batch_auditor_run_path", "")
                ),
                self._load_final_batch_auditor_run_context,
            ),
            replay_metadata=dict(bundle.get("replay_metadata", {})) if bundle.get(
                "replay_metadata") else None,
        )

    def _build_worker_prompt_response_text(
        self,
        run_context: WorkerRunContext,
    ) -> str:
        lines: list[str] = []
        for index, prompt_snapshot in enumerate(run_context.prompt_snapshots):
            response_payload = run_context.raw_model_responses[index] if index < len(
                run_context.raw_model_responses) else {}
            step_index = prompt_snapshot.get("step_index", "?")
            attempt_index = prompt_snapshot.get("attempt_index", "?")
            lines.extend(
                [
                    f"=== STEP {step_index} ATTEMPT {attempt_index} PROMPT ===",
                    "",
                    str(prompt_snapshot.get("prompt_text", "")),
                    "",
                    f"=== STEP {step_index} ATTEMPT {attempt_index} RESPONSE ===",
                    "",
                    str(response_payload.get("raw_response_text", "")),
                    "",
                ]
            )
        return "\n".join(lines).strip()

    def _build_aggregation_prompt_response_text(
        self,
        run_context: AggregationRunContext,
    ) -> str:
        lines = [
            "=== AGGREGATION PROMPT ===",
            "",
            run_context.prompt_text,
            "",
            "=== RAW RESPONSE ===",
            "",
            run_context.raw_response_text,
        ]
        return "\n".join(lines).strip()

    def _build_state_manager_prompt_response_text(
        self,
        run_context: StateManagerRunContext,
    ) -> str:
        lines = [
            "=== STATE MANAGER PROMPT ===",
            "",
            run_context.prompt_text,
            "",
            "=== RAW RESPONSE ===",
            "",
            run_context.raw_response_text,
        ]
        return "\n".join(lines).strip()

    def _build_critic_prompt_response_text(
        self,
        run_context: CriticRunContext,
    ) -> str:
        lines = [
            "=== CRITIC PROMPT ===",
            "",
            run_context.prompt_text,
            "",
            "=== RAW RESPONSE ===",
            "",
            run_context.raw_response_text,
        ]
        return "\n".join(lines).strip()

    def _build_final_batch_auditor_prompt_response_text(
        self,
        run_context: FinalBatchAuditorRunContext,
    ) -> str:
        lines = [
            "=== PROMPT ===",
            "",
            run_context.prompt_text,
            "",
            "=== RAW RESPONSE ===",
            "",
            run_context.raw_response_text,
        ]
        return "\n".join(lines).strip()

    def _preview_text(
        self,
        value: Any,
        *,
        limit: int = 120,
    ) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text or "none"
        return f"{text[: limit - 3].rstrip()}..."

    def _build_worker_step_traces(
        self,
        run_context: WorkerRunContext,
    ) -> list[WorkerStepTrace]:
        return build_worker_step_traces(
            prompt_snapshots=run_context.prompt_snapshots,
            raw_model_responses=run_context.raw_model_responses,
            parsed_steps=run_context.parsed_steps,
            tool_events=run_context.tool_events,
            retry_events=run_context.retry_events,
            failure_events=run_context.failure_events,
        )

    def _get_worker_result_payload(
        self,
        run_context: WorkerRunContext,
    ) -> dict[str, Any]:
        worker_result = dict(run_context.worker_result)
        if worker_result:
            return worker_result
        return dict(run_context.worker_output.get("worker_result", {}))

    def _build_worker_latest_step_lines(
        self,
        run_context: WorkerRunContext,
    ) -> list[str]:
        step_traces = self._build_worker_step_traces(run_context)
        if not step_traces:
            return ["No persisted step trace is available for this Worker run."]

        latest_step = step_traces[-1]
        worker_result = self._get_worker_result_payload(run_context)
        lines = [
            f"step={latest_step.step_index} | mode={latest_step.step_mode} | decision={latest_step.decision or 'unknown'} | attempts={len(latest_step.attempts)}",
            f"proposed_actions={len(latest_step.proposed_actions)} | executed_actions={len(latest_step.executed_actions)} | flags={len(latest_step.flags)}",
            f"reasoning: {self._preview_text(latest_step.reasoning_summary, limit=140)}",
        ]
        if worker_result:
            lines.append(
                "result: findings={findings} | contradictions={contradictions} | limitations={limitations}".format(
                    findings=len(worker_result.get("findings", [])),
                    contradictions=len(
                        worker_result.get("contradictions", [])),
                    limitations=len(worker_result.get("limitations", [])),
                )
            )
        return lines

    def _build_phase3a_round_timestamp(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> str:
        for component_context in [
            round_context.analysis_run,
            round_context.ranking_run,
            round_context.planner_run,
            round_context.critic_run,
        ]:
            if component_context is None:
                continue
            created_at = str(component_context.component_run.get(
                "created_at", "")).strip()
            if created_at:
                return created_at
        return "unavailable"

    def _build_phase3a_round_batch_id(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> str:
        for component_context in [
            round_context.analysis_run,
            round_context.ranking_run,
            round_context.planner_run,
            round_context.critic_run,
        ]:
            if component_context is None:
                continue
            batch_id = str(component_context.component_run.get(
                "batch_id", "")).strip()
            if batch_id:
                return batch_id
        return str(round_context.frozen_snapshot.get("batch_id", "unknown"))

    def _count_round_worker_runs(
        self,
        round_manifest: dict[str, Any],
    ) -> int:
        return sum(len(record.get("worker_run_paths", [])) for record in list(round_manifest.get("hypothesis_runs", [])))

    def _build_phase3a_strategy_preview(
        self,
        lineage_context: Phase3AHypothesisLineageContext,
    ) -> str:
        if lineage_context.router_run is None:
            return "unavailable"
        planner_strategy = dict(lineage_context.router_run.planner_strategy)
        if planner_strategy.get("strategic_objective"):
            return self._preview_text(planner_strategy.get("strategic_objective"), limit=120)
        key_checks = list(planner_strategy.get("key_checks", []))
        if key_checks:
            return self._preview_text(key_checks[0], limit=120)
        return self._preview_text(planner_strategy.get("strategy_id") or lineage_context.hypothesis_record.get("planner_strategy_id"), limit=120)

    def _build_phase3a_aggregation_preview(
        self,
        lineage_context: Phase3AHypothesisLineageContext,
    ) -> tuple[str, int, str]:
        if lineage_context.aggregation_run is None:
            return ("unavailable", 0, "No aggregation artifact is available.")

        aggregation_run = lineage_context.aggregation_run
        aggregation_handoff = dict(aggregation_run.aggregation_handoff)
        synthesis_preview = self._preview_text(
            aggregation_handoff.get("update_focus")
            or next(iter(aggregation_handoff.get("merged_findings", [])), "")
            or next(iter(aggregation_run.parsed_output.get("merged_findings", [])), ""),
            limit=120,
        )
        contradiction_count = len(
            aggregation_handoff.get("preserved_contradictions", []))
        status = str(aggregation_run.component_run.get("status", "unknown"))
        return status, contradiction_count, synthesis_preview

    def _build_phase3a_worker_preview_lines(
        self,
        worker_run: WorkerRunContext,
    ) -> list[str]:
        worker_result = self._get_worker_result_payload(worker_run)
        step_traces = self._build_worker_step_traces(worker_run)
        latest_step = step_traces[-1] if step_traces else None
        allowed_actions = ", ".join(
            list(worker_run.worker_task.get("allowed_actions", []))[:3]) or "none"
        local_refs = ", ".join(list(worker_run.worker_task.get(
            "local_context_refs", []))[:4]) or "none"
        lines = [
            f"task={worker_run.component_run.get('task_id', 'unknown')} | status={worker_run.component_run.get('status', 'unknown')} / {worker_run.component_run.get('worker_status', 'unknown')}",
            f"scope: {self._preview_text(worker_run.worker_task.get('task_scope'), limit=140)}",
            f"allowed_actions: {self._preview_text(allowed_actions, limit=120)} | local_context_refs: {self._preview_text(local_refs, limit=120)}",
        ]
        if latest_step is not None:
            lines.append(
                f"latest_step: {latest_step.step_index} ({latest_step.step_mode}) | decision={latest_step.decision or 'unknown'} | flags={len(latest_step.flags)}"
            )
        if worker_result:
            lines.append(
                "result: findings={findings} | contradictions={contradictions} | limitations={limitations}".format(
                    findings=len(worker_result.get("findings", [])),
                    contradictions=len(
                        worker_result.get("contradictions", [])),
                    limitations=len(worker_result.get("limitations", [])),
                )
            )
        return lines

    def _build_phase3a_round_default_hypothesis_lines(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> list[str]:
        hypothesis_records = list(
            round_context.round_manifest.get("hypothesis_runs", []))
        if not hypothesis_records:
            return []

        lineage_context = self._build_phase3a_hypothesis_lineage_context(
            hypothesis_records[0])
        aggregation_status, contradiction_count, synthesis_preview = self._build_phase3a_aggregation_preview(
            lineage_context)
        return [
            f"hypothesis_id={lineage_context.hypothesis_record.get('hypothesis_id', 'unknown')} | strategy_id={lineage_context.hypothesis_record.get('planner_strategy_id', 'unknown')}",
            f"planner_strategy: {self._build_phase3a_strategy_preview(lineage_context)}",
            f"aggregation={aggregation_status} | contradictions={contradiction_count}",
            f"synthesis: {synthesis_preview}",
        ]

    def _build_phase3a_hypothesis_default_worker_lines(
        self,
        lineage_context: Phase3AHypothesisLineageContext,
    ) -> list[str]:
        if not lineage_context.worker_runs:
            return []
        return self._build_phase3a_worker_preview_lines(lineage_context.worker_runs[0])

    def _build_phase3a_inter_hypothesis_focus_lines(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> list[str]:
        aggregation_summary = dict(
            round_context.global_aggregation_summary or {})
        parsed_output = dict(aggregation_summary.get(
            "parsed_output") or aggregation_summary)
        synthesis_records = [
            dict(item)
            for item in list(parsed_output.get("source_hypothesis_records", []))
            if isinstance(item, dict)
        ]
        if not synthesis_records:
            return ["No persisted source_hypothesis_records are available for this round."]

        lines: list[str] = []
        for record in synthesis_records[:5]:
            lines.append(
                "{hypothesis_id} | findings={findings} | contradictions={contradictions} | gaps={gaps} | evidence={evidence} | focus={focus}".format(
                    hypothesis_id=str(record.get(
                        "hypothesis_id", "unknown_hypothesis")),
                    findings=len(record.get("merged_findings", [])),
                    contradictions=len(record.get(
                        "preserved_contradictions", [])),
                    gaps=len(record.get("open_gaps", [])),
                    evidence=len(record.get("evidence_refs", [])),
                    focus=self._preview_text(
                        record.get("update_focus")
                        or next(iter(record.get("merged_findings", [])), "")
                        or "No persisted focus summary.",
                        limit=120,
                    ),
                )
            )
        remaining = len(synthesis_records) - len(lines)
        if remaining > 0:
            lines.append(
                f"... {remaining} additional persisted source_hypothesis_records.")
        return lines

    def _build_phase3a_inter_hypothesis_parsed_output(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> dict[str, Any]:
        aggregation_summary = dict(
            round_context.global_aggregation_summary or {})
        parsed_output = dict(aggregation_summary.get("parsed_output") or {})
        if parsed_output:
            return parsed_output
        return {
            "batch_id": str(aggregation_summary.get("batch_id", "")),
            "round_id": str(aggregation_summary.get("round_id", "")),
            "selected_hypothesis_ids": list(aggregation_summary.get("selected_hypothesis_ids", [])),
            "source_hypothesis_records": list(aggregation_summary.get("source_hypothesis_records", [])),
        }

    def _build_phase3a_runtime_event_identity(self, event: dict[str, Any]) -> str:
        payload = dict(event.get("payload", {}) or {})
        ids = dict(payload.get("ids", {}) or {})
        parts: list[str] = []
        for key in ("batch_id", "round_id", "hypothesis_id", "task_id", "step", "attempt"):
            value = payload.get(key)
            if value in {None, ""}:
                value = ids.get(key)
            if value in {None, ""}:
                continue
            parts.append(f"{key}={value}")
        return " ".join(parts) or "no_ids"

    def _build_phase3a_runtime_event_preview(self, event: dict[str, Any]) -> str:
        event_type = str(event.get("event_type", "unknown"))
        payload = dict(event.get("payload", {}) or {})
        if event_type == "VALIDATION_RESULT":
            validation = dict(payload.get("validation", {}) or {})
            return "validation_ok={ok} warnings={warnings} errors={errors}".format(
                ok=validation.get("ok", False),
                warnings=len(validation.get("warnings", [])),
                errors=len(validation.get("errors", [])),
            )
        if event_type == "BARRIER_STATUS":
            return "expected={expected} completed={completed} waiting_for={waiting}".format(
                expected=payload.get("expected", 0),
                completed=payload.get("completed", 0),
                waiting=len(payload.get("waiting_for", [])),
            )
        if event_type == "WORKER_STEP":
            return "mode={mode} decision={decision} actions={actions}".format(
                mode=payload.get("mode", "unknown"),
                decision=payload.get("decision", "unknown"),
                actions=payload.get("actions", 0),
            )
        if event_type == "PHASE_MESSAGE":
            return self._preview_text(payload.get("message"), limit=120)
        if event_type == "EXCEPTION":
            return self._preview_text(payload.get("exception_message"), limit=120)
        elapsed_s = payload.get("elapsed_s")
        if elapsed_s is not None:
            return f"elapsed_s={elapsed_s}"
        return self._preview_text(" ".join(list(event.get("terminal_lines", []))), limit=120)

    def _build_phase3a_runtime_event_index_lines(
        self,
        event_stream: list[dict[str, Any]],
    ) -> list[str]:
        lines: list[str] = []
        for index, event in enumerate(event_stream, start=1):
            lines.append(
                "[{index}] {event_type} | component={component} | {identity} | {preview}".format(
                    index=index,
                    event_type=str(event.get("event_type", "unknown")),
                    component=str(event.get("component", "unknown")),
                    identity=self._build_phase3a_runtime_event_identity(event),
                    preview=self._build_phase3a_runtime_event_preview(
                        event) or "no_preview",
                )
            )
        return lines

    def _render_phase3a_runtime_event_review(
        self,
        event_index: int,
        event: dict[str, Any],
    ) -> None:
        payload = dict(event.get("payload", {}) or {})
        terminal_lines = list(event.get("terminal_lines", []) or [])
        focus_lines = [
            f"identity: {self._build_phase3a_runtime_event_identity(event)}",
            f"preview: {self._build_phase3a_runtime_event_preview(event) or 'none'}",
            f"payload_keys: {', '.join(sorted(payload.keys())) or 'none'}",
            f"captured_terminal_lines: {len(terminal_lines)}",
        ]
        self._render(
            render_phase3a_runtime_event_review(
                event_label=f"event[{event_index}] {event.get('event_type', 'unknown')} / {event.get('component', 'unknown')}",
                summary_pairs=[
                    ("index", str(event_index)),
                    ("event_type", str(event.get("event_type", "unknown"))),
                    ("component", str(event.get("component", "unknown"))),
                    ("identity", self._build_phase3a_runtime_event_identity(event)),
                ],
                focus_lines=focus_lines,
                options=[
                    ("1", "Inspect Event Payload"),
                    ("2", "View Captured Terminal Lines"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _view_phase3a_runtime_event_stream_menu(
        self,
        run_context: Phase3ARuntimeRunContext,
    ) -> None:
        event_stream = [
            dict(event)
            for event in list(run_context.event_stream or [])
            if isinstance(event, dict)
        ]
        if not event_stream:
            self._show_error(
                "No persisted structured runtime event stream is available for this batch runtime run."
            )
            return

        event_lines = self._build_phase3a_runtime_event_index_lines(
            event_stream)
        event_type_counts = Counter(
            str(event.get("event_type", "unknown")) for event in event_stream
        )
        run_name = Path(
            run_context.artifact_paths.get("component_run_path", "")
        ).parent.name or "phase3a_runtime_run"
        summary_pairs = [
            ("events", str(len(event_stream))),
            ("components", str(
                len({str(event.get('component', 'unknown')) for event in event_stream}))),
            ("event_types", str(len(event_type_counts))),
            ("top_event_type", event_type_counts.most_common(
                1)[0][0] if event_type_counts else "none"),
        ]

        while True:
            self._render(
                render_phase3a_runtime_event_stream_index(
                    run_name=run_name,
                    summary_pairs=summary_pairs,
                    event_lines=event_lines,
                    options=[("B", "Back"), ("Q", "Quit")],
                )
            )
            choice = self._read_menu_choice(
                {str(index)
                 for index in range(1, len(event_stream) + 1)} | {"B", "Q"}
            )
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return

            selected_index = int(choice)
            selected_event = event_stream[selected_index - 1]
            while True:
                self._render_phase3a_runtime_event_review(
                    selected_index, selected_event)
                event_choice = self._read_menu_choice({"1", "2", "B", "Q"})
                if event_choice == "Q":
                    self._quit()
                    return
                if event_choice == "B":
                    break
                if event_choice == "1":
                    self._render(
                        render_tool_json_view(
                            title="Phase 3A Runtime Event Payload",
                            path_label="Phase 3A Components / Batch Runtime / Debugger / Event / Payload",
                            payload=selected_event,
                            hint="Full persisted runtime event payload in recorded order.",
                        )
                    )
                    self._wait_for_enter()
                    continue
                self._render(
                    render_text_view(
                        title="Phase 3A Runtime Event Terminal Lines",
                        path_label="Phase 3A Components / Batch Runtime / Debugger / Event / Terminal Lines",
                        content="\n".join(
                            list(selected_event.get("terminal_lines", [])))
                        or "No terminal lines were captured for this persisted event.",
                        hint="Terminal replay lines emitted alongside this structured runtime event.",
                    )
                )
                self._wait_for_enter()

    def _render_phase3a_runtime_inter_hypothesis_aggregation_review(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> None:
        aggregation_summary = dict(
            round_context.global_aggregation_summary or {})
        parsed_output = dict(aggregation_summary.get(
            "parsed_output") or aggregation_summary)
        component_run = dict(
            aggregation_summary.get("component_run", {}) or {})
        validation_report = dict(
            aggregation_summary.get("validation_report", {}) or {})
        runtime_metrics = dict(
            aggregation_summary.get("runtime_metrics", {}) or {})
        selected_hypothesis_ids = list(
            parsed_output.get("selected_hypothesis_ids", []))
        source_hypothesis_records = list(
            parsed_output.get("source_hypothesis_records", []))
        self._render(
            render_phase3a_runtime_inter_hypothesis_aggregation_review(
                round_id=str(round_context.round_manifest.get(
                    "round_id", "round")),
                summary_pairs=[
                    ("status", str(component_run.get("status", "unknown"))),
                    ("authoritative_status", str(component_run.get(
                        "authoritative_status", validation_report.get("ok", False)))),
                    ("validation_ok", str(component_run.get(
                        "validation_ok", validation_report.get("ok", False)))),
                    ("selected_hypotheses", str(component_run.get(
                        "selected_hypothesis_count", len(selected_hypothesis_ids)))),
                    ("source_records", str(component_run.get(
                        "source_hypothesis_count", len(source_hypothesis_records)))),
                    ("preserved_findings", str(runtime_metrics.get("preserved_finding_count", sum(
                        len(dict(record).get("merged_findings", [])) for record in source_hypothesis_records if isinstance(record, dict))))),
                    ("contradictions", str(runtime_metrics.get("preserved_contradiction_count", sum(
                        len(dict(record).get("preserved_contradictions", [])) for record in source_hypothesis_records if isinstance(record, dict))))),
                    ("open_gaps", str(runtime_metrics.get("preserved_open_gap_count", sum(
                        len(dict(record).get("open_gaps", [])) for record in source_hypothesis_records if isinstance(record, dict))))),
                ],
                synthesis_lines=self._build_phase3a_inter_hypothesis_focus_lines(
                    round_context),
                options=[
                    ("1", "Inspect Inputs"),
                    ("2", "Inspect Synthesized Output"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _view_phase3a_runtime_inter_hypothesis_aggregation_menu(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> None:
        aggregation_summary = dict(
            round_context.global_aggregation_summary or {})
        if not aggregation_summary:
            self._show_error(
                "No persisted inter-hypothesis aggregation artifact is available for this round."
            )
            return
        parsed_output = dict(aggregation_summary.get(
            "parsed_output") or aggregation_summary)

        while True:
            self._render_phase3a_runtime_inter_hypothesis_aggregation_review(
                round_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return
            if choice == "1":
                self._render(
                    render_tool_json_view(
                        title="Phase 3A Inter-Hypothesis Aggregation Inputs",
                        path_label="Phase 3A Components / Batch Runtime / Review / Round / Inter-Hypothesis Aggregation / Inputs",
                        payload={
                            "batch_id": parsed_output.get("batch_id", ""),
                            "round_id": parsed_output.get("round_id", ""),
                            "selected_hypothesis_ids": list(parsed_output.get("selected_hypothesis_ids", [])),
                            "source_hypothesis_records": list(parsed_output.get("source_hypothesis_records", [])),
                        },
                        hint="Persisted round inputs and source records consumed by the canonical aggregation step.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "2":
                self._render(
                    render_tool_json_view(
                        title="Phase 3A Inter-Hypothesis Aggregation Output",
                        path_label="Phase 3A Components / Batch Runtime / Review / Round / Inter-Hypothesis Aggregation / Output",
                        payload=self._build_phase3a_inter_hypothesis_parsed_output(
                            round_context),
                        hint="Canonical round artifact with preserved source hypothesis records and provenance.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "3":
                self._render(
                    render_tool_json_view(
                        title="Phase 3A Inter-Hypothesis Aggregation Validation",
                        path_label="Phase 3A Components / Batch Runtime / Review / Round / Inter-Hypothesis Aggregation / Validation",
                        payload=dict(aggregation_summary.get(
                            "validation_report", {}) or {}),
                        hint="Authoritative validation state for the persisted round-level aggregation record.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "4":
                prompt_text = str(aggregation_summary.get(
                    "prompt_text", "") or "").strip()
                raw_response_text = str(aggregation_summary.get(
                    "raw_response", "") or "").strip()
                self._render(
                    render_text_view(
                        title="Phase 3A Inter-Hypothesis Aggregation Prompt / Response",
                        path_label="Phase 3A Components / Batch Runtime / Review / Round / Inter-Hypothesis Aggregation / Prompt Response",
                        content=(
                            "prompt_text:\n"
                            + (str(aggregation_summary.get("rendered_prompt", "") or "")
                               or "No persisted prompt text is available for this round.")
                            + "\n\nraw_response_text:\n"
                            + (str(aggregation_summary.get("raw_response", "") or "")
                               or "No persisted raw response text is available for this round.")
                        ),
                        hint="Prompt/response surface for the canonical aggregation node.",
                    )
                )
                self._wait_for_enter()
                continue

            self._render(
                render_tool_json_view(
                    title="Phase 3A Inter-Hypothesis Aggregation Technical Details",
                    path_label="Phase 3A Components / Batch Runtime / Review / Round / Inter-Hypothesis Aggregation / Technical Details",
                    payload={
                        "component_run": dict(aggregation_summary.get("component_run", {}) or {}),
                        "runtime_metrics": dict(aggregation_summary.get("runtime_metrics", {}) or {}),
                        "replay_metadata": dict(aggregation_summary.get("replay_metadata", {}) or {}),
                        "artifact_path": str(round_context.round_manifest.get("global_aggregation_path", "")),
                    },
                    hint="Authoritative component status, metrics, replay metadata, and persisted artifact location for this round-level aggregation node.",
                )
            )
            self._wait_for_enter()

    def _build_worker_step_index_lines(
        self,
        step_traces: list[WorkerStepTrace],
    ) -> list[str]:
        lines: list[str] = []
        for index, step_trace in enumerate(step_traces, start=1):
            lines.append(
                "[{index}] step={step_index} | mode={mode} | decision={decision} | attempts={attempts} | actions={actions} | flags={flags}".format(
                    index=index,
                    step_index=step_trace.step_index,
                    mode=step_trace.step_mode,
                    decision=step_trace.decision or "unknown",
                    attempts=len(step_trace.attempts),
                    actions=len(step_trace.executed_actions),
                    flags=len(step_trace.flags),
                )
            )
        return lines

    def _render_critic_run_review(
        self,
        run_context: CriticRunContext,
    ) -> None:
        run_name = Path(
            run_context.artifact_paths.get("component_run_path", "")
        ).parent.name or "critic_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("round_id", str(run_context.component_run.get("round_id", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("final_round_gate", str(run_context.component_run.get(
                "final_round_gate_status", "unknown"))),
            ("observation_count", str(
                run_context.component_run.get("observation_count", 0))),
        ]
        self._render(
            render_critic_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Critic Input Summary"),
                    ("2", "Inspect Critic Observations"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_final_batch_auditor_run_review(
        self,
        run_context: FinalBatchAuditorRunContext,
    ) -> None:
        run_name = Path(
            run_context.artifact_paths.get("component_run_path", "")
        ).parent.name or "final_batch_audit_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("state_version", str(run_context.component_run.get(
                "state_version", "unknown"))),
            ("model", str(run_context.component_run.get("model_name", "unknown"))),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("validation_ok", str(run_context.component_run.get("validation_ok", False))),
            ("terminal_gate", str(run_context.component_run.get(
                "terminal_gate_status", "unknown"))),
            ("audit_mode", str(run_context.component_run.get(
                "audit_mode", "authoritative"))),
            ("traceability_refs", str(
                run_context.component_run.get("traceability_ref_count", 0))),
        ]
        self._render(
            render_final_batch_auditor_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Inspect Final Audit Input Summary"),
                    ("2", "Inspect Debugging Audit Report"),
                    ("3", "Inspect Validation"),
                    ("4", "Inspect Prompt / Response"),
                    ("5", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_phase3a_runtime_run_review(
        self,
        run_context: Phase3ARuntimeRunContext,
    ) -> None:
        component_models = dict(
            run_context.initial_runtime_context.get("component_model_names", {}))
        default_model_name = str(
            run_context.component_run.get("model_name", "unknown"))
        runtime_summary = dict(run_context.runtime_summary or {})
        round_manifests = list(
            run_context.batch_ledger.get("round_manifests", []))
        hypothesis_count = sum(
            len(manifest.get("hypothesis_runs", [])) for manifest in round_manifests)
        worker_task_count = sum(
            len(record.get("worker_run_paths", []))
            for manifest in round_manifests
            for record in list(manifest.get("hypothesis_runs", []))
        )
        summary_errors = list(runtime_summary.get("errors", []))
        summary_warnings = list(runtime_summary.get("warnings", []))
        completed_components = list(
            runtime_summary.get("completed_components", []))
        failed_components = list(runtime_summary.get("failed_components", []))
        error_message = ""
        if summary_errors and isinstance(summary_errors[0], dict):
            error_message = str(summary_errors[0].get("message", ""))
        run_name = Path(
            run_context.artifact_paths.get("component_run_path", "")
        ).parent.name or "phase3a_runtime_run"
        summary_pairs = [
            ("batch_id", str(run_context.component_run.get("batch_id", "unknown"))),
            ("dataset", str(run_context.initial_runtime_context.get(
                "dataset_path", "unknown"))),
            ("execution_mode", str(run_context.component_run.get("execution_mode",
             run_context.initial_runtime_context.get("execution_mode", "unknown")))),
            ("default_model", default_model_name),
            ("planning_model", str(component_models.get(
                "planner") or default_model_name)),
            ("worker_model", str(component_models.get("worker") or default_model_name)),
            ("synthesis_model", str(component_models.get(
                "aggregation") or default_model_name)),
            ("status", str(run_context.component_run.get("status", "unknown"))),
            ("final_status", str(run_context.component_run.get("final_status", "unknown"))),
            ("terminal_reason", str(run_context.component_run.get(
                "terminal_reason", "unknown"))),
            ("round_count", str(int(run_context.component_run.get(
                "round_count", 0) or len(round_manifests)))),
            ("rounds", str(len(round_manifests))),
            ("hypotheses", str(hypothesis_count)),
            ("worker_tasks", str(worker_task_count)),
            ("final_state_version", str(run_context.component_run.get(
                "final_state_version", "unknown"))),
            ("completed_components", str(len(completed_components))),
            ("failed_components", str(len(failed_components))),
            ("warnings", str(len(summary_warnings))),
            ("errors", str(len(summary_errors))),
            ("error", error_message or "none"),
        ]
        self._render(
            render_phase3a_runtime_run_review(
                run_name=run_name,
                summary_pairs=summary_pairs,
                artifact_paths=run_context.artifact_paths,
                options=[
                    ("1", "Review Semantic Extraction"),
                    ("2", "Review Hypothesis Generation"),
                    ("3", "Browse Hypothesis Ranking Tree"),
                    ("4", "Browse Planner Tree"),
                    ("5", "Browse Router / Worker / Aggregation Tree"),
                    ("6", "Review Statement / Final Batch Auditor"),
                    ("7", "Review Critic Tree"),
                    ("8", "View Runtime Execution Log"),
                    ("9", "View Structured Runtime Event Stream"),
                    ("10", "Inspect Runtime Overview"),
                    ("11", "Inspect Batch Ledger"),
                    ("12", "Inspect State Evolution"),
                    ("13", "Inspect Technical Details"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_phase3a_runtime_round_review(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> None:
        round_manifest = round_context.round_manifest
        summary_pairs = [
            ("batch_id", self._build_phase3a_round_batch_id(round_context)),
            ("round_id", str(round_manifest.get("round_id", "unknown"))),
            ("created_at", self._build_phase3a_round_timestamp(round_context)),
            ("analysis_mode", str(round_manifest.get("analysis_mode", "unknown"))),
            ("status", str(round_manifest.get("status", "unknown"))),
            ("terminal_reason", str(round_manifest.get("terminal_reason", "none"))),
            ("state_versions",
             f"{round_manifest.get('start_state_version', 'unknown')} -> {round_manifest.get('end_state_version', 'unknown')}"),
            ("selected_hypotheses", str(
                len(round_manifest.get("selected_hypothesis_ids", [])))),
            ("deferred_hypotheses", str(
                len(round_manifest.get("deferred_hypothesis_ids", [])))),
            ("hypothesis_runs", str(len(round_manifest.get("hypothesis_runs", [])))),
            ("worker_runs", str(self._count_round_worker_runs(round_manifest))),
        ]
        artifact_pairs = [
            ("frozen_snapshot", str(round_manifest.get(
                "frozen_snapshot_path", "unavailable"))),
            ("global_aggregation", str(round_manifest.get(
                "global_aggregation_path", "unavailable"))),
            ("analysis_run", str(round_manifest.get(
                "analysis_run_path", "unavailable"))),
            ("ranking_run", str(round_manifest.get("ranking_run_path", "unavailable"))),
            ("planner_run", str(round_manifest.get("planner_run_path", "unavailable"))),
            ("critic_run", str(round_manifest.get(
                "critic_run_path", "unavailable") or "unavailable")),
        ]
        self._render(
            render_phase3a_runtime_round_review(
                round_id=str(round_manifest.get("round_id", "round")),
                summary_pairs=summary_pairs,
                artifact_pairs=artifact_pairs,
                default_hypothesis_lines=self._build_phase3a_round_default_hypothesis_lines(
                    round_context),
                options=[
                    ("1", "Inspect Frozen Snapshot"),
                    ("2", "Review Investigation Analysis"),
                    ("3", "Review Ranking"),
                    ("4", "Review Planner"),
                    ("5", "Review Inter-Hypothesis Aggregation"),
                    ("6", "Browse Hypothesis Lineage"),
                    ("7", "Review Critic"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _render_phase3a_runtime_hypothesis_review(
        self,
        lineage_context: Phase3AHypothesisLineageContext,
    ) -> None:
        hypothesis_record = lineage_context.hypothesis_record
        aggregation_status, contradiction_count, synthesis_preview = self._build_phase3a_aggregation_preview(
            lineage_context)
        summary_pairs = [
            ("hypothesis_id", str(hypothesis_record.get("hypothesis_id", "unknown"))),
            ("strategy_id", str(hypothesis_record.get(
                "planner_strategy_id", "unknown"))),
            ("planner_strategy", self._build_phase3a_strategy_preview(lineage_context)),
            ("status", str(hypothesis_record.get("status", "unknown"))),
            ("aggregation_status", aggregation_status),
            ("task_count", str(len(hypothesis_record.get("task_ids", [])))),
            ("worker_runs", str(len(lineage_context.worker_runs))),
            ("contradictions", str(contradiction_count)),
            ("synthesis", synthesis_preview),
            ("state_versions",
             f"{hypothesis_record.get('start_state_version', 'unknown')} -> {hypothesis_record.get('end_state_version', 'unknown')}"),
        ]
        artifact_pairs = [
            ("router_run", str(hypothesis_record.get(
                "router_run_path", "unavailable"))),
            ("aggregation_run", str(hypothesis_record.get(
                "aggregation_run_path", "unavailable"))),
            ("state_manager_run", str(hypothesis_record.get(
                "state_manager_run_path", "unavailable"))),
        ]
        self._render(
            render_phase3a_runtime_hypothesis_review(
                hypothesis_id=str(hypothesis_record.get(
                    "hypothesis_id", "unknown_hypothesis")),
                summary_pairs=summary_pairs,
                artifact_pairs=artifact_pairs,
                default_worker_lines=self._build_phase3a_hypothesis_default_worker_lines(
                    lineage_context),
                options=[
                    ("1", "Review Router"),
                    ("2", "Review Worker Tasks"),
                    ("3", "Review Aggregation"),
                    ("4", "Review State Manager"),
                    ("5", "Inspect Lineage Summary"),
                    ("B", "Back"),
                    ("Q", "Quit"),
                ],
            )
        )

    def _review_loaded_component_context(
        self,
        *,
        run_context: Any,
        render_func: Callable[[Any], None],
        handle_func: Callable[[str, Any], None],
        valid_choices: set[str],
    ) -> None:
        while True:
            render_func(run_context)
            choice = self._read_menu_choice(valid_choices)
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return
            handle_func(choice, run_context)
            if not self._running:
                return

    def _build_phase3a_state_evolution_payload(
        self,
        run_context: Phase3ARuntimeRunContext,
    ) -> dict[str, Any]:
        round_summaries: list[dict[str, Any]] = []
        for manifest in list(run_context.batch_ledger.get("round_manifests", [])):
            hypothesis_summaries = []
            for record in list(manifest.get("hypothesis_runs", [])):
                hypothesis_summaries.append(
                    {
                        "hypothesis_id": record.get("hypothesis_id", "unknown"),
                        "planner_strategy_id": record.get("planner_strategy_id", ""),
                        "state_versions": {
                            "start": record.get("start_state_version", 0),
                            "end": record.get("end_state_version", 0),
                        },
                        "state_manager_run_path": record.get("state_manager_run_path", ""),
                    }
                )

            round_summaries.append(
                {
                    "round_id": manifest.get("round_id", "unknown"),
                    "state_versions": {
                        "start": manifest.get("start_state_version", 0),
                        "end": manifest.get("end_state_version", 0),
                    },
                    "terminal_reason": manifest.get("terminal_reason", ""),
                    "hypothesis_state_updates": hypothesis_summaries,
                }
            )

        return {
            "initial_state_version": run_context.initial_state.get("state_version", 0),
            "final_state_version": run_context.finalization_summary.get("final_state_version", 0),
            "rounds": round_summaries,
            "finalization": run_context.finalization_summary,
        }

    def _view_phase3a_runtime_rounds_menu(
        self,
        run_context: Phase3ARuntimeRunContext,
    ) -> None:
        round_manifests = list(
            run_context.batch_ledger.get("round_manifests", []))
        if not round_manifests:
            self._show_error(
                "No persisted round manifests are available for this Phase 3A batch run.")
            return

        run_name = Path(run_context.artifact_paths.get(
            "component_run_path", "")).parent.name or "phase3a_runtime_run"
        round_contexts = [self._build_phase3a_runtime_round_context(
            manifest) for manifest in round_manifests]
        while True:
            round_lines = [
                "[{index}] {round_id} | batch={batch_id} | started={started} | mode={analysis_mode} | hypotheses={hypothesis_runs} | workers={worker_runs} | status={status}".format(
                    index=index,
                    round_id=str(context.round_manifest.get(
                        "round_id", "unknown_round")),
                    batch_id=self._build_phase3a_round_batch_id(context),
                    started=self._build_phase3a_round_timestamp(context),
                    analysis_mode=str(context.round_manifest.get(
                        "analysis_mode", "unknown")),
                    hypothesis_runs=len(
                        context.round_manifest.get("hypothesis_runs", [])),
                    worker_runs=self._count_round_worker_runs(
                        context.round_manifest),
                    status=str(context.round_manifest.get(
                        "status", "unknown")),
                )
                for index, context in enumerate(round_contexts, start=1)
            ]
            self._render(
                render_phase3a_runtime_rounds_index(
                    run_name=run_name,
                    round_lines=round_lines,
                    options=[("B", "Back"), ("Q", "Quit")],
                )
            )
            choice = self._read_menu_choice(
                {str(index) for index in range(1, len(round_manifests) + 1)} | {"B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return

            round_context = round_contexts[int(choice) - 1]
            self._view_phase3a_runtime_round_review_menu(round_context)
            if not self._running:
                return

    def _view_phase3a_runtime_round_review_menu(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> None:
        while True:
            self._render_phase3a_runtime_round_review(round_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "6", "7", "B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return
            if choice == "1":
                self._render(
                    render_tool_json_view(
                        title="Phase 3A Frozen Round Snapshot",
                        path_label="Phase 3A Components / Batch Runtime / Review / Round / Snapshot",
                        payload=round_context.frozen_snapshot,
                        hint="Frozen same-round snapshot used as the stable round-start state.",
                    )
                )
                self._wait_for_enter()
                continue
            if choice == "2":
                if round_context.analysis_run is None:
                    self._show_error(
                        "No Investigation Analysis artifact is available for this round.")
                    continue
                self._review_loaded_component_context(
                    run_context=round_context.analysis_run,
                    render_func=self._render_investigation_analysis_run_review,
                    handle_func=self._handle_investigation_analysis_review_choice,
                    valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
                )
                continue
            if choice == "3":
                if round_context.ranking_run is None:
                    self._show_error(
                        "No Hypothesis Ranking artifact is available for this round.")
                    continue
                self._review_loaded_component_context(
                    run_context=round_context.ranking_run,
                    render_func=self._render_hypothesis_ranking_run_review,
                    handle_func=self._handle_hypothesis_ranking_review_choice,
                    valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
                )
                continue
            if choice == "4":
                if round_context.planner_run is None:
                    self._show_error(
                        "No Planner artifact is available for this round.")
                    continue
                self._review_loaded_component_context(
                    run_context=round_context.planner_run,
                    render_func=self._render_planner_run_review,
                    handle_func=self._handle_planner_review_choice,
                    valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
                )
                continue
            if choice == "5":
                self._view_phase3a_runtime_inter_hypothesis_aggregation_menu(
                    round_context)
                continue
            if choice == "6":
                self._view_phase3a_runtime_hypothesis_lineage_menu(
                    round_context)
                continue

            if round_context.critic_run is None:
                self._show_error(
                    "No Critic artifact is available for this round.")
                continue
            self._review_loaded_component_context(
                run_context=round_context.critic_run,
                render_func=self._render_critic_run_review,
                handle_func=self._handle_critic_review_choice,
                valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
            )

    def _view_phase3a_runtime_hypothesis_lineage_menu(
        self,
        round_context: Phase3ARuntimeRoundContext,
    ) -> None:
        hypothesis_records = list(
            round_context.round_manifest.get("hypothesis_runs", []))
        if not hypothesis_records:
            self._show_error(
                "No persisted hypothesis executions are available for this round.")
            return

        round_id = str(round_context.round_manifest.get("round_id", "round"))
        lineage_contexts = [self._build_phase3a_hypothesis_lineage_context(
            record) for record in hypothesis_records]
        while True:
            hypothesis_lines = [
                "[{index}] {hypothesis_id} | strategy={strategy_preview} | aggregation={aggregation_status} | contradictions={contradictions} | synthesis={synthesis} | workers={worker_runs}".format(
                    index=index,
                    hypothesis_id=str(context.hypothesis_record.get(
                        "hypothesis_id", "unknown_hypothesis")),
                    strategy_preview=self._build_phase3a_strategy_preview(
                        context),
                    aggregation_status=self._build_phase3a_aggregation_preview(context)[
                        0],
                    contradictions=self._build_phase3a_aggregation_preview(context)[
                        1],
                    synthesis=self._build_phase3a_aggregation_preview(context)[
                        2],
                    worker_runs=len(context.worker_runs),
                )
                for index, context in enumerate(lineage_contexts, start=1)
            ]
            self._render(
                render_phase3a_runtime_hypothesis_index(
                    round_id=round_id,
                    hypothesis_lines=hypothesis_lines,
                    options=[("B", "Back"), ("Q", "Quit")],
                )
            )
            choice = self._read_menu_choice(
                {str(index) for index in range(1, len(hypothesis_records) + 1)} | {"B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return

            lineage_context = lineage_contexts[int(choice) - 1]
            self._view_phase3a_runtime_hypothesis_review_menu(lineage_context)
            if not self._running:
                return

    def _view_phase3a_runtime_hypothesis_review_menu(
        self,
        lineage_context: Phase3AHypothesisLineageContext,
    ) -> None:
        while True:
            self._render_phase3a_runtime_hypothesis_review(lineage_context)
            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return
            if choice == "1":
                if lineage_context.router_run is None:
                    self._show_error(
                        "No Router artifact is available for this hypothesis lineage.")
                    continue
                self._review_loaded_component_context(
                    run_context=lineage_context.router_run,
                    render_func=self._render_router_run_review,
                    handle_func=self._handle_router_review_choice,
                    valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
                )
                continue
            if choice == "2":
                if not lineage_context.worker_runs:
                    self._show_error(
                        "No Worker artifacts are available for this hypothesis lineage.")
                    continue
                self._view_phase3a_runtime_worker_runs_menu(lineage_context)
                continue
            if choice == "3":
                if lineage_context.aggregation_run is None:
                    self._show_error(
                        "No Aggregation artifact is available for this hypothesis lineage.")
                    continue
                self._review_loaded_component_context(
                    run_context=lineage_context.aggregation_run,
                    render_func=self._render_aggregation_run_review,
                    handle_func=self._handle_aggregation_review_choice,
                    valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
                )
                continue
            if choice == "4":
                if lineage_context.state_manager_run is None:
                    self._show_error(
                        "No State Manager artifact is available for this hypothesis lineage.")
                    continue
                self._review_loaded_component_context(
                    run_context=lineage_context.state_manager_run,
                    render_func=self._render_state_manager_run_review,
                    handle_func=self._handle_state_manager_review_choice,
                    valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
                )
                continue

            self._render(
                render_tool_json_view(
                    title="Phase 3A Hypothesis Lineage Summary",
                    path_label="Phase 3A Components / Batch Runtime / Review / Hypothesis / Summary",
                    payload={
                        "hypothesis_record": lineage_context.hypothesis_record,
                        "worker_run_paths": [
                            worker_run.artifact_paths.get(
                                "component_run_path", "")
                            for worker_run in lineage_context.worker_runs
                        ],
                    },
                    hint="Persisted hypothesis-local lineage refs across Router, Worker, Aggregation, and State Manager.",
                )
            )
            self._wait_for_enter()

    def _view_phase3a_runtime_worker_runs_menu(
        self,
        lineage_context: Phase3AHypothesisLineageContext,
    ) -> None:
        worker_runs = lineage_context.worker_runs
        while True:
            worker_lines = [
                "[{index}] {task_id} | scope={scope} | actions={actions} | context={context_refs} | status={status}/{worker_status} | findings={findings} | contradictions={contradictions} | limitations={limitations}".format(
                    index=index,
                    task_id=str(worker_run.component_run.get(
                        "task_id", "unknown_task")),
                    scope=self._preview_text(
                        worker_run.worker_task.get("task_scope"), limit=72),
                    actions=self._preview_text(", ".join(list(worker_run.worker_task.get(
                        "allowed_actions", []))[:3]) or "none", limit=54),
                    context_refs=self._preview_text(", ".join(list(worker_run.worker_task.get(
                        "local_context_refs", []))[:4]) or "none", limit=54),
                    status=str(worker_run.component_run.get(
                        "status", "unknown")),
                    worker_status=str(worker_run.component_run.get(
                        "worker_status", "unknown")),
                    findings=len(self._get_worker_result_payload(
                        worker_run).get("findings", [])),
                    contradictions=len(self._get_worker_result_payload(
                        worker_run).get("contradictions", [])),
                    limitations=len(self._get_worker_result_payload(
                        worker_run).get("limitations", [])),
                )
                for index, worker_run in enumerate(worker_runs, start=1)
            ]
            self._render(
                render_phase3a_runtime_worker_index(
                    hypothesis_id=str(lineage_context.hypothesis_record.get(
                        "hypothesis_id", "hypothesis")),
                    worker_lines=worker_lines,
                    options=[("B", "Back"), ("Q", "Quit")],
                )
            )
            choice = self._read_menu_choice(
                {str(index) for index in range(1, len(worker_runs) + 1)} | {"B", "Q"})
            if choice == "Q":
                self._quit()
                return
            if choice == "B":
                return

            selected_worker_run = worker_runs[int(choice) - 1]
            while True:
                self._render_worker_run_review(selected_worker_run)
                review_choice = self._read_menu_choice(
                    {"1", "2", "3", "4", "5", "6", "7", "B", "Q"})
                if review_choice == "Q":
                    self._quit()
                    return
                if review_choice == "B":
                    break
                self._handle_worker_review_choice(
                    review_choice, selected_worker_run)
                if not self._running:
                    return
            if not self._running:
                return

    def _handle_phase3a_runtime_review_choice(
        self,
        choice: str,
        run_context: Phase3ARuntimeRunContext,
    ) -> None:
        if choice == "1":
            if run_context.semantic_extraction_run is None:
                self._show_error(
                    "No Semantic Extraction artifact is available for this batch runtime run.")
                return
            self._review_loaded_component_context(
                run_context=run_context.semantic_extraction_run,
                render_func=self._render_semantic_extraction_run_review,
                handle_func=self._handle_semantic_extraction_review_choice,
                valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
            )
            return
        if choice == "2":
            initial_analysis_path = str(run_context.batch_ledger.get(
                "initial_investigation_analysis_run_path", ""))
            investigation_analysis_run = self._load_optional_component_context(
                initial_analysis_path,
                self._load_investigation_analysis_run_context,
            )
            if investigation_analysis_run is None:
                self._show_error(
                    "No Hypothesis Generation artifact is available for this batch runtime run.")
                return
            self._review_loaded_component_context(
                run_context=investigation_analysis_run,
                render_func=self._render_investigation_analysis_run_review,
                handle_func=self._handle_investigation_analysis_review_choice,
                valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
            )
            return
        if choice in {"3", "4", "5", "7"}:
            self._view_phase3a_runtime_rounds_menu(run_context)
            return
        if choice == "6":
            if run_context.final_batch_auditor_run is None:
                self._show_error(
                    "No Final Batch Auditor artifact is available for this batch runtime run.")
                return
            self._review_loaded_component_context(
                run_context=run_context.final_batch_auditor_run,
                render_func=self._render_final_batch_auditor_run_review,
                handle_func=self._handle_final_batch_auditor_review_choice,
                valid_choices={"1", "2", "3", "4", "5", "B", "Q"},
            )
            return
        if choice == "8":
            self._render(
                render_text_view(
                    title="Phase 3A Runtime Execution Log",
                    path_label="Phase 3A Components / Batch Runtime / Debugger / Runtime Log",
                    content=run_context.terminal_log_text or "No persisted runtime terminal log is available for this run.",
                    hint="Replay of the persisted runtime stream captured during authoritative execution.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "9":
            self._view_phase3a_runtime_event_stream_menu(run_context)
            return
        if choice == "10":
            self._render(
                render_tool_json_view(
                    title="Phase 3A Runtime Overview",
                    path_label="Phase 3A Components / Batch Runtime / Debugger / Runtime Overview",
                    payload={
                        "component_run": run_context.component_run,
                        "run_manifest": run_context.run_manifest or {},
                        "initial_runtime_context": run_context.initial_runtime_context,
                        "finalization_summary": run_context.finalization_summary,
                        "runtime_metrics": run_context.runtime_metrics,
                        "runtime_summary": run_context.runtime_summary or {},
                        "event_stream": run_context.event_stream or [],
                    },
                    hint="High-level runtime configuration, terminal summary, and recorded metrics.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "11":
            self._render(
                render_tool_json_view(
                    title="Phase 3A Batch Ledger",
                    path_label="Phase 3A Components / Batch Runtime / Debugger / Batch Ledger",
                    payload=run_context.batch_ledger,
                    hint="Round-by-round lifecycle bookkeeping owned by the authoritative runtime.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "12":
            self._render(
                render_tool_json_view(
                    title="Phase 3A State Evolution",
                    path_label="Phase 3A Components / Batch Runtime / Debugger / State Evolution",
                    payload=self._build_phase3a_state_evolution_payload(
                        run_context),
                    hint="Version lineage across the initial state, per-round hypothesis updates, and finalization.",
                )
            )
            self._wait_for_enter()
            return
        if choice == "13":
            self._render(
                render_tool_json_view(
                    title="Phase 3A Runtime Technical Details",
                    path_label="Phase 3A Components / Batch Runtime / Debugger / Technical Details",
                    payload={
                        "component_run": run_context.component_run,
                        "runtime_metrics": run_context.runtime_metrics,
                        "replay_metadata": run_context.replay_metadata or {},
                        "artifact_paths": run_context.artifact_paths,
                    },
                    hint="Metrics, replay metadata, and persisted artifact locations.",
                )
            )
            self._wait_for_enter()
            return

        self._show_error(f"Unknown Phase 3A runtime review choice: {choice}")

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

    def _change_critic_model_name(self) -> None:
        selected_model = self._select_model_name(
            current_name=self._resolve_phase3a_model_name("critic"),
            custom_label="critic model",
        )
        if selected_model is None:
            return
        self.session_config.critic_model_name = selected_model
        self._show_info(
            f"Critic model updated to: {self.session_config.critic_model_name}")

    def _edit_session_config_flow(self) -> str:
        while True:
            self._render(
                render_session_config(
                    model_name=self.session_config.model_name,
                    planning_model_name=self._render_session_model_name(
                        "planning"),
                    worker_model_name=self._render_session_model_name(
                        "worker"),
                    synthesis_model_name=self._render_session_model_name(
                        "synthesis"),
                    critic_model_name=self._render_session_model_name(
                        "critic"),
                    judge_model_name=self.session_config.judge_model_name,
                    dataset_name=self._get_selected_dataset_label(),
                    trace_enabled=self.session_config.trace_enabled,
                    max_steps=self.session_config.max_steps,
                    evaluation_window=self.session_config.evaluation_window,
                )
            )

            choice = self._read_menu_choice(
                {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "B", "Q"})
            if choice == "B":
                return "back"
            if choice == "Q":
                return "quit"
            if choice == "1":
                self._change_model_name()
                continue
            if choice == "2":
                self._change_planning_model_name()
                continue
            if choice == "3":
                self._change_worker_model_name()
                continue
            if choice == "4":
                self._change_synthesis_model_name()
                continue
            if choice == "5":
                self._change_critic_model_name()
                continue
            if choice == "6":
                self._change_judge_model_name()
                continue
            if choice == "7":
                self._change_dataset_partition()
                continue
            if choice == "8":
                self._toggle_trace_enabled()
                continue
            if choice == "9":
                self._change_max_steps()
                continue
            self._change_evaluation_window()

    def _critic_config_flow(self) -> str:
        """Inline model selection for the Critic component."""
        selected = self._select_model_name(
            current_name=self._resolve_phase3a_model_name("critic"),
            custom_label="critic model",
        )
        if selected is not None:
            self.session_config.critic_model_name = selected
        return "critic"

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
        partition_name: str | None = None
        try:
            partition_name = self._get_selected_dataset_path().name
        except FileNotFoundError:
            partition_name = None
        return build_session_run_basename(
            self._session_run_counter,
            partition_name=partition_name,
            model_name=self.session_config.model_name,
        )

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
        selected_model = self._select_model_name(
            current_name=self.session_config.model_name,
            custom_label="session model",
        )
        if selected_model is None:
            return
        self.session_config.model_name = selected_model
        self._show_info(
            f"Session model updated to: {self.session_config.model_name}")

    def _change_judge_model_name(self) -> None:
        selected_model = self._select_model_name(
            current_name=self.session_config.judge_model_name,
            custom_label="judge model",
        )
        if selected_model is None:
            return
        self.session_config.judge_model_name = selected_model
        self._show_info(
            f"Judge model updated to: {self.session_config.judge_model_name}")

    def _change_planning_model_name(self) -> None:
        selected_model = self._select_model_name(
            current_name=self._resolve_phase3a_model_name("planner"),
            custom_label="planning model",
        )
        if selected_model is None:
            return
        self.session_config.planning_model_name = selected_model
        self._show_info(
            f"Planning model updated to: {self.session_config.planning_model_name}")

    def _change_worker_model_name(self) -> None:
        selected_model = self._select_model_name(
            current_name=self._resolve_phase3a_model_name("worker"),
            custom_label="worker model",
        )
        if selected_model is None:
            return
        self.session_config.worker_model_name = selected_model
        self._show_info(
            f"Worker model updated to: {self.session_config.worker_model_name}")

    def _change_synthesis_model_name(self) -> None:
        selected_model = self._select_model_name(
            current_name=self._resolve_phase3a_model_name("aggregation"),
            custom_label="synthesis model",
        )
        if selected_model is None:
            return
        self.session_config.synthesis_model_name = selected_model
        self._show_info(
            f"Synthesis model updated to: {self.session_config.synthesis_model_name}")

    def _select_model_name(self, *, current_name: str, custom_label: str) -> str | None:
        showing_full_list = False
        while True:
            options = OPENAI_FULL_MODEL_OPTIONS if showing_full_list else OPENAI_MODEL_OPTIONS
            toggle_key = "F" if showing_full_list else "L"
            toggle_label = "Featured models" if showing_full_list else "Full model list"

            self._render(
                render_model_selection(
                    options,
                    current_name,
                    description=(
                        "Choose one of the featured models or open the full list."
                        if not showing_full_list
                        else "Choose any available model or go back to the featured options."
                    ),
                    section_title=(
                        "Full Model List" if showing_full_list else "Featured Models"),
                    extra_actions=[(toggle_key, toggle_label)],
                )
            )

            valid_choices = {str(index) for index in range(
                1, len(options) + 1)} | {"B", "C", "Q", toggle_key}
            choice = self._read_menu_choice(valid_choices)
            if choice == "B":
                return None
            if choice == "C":
                return self._read_custom_model_name(custom_label)
            if choice == "Q":
                self._quit()
                return None
            if choice == toggle_key:
                showing_full_list = not showing_full_list
                continue
            return options[int(choice) - 1][1]

    def _read_custom_model_name(self, label: str) -> str:
        self._clear_screen()
        print(f"Enter the OpenAI model ID for the {label}:")
        while True:
            raw_value = input("> ").strip()
            if not raw_value:
                print("Enter a non-empty model ID.")
                continue
            return raw_value

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
            overview_lines = split_bullet_lines(
                extract_response_text(response))
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

    def _show_component_action_pending(
        self,
        *,
        component_name: str,
        action_name: str,
        implemented_summary: str,
    ) -> None:
        normalized_summary = implemented_summary.replace(
            " are available", " are implemented")
        self._show_info(
            f"{component_name} {action_name} is not implemented yet. Current CLI progress: {normalized_summary}."
        )

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
