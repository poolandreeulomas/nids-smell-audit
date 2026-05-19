"""Strict parser for MVP ReAct model output."""

from __future__ import annotations

import json
from typing import Any


def _parse_error(
    error_code: str,
    error_message: str,
    raw_output: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "thought": None,
        "action": None,
        "action_input": None,
        "error_code": error_code,
        "error_message": error_message,
        "raw_output": raw_output,
    }


def parse_react_output(text: str) -> dict[str, Any]:
    """Parse strict three-line ReAct output.

    Expected format:
    THOUGHT: ...
    ACTION: ...
    ACTION_INPUT: {"feature_name": "..."}
    """
    lines = [line.rstrip()
             for line in text.strip().splitlines() if line.strip()]

    if len(lines) != 3:
        return _parse_error(
            "PARSE_ERROR",
            "Model output must contain exactly 3 non-empty lines.",
            text,
        )

    expected_prefixes = ["THOUGHT:", "ACTION:", "ACTION_INPUT:"]
    for line, prefix in zip(lines, expected_prefixes, strict=True):
        if not line.startswith(prefix):
            return _parse_error(
                "PARSE_ERROR",
                f"Expected line prefix '{prefix}'.",
                text,
            )

    thought = lines[0][len("THOUGHT:"):].strip()
    action = lines[1][len("ACTION:"):].strip()
    action_input_text = lines[2][len("ACTION_INPUT:"):].strip()

    if not thought:
        return _parse_error("PARSE_ERROR", "THOUGHT cannot be empty.", text)
    if not action:
        return _parse_error("PARSE_ERROR", "ACTION cannot be empty.", text)

    try:
        action_input = json.loads(action_input_text)
    except json.JSONDecodeError as exc:
        return _parse_error(
            "INVALID_JSON",
            f"ACTION_INPUT is not valid JSON: {exc.msg}",
            text,
        )

    if not isinstance(action_input, dict):
        return _parse_error(
            "PARSE_ERROR",
            "ACTION_INPUT must decode to a JSON object.",
            text,
        )

    if set(action_input.keys()) != {"feature_name"}:
        return _parse_error(
            "PARSE_ERROR",
            "ACTION_INPUT must contain exactly one key: 'feature_name'.",
            text,
        )

    feature_name = action_input.get("feature_name")
    if not isinstance(feature_name, str) or not feature_name.strip():
        return _parse_error(
            "PARSE_ERROR",
            "ACTION_INPUT.feature_name must be a non-empty string.",
            text,
        )

    return {
        "ok": True,
        "thought": thought,
        "action": action,
        "action_input": {"feature_name": feature_name},
        "error_code": None,
        "error_message": None,
        "raw_output": text,
    }
