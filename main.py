"""Main entrypoint for one MVP agent run."""

from __future__ import annotations

import os
from pathlib import Path

from agent.loop import run_agent
from config import DATA_DIR, MAX_STEPS
from data.dataset_config import get_default_dataset_config
from data.loader import load_dataset
from src.feature_index import build_compact_feature_index
from state.schema import AgentState
from state.store import init_state
from tools.registry import get_tool_registry
from utils.openai_response import build_responses_create_kwargs, extract_response_text

DEFAULT_OBJECTIVE = (
    "Audit the dataset partition for potential design artefacts (determinism, "
    "redundancy, duplication, and suspicious distributional patterns) and "
    "produce a compact structured JSON of suspect features with supporting "
    "evidence."
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
        for path in Path(data_dir).iterdir()
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


def main() -> AgentState:
    """Wire dependencies and execute one bounded MVP run."""
    dataset_config = get_default_dataset_config()
    dataset_path = _select_dataset_path(DATA_DIR)
    dataset_frame, available_features = load_dataset(
        dataset_path, dataset_config)
    tool_names = list(get_tool_registry().keys())

    model_name = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    model_version = os.environ.get("OPENAI_MODEL_VERSION")
    temperature = float(os.environ.get("OPENAI_TEMPERATURE", "0.0"))
    trace = os.environ.get("REACT_TRACE", "1") != "0"
    seed_value = os.environ.get("OPENAI_SEED")
    seed = int(seed_value) if seed_value else None
    max_steps_value = os.environ.get("NIDS_MAX_STEPS")
    max_steps = int(max_steps_value) if max_steps_value else MAX_STEPS

    state = init_state(
        run_id="run_local",
        objective=os.environ.get("NIDS_OBJECTIVE", DEFAULT_OBJECTIVE),
        max_steps=max_steps,
        available_features=available_features,
        metadata={
            "compact_feature_index": build_compact_feature_index(
                dataset_frame,
                label_col=dataset_config.label_column,
            )
        },
    )

    llm_callable = _build_openai_llm_callable(model_name, temperature)
    return run_agent(
        state=state,
        llm_callable=llm_callable,
        dataset_path=dataset_path,
        dataset_config=dataset_config,
        tool_names=tool_names,
        model_name=model_name,
        model_version=model_version,
        temperature=temperature,
        seed=seed,
        top_p=None,
        repo_path=Path(__file__).resolve().parent,
        dataset_frame=dataset_frame,
        valid_numeric_features=available_features,
        trace=trace,
    )


if __name__ == "__main__":
    main()
