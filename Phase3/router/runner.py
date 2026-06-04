"""Execution wrapper for the Phase 3A Router component."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable
import re

from planner.validator import validate_planner_round_output
from router.context_reducer import (
    build_task_bundle_index,
    collect_known_action_classes,
    project_planner_strategy,
    project_router_context_min,
)
from router.parser import parse_router_response
from router.prompt_builder import build_router_prompt
from router.runtime_artifacts import build_router_artifact_paths, save_router_artifacts
from router.validator import validate_router_context_min, validate_router_output
from router.contracts import SCHEMA_VERSION
from tools.registry import get_tool_capability_records
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end, validation_result, exception, phase_message


RouterCallable = Callable[[str], str]


def _sanitize_allowed_actions_in_parsed_output(parsed_output: dict[str, Any], allowed_action_classes: set[str]) -> None:
    """Ensure `allowed_actions` entries are canonical action classes.

    This mutates `parsed_output` in-place. For any action string that is not
    directly present in `allowed_action_classes` we apply a small heuristic
    token-matching step to map likely synonyms (for example
    'feature_relation' -> 'relation_verification'). Any unknown values that
    cannot be mapped are dropped.
    """
    if not isinstance(parsed_output, dict):
        return
    worker_tasks = parsed_output.get("worker_tasks") if isinstance(
        parsed_output.get("worker_tasks"), list) else []
    for wt in worker_tasks:
        if not isinstance(wt, dict):
            continue
        raw_allowed = wt.get("allowed_actions") or []
        if not isinstance(raw_allowed, list):
            raw_allowed = []
        sanitized: list[str] = []
        for action in raw_allowed:
            if not isinstance(action, str):
                continue
            candidate = action.strip()
            if not candidate:
                continue
            # If already canonical, keep it
            if candidate in allowed_action_classes:
                sanitized.append(candidate)
                continue
            # Heuristic token matching: prefer candidates that share tokens
            normalized = re.sub(r"[^a-zA-Z]", " ", candidate).lower()
            tokens = set(t for t in normalized.split() if t)
            if not tokens:
                continue
            best: str | None = None
            best_score = 0
            for a in sorted(allowed_action_classes):
                a_tokens = set(a.split("_"))
                score = len(a_tokens & tokens)
                if score > best_score:
                    best = a
                    best_score = score
            if best and best_score > 0:
                sanitized.append(best)
                continue
            # Fallback substring match
            for a in sorted(allowed_action_classes):
                if a in candidate.lower() or any(tok in a for tok in tokens):
                    sanitized.append(a)
                    break
        # Deduplicate while preserving order
        dedup: list[str] = []
        seen: set[str] = set()
        for s in sanitized:
            if s not in seen:
                dedup.append(s)
                seen.add(s)
        wt["allowed_actions"] = dedup


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def _build_openai_router_callable(
    model_name: str,
    temperature: float = 0.0,
) -> RouterCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run router."
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


def run_router(
    planner_strategy: dict[str, Any],
    router_context_min: dict[str, Any],
    *,
    batch_id: str,
    round_id: str,
    llm_callable: RouterCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
) -> dict[str, Any]:
    raw_planner_strategy = planner_strategy if isinstance(
        planner_strategy, dict) else {}
    raw_router_context = router_context_min if isinstance(
        router_context_min, dict) else {}

    normalized_batch_id = str(
        batch_id or "unknown_batch").strip() or "unknown_batch"
    normalized_round_id = str(
        round_id or "unknown_round").strip() or "unknown_round"
    hypothesis_id = str(raw_planner_strategy.get(
        "hypothesis_id") or "unknown_hypothesis").strip() or "unknown_hypothesis"
    planner_strategy_id = str(raw_planner_strategy.get(
        "strategy_id") or "unknown_strategy").strip() or "unknown_strategy"

    tool_capability_records = get_tool_capability_records()
    known_tool_refs = set(tool_capability_records.keys())

    planner_strategy_validation = validate_planner_round_output(
        {
            "batch_id": normalized_batch_id,
            "round_id": normalized_round_id,
            "planner_strategies": [raw_planner_strategy],
        },
        selected_hypothesis_ids=[hypothesis_id] if hypothesis_id else [],
        expected_batch_id=normalized_batch_id,
        expected_round_id=normalized_round_id,
        known_tool_capability_refs=known_tool_refs,
    )
    router_context_validation = validate_router_context_min(
        raw_router_context,
        known_tool_capability_refs=known_tool_refs,
    )

    projected_planner_strategy = project_planner_strategy(raw_planner_strategy)
    reduced_context = project_router_context_min(
        raw_router_context,
        tool_capability_catalog=tool_capability_records,
    )
    allowed_action_classes = set(
        reduced_context.get("available_action_classes", []))
    known_context_refs = set(reduced_context.get("related_substrate_refs", []))
    max_tasks = reduced_context.get("execution_budget", {}).get("max_tasks", 0)

    prompt_text = ""
    raw_response_text = ""
    parsed_output: dict[str, Any] = {}
    task_bundle_index = build_task_bundle_index(parsed_output)
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    output_validation: dict[str, Any] = _report_error(
        "parsed_output",
        "Parsed router output was not produced.",
    )

    start_time = perf_counter()
    phase_start("router", batch_id=normalized_batch_id,
                round_id=normalized_round_id, hypothesis_id=hypothesis_id)
    if planner_strategy_validation["ok"] and router_context_validation["ok"]:
        prompt_text = build_router_prompt(
            batch_id=normalized_batch_id,
            round_id=normalized_round_id,
            projected_planner_strategy=projected_planner_strategy,
            projected_router_context=reduced_context,
        )
        try:
            callable_to_use = llm_callable or _build_openai_router_callable(
                model_name, temperature)
            raw_response_text = str(callable_to_use(prompt_text) or "")
            parsed_output = parse_router_response(raw_response_text)
            # Sanitize allowed_actions so only canonical action classes
            # from the reduced context are present. This prevents tool-name
            # leakage (e.g. 'feature_relation') into the worker task field.
            _sanitize_allowed_actions_in_parsed_output(
                parsed_output, allowed_action_classes)
            task_bundle_index = build_task_bundle_index(parsed_output)
            phase_message(
                "router",
                f"GENERATED {task_bundle_index.get('task_count', len(parsed_output.get('worker_tasks', [])))} TASKS",
                hypothesis_id=hypothesis_id,
            )
            parse_validation = {"ok": True, "errors": [], "warnings": []}
            output_validation = validate_router_output(
                parsed_output,
                expected_batch_id=normalized_batch_id,
                expected_round_id=normalized_round_id,
                expected_hypothesis_id=hypothesis_id,
                expected_planner_strategy_id=planner_strategy_id,
                allowed_action_classes=allowed_action_classes,
                known_context_refs=known_context_refs,
                max_tasks=max_tasks if isinstance(max_tasks, int) and max_tasks > 0 else len(
                    parsed_output.get("worker_tasks", [])),
                known_tool_capability_refs=known_tool_refs,
            )
        except ValueError as exc:
            parse_validation = _report_error("raw_response", str(exc))
            validation_result("router", parse_validation, batch_id=normalized_batch_id,
                              round_id=normalized_round_id, hypothesis_id=hypothesis_id)
        except Exception as exc:  # pragma: no cover
            parse_validation = _report_error("runtime", str(exc))
            exception("router", exc, round_id=normalized_round_id,
                      hypothesis_id=hypothesis_id)

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    validation_report = {
        "ok": (
            planner_strategy_validation["ok"]
            and router_context_validation["ok"]
            and parse_validation["ok"]
            and output_validation["ok"]
        ),
        "schema_version": SCHEMA_VERSION,
        "planner_strategy_validation": planner_strategy_validation,
        "router_context_validation": router_context_validation,
        "parse_validation": parse_validation,
        "output_validation": output_validation,
    }
    status = "ok" if validation_report["ok"] else "error"

    output_stats = output_validation.get(
        "stats", {}) if isinstance(output_validation, dict) else {}
    runtime_metrics = {
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "hypothesis_id": hypothesis_id,
        "planner_strategy_id": planner_strategy_id,
        "model_name": model_name,
        "duration_ms": duration_ms,
        "status": status,
        "prompt_chars": len(prompt_text),
        "raw_response_chars": len(raw_response_text),
        "task_count": output_stats.get("task_count", task_bundle_index.get("task_count", 0)),
        "allowed_action_class_count": output_stats.get(
            "allowed_action_class_count",
            task_bundle_index.get("action_class_count", 0),
        ),
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
    }
    component_run = {
        "component": "router",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "hypothesis_id": hypothesis_id,
        "planner_strategy_id": planner_strategy_id,
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

    artifact_paths = build_router_artifact_paths(
        planner_strategy_id=planner_strategy_id,
        log_dir=log_dir,
    )
    persisted_paths = save_router_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        planner_strategy=raw_planner_strategy,
        router_context_min=raw_router_context,
        reduced_context=reduced_context,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        parsed_output=parsed_output,
        task_bundle_index=task_bundle_index,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    # Instrument validation and phase end
    validation_result("router", validation_report, batch_id=normalized_batch_id,
                      round_id=normalized_round_id, hypothesis_id=hypothesis_id)
    phase_end("router", elapsed_s=duration_ms / 1000.0, batch_id=normalized_batch_id,
              round_id=normalized_round_id, hypothesis_id=hypothesis_id)

    return {
        "component_run": component_run,
        "planner_strategy": raw_planner_strategy,
        "router_context_min": raw_router_context,
        "reduced_context": reduced_context,
        "prompt_text": prompt_text,
        "raw_response_text": raw_response_text,
        "router_output": parsed_output,
        "parsed_output": parsed_output,
        "task_bundle_index": task_bundle_index,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }
