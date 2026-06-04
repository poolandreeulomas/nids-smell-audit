"""Helpers for extracting text from OpenAI Responses API objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_local_dotenv(start_path: str | Path | None = None) -> Path | None:
    """Load the nearest repo-local .env file without overriding shell vars."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    anchor = Path(start_path or __file__).resolve()
    search_root = anchor if anchor.is_dir() else anchor.parent

    for candidate_dir in (search_root, *search_root.parents):
        candidate = candidate_dir / ".env"
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    return None


_LOADED_DOTENV_PATH = load_local_dotenv()


_RESPONSES_MODELS_WITHOUT_TEMPERATURE_PREFIXES = (
    # Exclude all GPT-5 family models from receiving the `temperature`
    # parameter since newer GPT-5 variants may reject it at the transport
    # layer. Matching on the prefix `gpt-5` covers `gpt-5-mini`,
    # `gpt-5.5`, and other GPT-5 variants.
    "gpt-5",
)


def build_responses_create_kwargs(
    *,
    model_name: str,
    prompt_text: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Build OpenAI Responses API kwargs with model-specific compatibility.

    Some models reject parameters that older models accept. Keep the request
    shape minimal for those cases so runs fail less often on transport-level
    incompatibilities.
    """

    kwargs: dict[str, Any] = {
        "model": model_name,
        "input": prompt_text,
    }
    if temperature is None:
        return kwargs

    normalized_model = model_name.strip().lower()
    if normalized_model.startswith(_RESPONSES_MODELS_WITHOUT_TEMPERATURE_PREFIXES):
        return kwargs

    kwargs["temperature"] = temperature
    return kwargs


def _iter_output_text_blocks(response: Any) -> list[str]:
    blocks: list[str] = []

    for output in list(getattr(response, "output", []) or []):
        if getattr(output, "type", None) != "message":
            continue

        for content in list(getattr(output, "content", []) or []):
            if getattr(content, "type", None) != "output_text":
                continue

            text = getattr(content, "text", None)
            if isinstance(text, str) and text.strip():
                blocks.append(text)

    return blocks


def extract_response_text(response: Any) -> str:
    """Return text content while collapsing exact duplicate text blocks.

    The SDK's ``response.output_text`` concatenates every ``output_text`` block
    from every message output with no separator. For strict text protocols, that
    can turn a duplicated assistant reply into an unparsable flat string.
    """

    text_blocks = _iter_output_text_blocks(response)
    if not text_blocks:
        output_text = getattr(response, "output_text", "")
        return output_text if isinstance(output_text, str) else ""

    normalized_blocks = [block.strip() for block in text_blocks]
    if len(normalized_blocks) > 1 and len(set(normalized_blocks)) == 1:
        return text_blocks[0]

    return "".join(text_blocks)
