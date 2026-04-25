"""Shared helpers for concise human-readable CLI and trace text."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def format_number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{float(value):.3f}"


def first_metric_text(metrics: dict[str, Any]) -> str | None:
    preferred = (
        "js_divergence",
        "correlation",
        "cardinality_ratio",
        "duplicate_ratio",
        "unique_values",
    )
    for key in preferred:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"{key}={format_number(value)}"

    for key, value in metrics.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"{key}={format_number(value)}"
    return None


def parse_thought_fields(thought: str | None) -> dict[str, str]:
    if not isinstance(thought, str) or not thought.strip():
        return {}

    fields: dict[str, str] = {}
    for chunk in thought.split(" | "):
        label, separator, value = chunk.partition(":")
        if not separator:
            continue
        normalized_label = label.strip().lower().replace(" ", "_")
        normalized_value = value.strip()
        if normalized_value:
            fields[normalized_label] = normalized_value
    return fields


def summarize_action(action: str | None, action_input: dict[str, Any] | None) -> str:
    if not isinstance(action, str) or not action:
        return "No valid action was executed."

    payload = action_input or {}
    feature_name = payload.get("feature_name") or "dataset"
    related_feature = payload.get(
        "feature_name_2") or payload.get("related_feature_name")
    if related_feature:
        return f"{action} on {feature_name} and {related_feature}"
    return f"{action} on {feature_name}"


def split_bullet_lines(text: str | Iterable[str]) -> list[str]:
    if isinstance(text, str):
        raw_lines = text.splitlines()
    else:
        raw_lines = [str(line) for line in text]

    lines: list[str] = []
    for line in raw_lines:
        normalized = line.strip()
        if not normalized:
            continue
        if normalized.startswith(("- ", "* ")):
            normalized = normalized[2:].strip()
        lines.append(normalized)
    return lines


def summarize_observation(observation: dict[str, Any], *, failure_noun: str = "action") -> str:
    if not isinstance(observation, dict):
        return "No interpretable observation was produced."

    if not observation.get("ok", False):
        error_code = observation.get("error_code") or "UNKNOWN"
        error_message = observation.get(
            "error_message") or "no additional detail"
        return f"The {failure_noun} failed ({error_code}): {error_message}."

    evidence = observation.get("evidence") or {}
    signals = [
        str(signal).replace("_", " ")
        for signal in (evidence.get("signals") or [])
        if isinstance(signal, str)
    ]
    metric_text = first_metric_text(dict(evidence.get("metrics", {}) or {}))

    if signals and metric_text:
        return f"Found {signals[0]} with {metric_text}."
    if signals:
        return f"Found {signals[0]}."
    if metric_text:
        return f"Measured {metric_text}."
    if observation.get("value") is not None:
        return f"Measured value={format_number(observation.get('value'))}."
    return "The action completed without a clear signal."
