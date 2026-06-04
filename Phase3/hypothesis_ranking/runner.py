"""Execution wrapper for the Phase 3A Hypothesis Ranking component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from hypothesis_ranking.context_resolver import (
    build_selection_index,
    collect_candidate_hypothesis_ids,
    project_candidate_hypothesis_context,
    project_ranking_state_min,
)
from hypothesis_ranking.contracts import MAX_SELECTION_BUDGET, SCHEMA_VERSION
from hypothesis_ranking.parser import parse_hypothesis_ranking_response
from hypothesis_ranking.prompt_builder import build_hypothesis_ranking_prompt
from hypothesis_ranking.runtime_artifacts import (
    build_hypothesis_ranking_artifact_paths,
    save_hypothesis_ranking_artifacts,
)
from hypothesis_ranking.validator import validate_ranking_decision, validate_ranking_state_min
from investigation_analysis.validator import validate_hypothesis_set
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception


HypothesisRankingCallable = Callable[[str], str]


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_hypothesis_ranking_callable(
    model_name: str,
    temperature: float = 0.0,
) -> HypothesisRankingCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run hypothesis ranking."
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


def run_hypothesis_ranking(
    investigation_hypothesis_set: dict[str, Any],
    ranking_state_min: dict[str, Any],
    *,
    llm_callable: HypothesisRankingCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
) -> dict[str, Any]:
    raw_hypothesis_set = investigation_hypothesis_set if isinstance(
        investigation_hypothesis_set, dict) else {}
    raw_ranking_state = ranking_state_min if isinstance(
        ranking_state_min, dict) else {}

    batch_id = str(raw_hypothesis_set.get("batch_id")
                   or "unknown_batch").strip() or "unknown_batch"
    analysis_id = str(raw_hypothesis_set.get("analysis_id")
                      or "unknown_analysis").strip() or "unknown_analysis"
    round_id = str(raw_ranking_state.get("round_id")
                   or "unknown_round").strip() or "unknown_round"

    hypothesis_set_validation = validate_hypothesis_set(
        raw_hypothesis_set,
        expected_batch_id=batch_id,
    )
    ranking_state_validation = validate_ranking_state_min(raw_ranking_state)

    projected_candidate_context = project_candidate_hypothesis_context(
        raw_hypothesis_set)
    projected_ranking_state = project_ranking_state_min(raw_ranking_state)
    candidate_hypothesis_ids = collect_candidate_hypothesis_ids(
        raw_hypothesis_set)
    selection_budget = (
        raw_ranking_state.get("selection_budget")
        if isinstance(raw_ranking_state.get("selection_budget"), int)
        else MAX_SELECTION_BUDGET
    )

    prompt_text = ""
    raw_response_text = ""
    parsed_output: dict[str, Any] = {}
    selection_index: dict[str, Any] = build_selection_index(
        raw_hypothesis_set, parsed_output)
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    output_validation: dict[str, Any] = _report_error(
        "parsed_output", "Parsed ranking decision was not produced.")

    start_time = perf_counter()
    phase_start("hypothesis_ranking", batch_id=batch_id, round_id=round_id)
    if hypothesis_set_validation["ok"] and ranking_state_validation["ok"]:
        prompt_text = build_hypothesis_ranking_prompt(
            batch_id=batch_id,
            round_id=round_id,
            projected_candidate_context=projected_candidate_context,
            projected_ranking_state=projected_ranking_state,
        )
        try:
            callable_to_use = llm_callable or _build_openai_hypothesis_ranking_callable(
                model_name,
                temperature,
            )
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_output = parse_hypothesis_ranking_response(
                raw_response_text)
            selection_index = build_selection_index(
                raw_hypothesis_set, parsed_output)
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            output_validation = validate_ranking_decision(
                parsed_output,
                candidate_hypothesis_ids=candidate_hypothesis_ids,
                expected_batch_id=batch_id,
                expected_round_id=round_id,
                selection_budget=selection_budget,
            )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("hypothesis_ranking", parse_validation,
                              batch_id=batch_id, round_id=round_id, analysis_id=analysis_id)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            parse_validation = _report_error("runtime", str(exc))
            exception("hypothesis_ranking", exc, round_id=round_id)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": (
            hypothesis_set_validation["ok"]
            and ranking_state_validation["ok"]
            and parse_validation["ok"]
            and output_validation["ok"]
        ),
        "schema_version": SCHEMA_VERSION,
        "hypothesis_set_validation": hypothesis_set_validation,
        "ranking_state_validation": ranking_state_validation,
        "parse_validation": parse_validation,
        "output_validation": output_validation,
    }
    status = "ok" if validation_report["ok"] else "error"
    validation_result("hypothesis_ranking", validation_report,
                      batch_id=batch_id, round_id=round_id, analysis_id=analysis_id)
    phase_end("hypothesis_ranking", elapsed_s=duration_ms / 1000.0,
              batch_id=batch_id, round_id=round_id, analysis_id=analysis_id)

    output_stats = output_validation.get(
        "stats", {}) if isinstance(output_validation, dict) else {}
    runtime_metrics = {
        "batch_id": batch_id,
        "analysis_id": analysis_id,
        "round_id": round_id,
        "model_name": model_name,
        "duration_ms": duration_ms,
        "status": status,
        "prompt_chars": len(prompt_text),
        "raw_response_chars": len(raw_response_text),
        "candidate_count": len(candidate_hypothesis_ids),
        "selected_count": output_stats.get("selected_count", selection_index.get("selected_count", 0)),
        "deferred_count": output_stats.get("deferred_count", selection_index.get("deferred_count", 0)),
        "selection_budget": selection_budget,
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "hypothesis_ranking",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "analysis_id": analysis_id,
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

    artifact_paths = build_hypothesis_ranking_artifact_paths(
        round_id=round_id, log_dir=log_dir)
    persisted_paths = save_hypothesis_ranking_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        candidate_hypotheses=raw_hypothesis_set,
        ranking_state_snapshot=raw_ranking_state,
        projected_candidate_context=projected_candidate_context,
        projected_ranking_state=projected_ranking_state,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        parsed_output=parsed_output,
        selection_index=selection_index,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    return {
        "component_run": component_run,
        "investigation_hypothesis_set": raw_hypothesis_set,
        "ranking_state_min": raw_ranking_state,
        "projected_candidate_context": projected_candidate_context,
        "projected_ranking_state": projected_ranking_state,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "ranking_decision": parsed_output,
        "parsed_output": parsed_output,
        "selection_index": selection_index,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }
