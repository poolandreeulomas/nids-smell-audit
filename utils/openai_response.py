"""Helpers for extracting text from OpenAI Responses API objects."""

from __future__ import annotations

from typing import Any


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
