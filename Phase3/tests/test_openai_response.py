import os

from utils.openai_response import (
    build_responses_create_kwargs,
    extract_response_text,
    load_local_dotenv,
)


class _DummyText:
    def __init__(self, text: str):
        self.type = "output_text"
        self.text = text


class _DummyReasoning:
    type = "reasoning"


class _DummyMessage:
    def __init__(self, *texts: str):
        self.type = "message"
        self.content = [_DummyText(text) for text in texts]


class _DummyResponse:
    def __init__(self, outputs, output_text: str = ""):
        self.output = list(outputs)
        self.output_text = output_text


def test_extract_response_text_returns_single_output_block():
    block = (
        "THOUGHT: test\n"
        "ACTION: feature_summary\n"
        'ACTION_INPUT: {"feature_name":"Destination Port"}'
    )

    response = _DummyResponse([_DummyMessage(block)], output_text=block)

    assert extract_response_text(response) == block


def test_extract_response_text_deduplicates_identical_blocks():
    block = (
        "THOUGHT: test\n"
        "ACTION: feature_summary\n"
        'ACTION_INPUT: {"feature_name":"Destination Port"}'
    )

    response = _DummyResponse(
        [_DummyMessage(block), _DummyMessage(block)],
        output_text=block + block,
    )

    assert extract_response_text(response) == block


def test_extract_response_text_preserves_distinct_blocks():
    first = "first block"
    second = "second block"
    response = _DummyResponse(
        [_DummyMessage(first), _DummyMessage(second)],
        output_text=first + second,
    )

    assert extract_response_text(response) == first + second


def test_extract_response_text_falls_back_to_sdk_output_text():
    response = _DummyResponse([_DummyReasoning()], output_text="fallback")

    assert extract_response_text(response) == "fallback"


def test_build_responses_create_kwargs_keeps_temperature_for_supported_models():
    kwargs = build_responses_create_kwargs(
        model_name="gpt-5.4",
        prompt_text="hello",
        temperature=0.0,
    )

    assert kwargs == {
        "model": "gpt-5.4",
        "input": "hello",
        "temperature": 0.0,
    }


def test_build_responses_create_kwargs_omits_temperature_for_gpt55():
    kwargs = build_responses_create_kwargs(
        model_name="gpt-5.5",
        prompt_text="hello",
        temperature=0.0,
    )

    assert kwargs == {
        "model": "gpt-5.5",
        "input": "hello",
    }


def test_load_local_dotenv_loads_nearest_env_file(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    nested_dir = repo_root / "phase3" / "utils"
    nested_dir.mkdir(parents=True)
    env_path = repo_root / ".env"
    env_path.write_text("PHASE3_TEST_DOTENV=loaded\n", encoding="utf-8")
    monkeypatch.delenv("PHASE3_TEST_DOTENV", raising=False)

    loaded_path = load_local_dotenv(nested_dir / "openai_response.py")

    assert loaded_path == env_path
    assert os.environ["PHASE3_TEST_DOTENV"] == "loaded"


def test_load_local_dotenv_returns_none_when_not_found(tmp_path, monkeypatch):
    nested_dir = tmp_path / "phase3" / "utils"
    nested_dir.mkdir(parents=True)
    monkeypatch.delenv("PHASE3_TEST_DOTENV", raising=False)

    loaded_path = load_local_dotenv(nested_dir / "openai_response.py")

    assert loaded_path is None
