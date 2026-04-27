from utils.openai_response import extract_response_text


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
