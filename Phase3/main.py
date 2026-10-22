"""Main entrypoint for ATLAS batch runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from config import DATA_DIR
from phase3_runtime.orchestrator import run_phase3a_batch
from utils.openai_response import build_responses_create_kwargs, extract_response_text

DEFAULT_OBJECTIVE = (
    "Audit the dataset partition for potential design artefacts (determinism, "
    "redundancy, duplication, and suspicious distributional patterns) and "
    "produce a compact structured JSON of suspect features with supporting "
    "evidence."
)

PHASE3A_RUNTIME_COMPONENTS: tuple[str, ...] = (
    "semantic_extraction",
    "investigation_analysis",
    "hypothesis_ranking",
    "planner",
    "router",
    "worker",
    "aggregation",
    "state_manager",
    "critic",
    "final_batch_auditor",
    "final_batch_report",
    "round_report",
)


def _select_dataset_path(data_dir: str | Path) -> Path:
    selected_dataset = os.environ.get("NIDS_DATASET_PATH")
    if selected_dataset:
        dataset_path = Path(selected_dataset)
        if not dataset_path.is_absolute():
            dataset_path = Path(data_dir) / selected_dataset
        if not dataset_path.is_file():
            raise FileNotFoundError(
                f"Configured dataset '{dataset_path}' does not exist."
            )
        if dataset_path.suffix.lower() not in {".csv", ".tsv", ".tab"}:
            raise FileNotFoundError(
                f"Configured dataset '{dataset_path}' is not a CSV/TSV file."
            )
        return dataset_path

    candidates = sorted(
        path
        for path in Path(data_dir).rglob("*")
        if path.is_file() and path.suffix.lower() in {".csv", ".tsv", ".tab"}
    )
    if not candidates:
        raise FileNotFoundError(f"No CSV/TSV datasets found in '{data_dir}'.")
    return candidates[0]


def _build_openai_llm_callable(model_name: str, temperature: float):
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run the agent."
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


def _build_phase3a_llm_callables(
    model_name: str,
    temperature: float,
    component_model_names: dict[str, str] | None = None,
) -> dict[str, Callable[[str], str]]:
    component_models = dict(component_model_names or {})
    callable_cache: dict[str, Callable[[str], str]] = {}
    llm_callables: dict[str, Callable[[str], str]] = {}
    for component_name in PHASE3A_RUNTIME_COMPONENTS:
        target_model_name = str(component_models.get(component_name) or model_name).strip() or model_name
        if target_model_name not in callable_cache:
            callable_cache[target_model_name] = _build_openai_llm_callable(target_model_name, temperature)
        llm_callables[component_name] = callable_cache[target_model_name]
    return llm_callables


def build_phase3a_llm_callables(
    model_name: str,
    temperature: float,
    component_model_names: dict[str, str] | None = None,
) -> dict[str, Callable[[str], str]]:
    return _build_phase3a_llm_callables(
        model_name=model_name,
        temperature=temperature,
        component_model_names=component_model_names,
    )


def main() -> dict[str, object]:
    """Execute authoritative Phase 3A batch runtime as default entrypoint."""
    return main_phase3a_batch()


def main_phase3a_batch() -> dict[str, object]:
    """Wire dependencies and execute one authoritative Phase 3A batch runtime."""
    dataset_path = _select_dataset_path(DATA_DIR)
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    temperature = float(os.environ.get("OPENAI_TEMPERATURE", "0.0"))
    max_rounds = int(os.environ.get("PHASE3A_MAX_ROUNDS", "3"))
    max_concurrent_workers_value = os.environ.get("PHASE3A_MAX_CONCURRENT_WORKERS")
    max_concurrent_hypotheses_value = os.environ.get("PHASE3A_MAX_CONCURRENT_HYPOTHESES")
    planning_model_name = os.environ.get("PHASE3A_PLANNING_MODEL")
    worker_model_name = os.environ.get("PHASE3A_WORKER_MODEL")
    synthesis_model_name = os.environ.get("PHASE3A_SYNTHESIS_MODEL")
    execution_mode = os.environ.get("PHASE3A_EXECUTION_MODE", "full_batch")
    enable_critic = os.environ.get("PHASE3A_ENABLE_CRITIC", "0") != "0"
    batch_id = os.environ.get("PHASE3A_BATCH_ID")
    log_dir = os.environ.get("PHASE3A_LOG_DIR")

    component_model_names = {
        component_name: target_model
        for component_name, target_model in {
            "investigation_analysis": planning_model_name,
            "hypothesis_ranking": planning_model_name,
            "planner": planning_model_name,
            "router": planning_model_name,
            "worker": worker_model_name,
            "aggregation": synthesis_model_name,
            "state_manager": synthesis_model_name,
            "critic": synthesis_model_name,
            "final_batch_auditor": synthesis_model_name,
            "final_batch_report": synthesis_model_name,
            "round_report": synthesis_model_name,
        }.items()
        if str(target_model or "").strip()
    }

    return run_phase3a_batch(
        dataset_path,
        batch_id=batch_id,
        model_name=model_name,
        temperature=temperature,
        max_rounds=max_rounds,
        max_concurrent_workers=(int(max_concurrent_workers_value) if max_concurrent_workers_value else None),
        max_concurrent_hypotheses=(int(max_concurrent_hypotheses_value) if max_concurrent_hypotheses_value else None),
        execution_mode=execution_mode,
        enable_critic=enable_critic,
        log_dir=log_dir,
        caller_mode="main",
        llm_callables=_build_phase3a_llm_callables(model_name, temperature, component_model_names),
        component_model_names=component_model_names,
    )


if __name__ == "__main__":
    main()
