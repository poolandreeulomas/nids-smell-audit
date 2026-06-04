"""Execution wrapper for the Phase 3A Planner component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from planner.context_resolver import (
    build_strategy_index,
    collect_selected_hypothesis_ids,
    project_planner_round_context,
    project_selected_hypothesis_context,
)
from planner.contracts import SCHEMA_VERSION
from planner.parser import parse_planner_response
from planner.prompt_builder import build_planner_prompt
from planner.runtime_artifacts import build_planner_artifact_paths, save_planner_artifacts
from planner.validator import (
    validate_planner_round_context,
    validate_planner_round_output,
    validate_ranking_decision_min,
    validate_selected_hypothesis_context,
)
from tools.registry import get_tool_capability_records
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception


PlannerCallable = Callable[[str], str]


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_planner_callable(
    model_name: str,
    temperature: float = 0.0,
) -> PlannerCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run planner."
            ) from exc

        client = OpenAI()
        response = client.responses.create(
            **build_responses_create_kwargs(
                model_name=model_name,
                prompt_text=prompt_text,
                temperature=temperature,
            )
        )
        return extract_response_text(response)

    return _call_llm


def run_planner(
    ranking_decision_min: dict[str, Any],
    selected_hypothesis_context: dict[str, Any],
    planner_round_context: dict[str, Any],
    *,
    llm_callable: PlannerCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
) -> dict[str, Any]:
    raw_ranking_decision = ranking_decision_min if isinstance(
        ranking_decision_min, dict) else {}
    raw_selected_context = (
        selected_hypothesis_context if isinstance(
            selected_hypothesis_context, dict) else {}
    )
    raw_planner_round_context = planner_round_context if isinstance(
        planner_round_context, dict) else {}

    batch_id = str(raw_ranking_decision.get("batch_id")
                   or "unknown_batch").strip() or "unknown_batch"
    round_id = str(
        raw_ranking_decision.get("round_id")
        or raw_planner_round_context.get("round_id")
        or "unknown_round"
    ).strip() or "unknown_round"

    tool_capability_records = get_tool_capability_records()
    known_tool_refs = set(tool_capability_records.keys())

    ranking_decision_validation = validate_ranking_decision_min(
        raw_ranking_decision)
    selected_hypothesis_ids = collect_selected_hypothesis_ids(
        raw_ranking_decision)
    selected_context_validation = validate_selected_hypothesis_context(
        raw_selected_context,
        expected_selected_hypothesis_ids=selected_hypothesis_ids,
    )
    planner_round_context_validation = validate_planner_round_context(
        raw_planner_round_context,
        expected_round_id=round_id,
        known_tool_capability_refs=known_tool_refs,
    )

    projected_selected_context = project_selected_hypothesis_context(
        raw_selected_context)
    projected_planner_round_context = project_planner_round_context(
        raw_planner_round_context,
        tool_capability_catalog=tool_capability_records,
    )

    prompt_text = ""
    raw_response_text = ""
    parsed_output: dict[str, Any] = {}
    strategy_index: dict[str, Any] = build_strategy_index(
        raw_selected_context, parsed_output)
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    output_validation: dict[str, Any] = _report_error(
        "parsed_output",
        "Parsed planner output was not produced.",
    )

    start_time = perf_counter()
    phase_start("planner", batch_id=batch_id, round_id=round_id)
    if (
        ranking_decision_validation["ok"]
        and selected_context_validation["ok"]
        and planner_round_context_validation["ok"]
    ):
        prompt_text = build_planner_prompt(
            batch_id=batch_id,
            round_id=round_id,
            projected_selected_context=projected_selected_context,
            projected_planner_round_context=projected_planner_round_context,
        )
        try:
            callable_to_use = llm_callable or _build_openai_planner_callable(
                model_name, temperature)
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_output = parse_planner_response(raw_response_text)
            strategy_index = build_strategy_index(
                raw_selected_context, parsed_output)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            output_validation = validate_planner_round_output(
                parsed_output,
                selected_hypothesis_ids=selected_hypothesis_ids,
                expected_batch_id=batch_id,
                expected_round_id=round_id,
                known_tool_capability_refs=known_tool_refs,
            )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("planner", parse_validation,
                              batch_id=batch_id, round_id=round_id)
        except Exception as exc:  # pragma: no cover
            parse_validation = _report_error("runtime", str(exc))
            exception("planner", exc, round_id=round_id)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": (
            ranking_decision_validation["ok"]
            and selected_context_validation["ok"]
            and planner_round_context_validation["ok"]
            and parse_validation["ok"]
            and output_validation["ok"]
        ),
        "schema_version": SCHEMA_VERSION,
        "ranking_decision_validation": ranking_decision_validation,
        "selected_context_validation": selected_context_validation,
        "planner_round_context_validation": planner_round_context_validation,
        "parse_validation": parse_validation,
        "output_validation": output_validation,
    }
    status = "ok" if validation_report["ok"] else "error"
    validation_result("planner", validation_report,
                      batch_id=batch_id, round_id=round_id)
    phase_end("planner", elapsed_s=duration_ms / 1000.0,
              batch_id=batch_id, round_id=round_id)

    output_stats = output_validation.get(
        "stats", {}) if isinstance(output_validation, dict) else {}
    runtime_metrics = {
        "batch_id": batch_id,
        "round_id": round_id,
        "model_name": model_name,
        "duration_ms": duration_ms,
        "status": status,
        "prompt_chars": len(prompt_text),
        "raw_response_chars": len(raw_response_text),
        "selected_count": len(selected_hypothesis_ids),
        "strategy_count": output_stats.get("strategy_count", strategy_index.get("strategy_count", 0)),
        "tool_capability_ref_count": len(projected_planner_round_context.get("tool_capability_refs", [])),
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "planner",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "round_id": round_id,
        "status": status,
        "validation_ok": validation_report["ok"],
        "model_name": model_name,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }
    replay_metadata = {
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
    }

    artifact_paths = build_planner_artifact_paths(
        round_id=round_id, log_dir=log_dir)
    persisted_paths = save_planner_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        ranking_decision_min=raw_ranking_decision,
        selected_hypothesis_context=raw_selected_context,
        planner_round_context=raw_planner_round_context,
        projected_selected_context=projected_selected_context,
        projected_planner_round_context=projected_planner_round_context,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        parsed_output=parsed_output,
        strategy_index=strategy_index,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    return {
        "component_run": component_run,
        "ranking_decision_min": raw_ranking_decision,
        "selected_hypothesis_context": raw_selected_context,
        "planner_round_context": raw_planner_round_context,
        "projected_selected_context": projected_selected_context,
        "projected_planner_round_context": projected_planner_round_context,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "planner_round_output": parsed_output,
        "parsed_output": parsed_output,
        "strategy_index": strategy_index,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }
