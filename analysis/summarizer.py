"""Human-readable deterministic summaries for interpreted run insights."""

from __future__ import annotations

from typing import Any


def _format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _describe_feature(feature_name: str, feature_evidence: dict[str, dict[str, float | None]]) -> str:
    evidence = feature_evidence.get(feature_name, {})
    correlation = _format_value(evidence.get("correlation"))
    wasserstein = _format_value(evidence.get("wasserstein"))
    return (
        f"- {feature_name}: correlation={correlation}, "
        f"wasserstein={wasserstein}"
    )


def _build_key_findings(insights: dict[str, Any]) -> list[str]:
    top_features = list(insights.get("top_features", []))
    strong_features = list(insights.get("strong_features", []))
    feature_evidence = dict(insights.get("feature_evidence", {}))

    lines = []
    if top_features:
        lines.append("Top features identified:")
        lines.extend(_describe_feature(feature_name, feature_evidence)
                     for feature_name in top_features)
    else:
        lines.append("No top features were identified.")

    if strong_features:
        strongest_feature = max(
            strong_features,
            key=lambda name: abs(feature_evidence.get(
                name, {}).get("wasserstein") or 0.0),
        )
        strongest_evidence = feature_evidence.get(strongest_feature, {})
        lines.append(
            "Strongest confirmed feature: "
            f"{strongest_feature} with correlation={_format_value(strongest_evidence.get('correlation'))}, "
            f"wasserstein={_format_value(strongest_evidence.get('wasserstein'))}"
        )
    else:
        lines.append("No feature was confirmed with both tools.")
    return lines


def _build_behavior_analysis(insights: dict[str, Any]) -> list[str]:
    behavior = dict(insights.get("behavior", {}))
    patterns = dict(insights.get("patterns", {}))
    confirmed_features = list(patterns.get("confirmed_features", []))
    reacted_to_errors = bool(patterns.get("reacted_to_errors", False))

    return [
        "Hypothesis confirmation: "
        + ("yes, it confirmed features with both tools." if confirmed_features else "no, it did not confirm any feature with both tools."),
        "Tool usage: "
        + ("it used both tools during the run." if behavior.get("used_both_tools")
           else "it relied on a single tool."),
        "Error reaction: "
        + ("it changed course after an error." if reacted_to_errors else "it did not clearly react to errors."),
    ]


def _build_error_lines(insights: dict[str, Any]) -> list[str]:
    errors = list(insights.get("errors", []))
    repeated_failures = list(insights.get(
        "patterns", {}).get("repeated_failures", []))

    if not errors:
        return ["No tool errors were recorded."]

    lines = [
        f"- {error.get('feature_name')}: {error.get('error_code')}"
        for error in errors
    ]
    if repeated_failures:
        lines.append(
            "Repeated failures detected for: " + ", ".join(repeated_failures)
        )
    else:
        lines.append("No repeated failures were detected.")
    return lines


def _build_conclusion(insights: dict[str, Any]) -> str:
    behavior = dict(insights.get("behavior", {}))
    confirmed_features = list(insights.get(
        "patterns", {}).get("confirmed_features", []))
    errors = list(insights.get("errors", []))

    reasoning_quality = "good" if confirmed_features else "limited"
    tool_usage = "balanced" if behavior.get("used_both_tools") else "narrow"
    limitations = "errors were handled but still present" if errors else "no major limitations observed in this run"
    return (
        f"Reasoning quality appears {reasoning_quality}. "
        f"Tool usage is {tool_usage}. "
        f"Main limitation: {limitations}."
    )


def generate_summary(insights: dict[str, Any]) -> str:
    """Render interpreted run insights as a human-readable summary."""
    behavior = dict(insights.get("behavior", {}))

    sections = [
        "RUN SUMMARY",
        f"- Steps: {behavior.get('num_steps', 0)}",
        f"- Features attempted: {behavior.get('unique_features_attempted', 0)}",
        f"- Features successful: {behavior.get('unique_features_successful', 0)}",
        f"- Errors: {behavior.get('num_errors', 0)}",
        "",
        "KEY FINDINGS",
        *(_build_key_findings(insights)),
        "",
        "BEHAVIOR ANALYSIS",
        *(_build_behavior_analysis(insights)),
        "",
        "ERRORS",
        *(_build_error_lines(insights)),
        "",
        "CONCLUSION",
        _build_conclusion(insights),
    ]
    return "\n".join(sections)
