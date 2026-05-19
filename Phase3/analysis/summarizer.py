"""Human-readable deterministic summaries for interpreted run insights."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any


def _format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _describe_feature(feature_name: str, feature_evidence: dict[str, dict[str, float | None]]) -> str:
    evidence = feature_evidence.get(feature_name, {})
    tools = ", ".join(evidence.get("tools_used", []) or []) or "none"
    signals = "; ".join(evidence.get("signals", []) or []) or "none"
    metrics = dict(evidence.get("metrics", {}) or {})
    top_metric = next(
        (f"{k}={_format_value(v)}" for k,
         v in metrics.items() if isinstance(v, (int, float))),
        "none",
    )
    return f"- {feature_name}: tools=[{tools}], signals=[{signals}], top_metric={top_metric}"


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
            key=lambda name: int(feature_evidence.get(
                name, {}).get("anchor_count") or 0),
        )
        strongest_evidence = feature_evidence.get(strongest_feature, {})
        tools = ", ".join(strongest_evidence.get(
            "tools_used", []) or []) or "none"
        lines.append(
            f"Strongest confirmed feature: {strongest_feature} "
            f"(tools=[{tools}], anchors={strongest_evidence.get('anchor_count', 0)})"
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


def _build_reasoning_metrics(insights: dict[str, Any]) -> list[str]:
    events = list(insights.get("events", []))
    hyp_revisions = sum(1 for e in events if e.get("type") == "hypothesis")
    ce = dict(insights.get("counterevidence", {}))
    ce_seen = int(ce.get("seen", 0) or 0)
    ce_acted = int(ce.get("acted", 0) or 0)
    overview = int(insights.get("overview_usage", 0) or 0)
    accesses = list(insights.get("feature_accesses", []))
    distinct = len(set(accesses))
    # Compute Shannon entropy directly from feature_accesses (same logic as scoring)
    if accesses:
        counts = Counter(accesses)
        total = sum(counts.values())
        entropy = -sum((c / total) * math.log2(c / total)
                       for c in counts.values())
    else:
        entropy = 0.0
    evidence_eff = float(insights.get("evidence_signals", 0.0) or 0.0)

    return [
        "REASONING METRICS:",
        f"- Hypothesis revisions: {hyp_revisions}",
        f"- Counterevidence seen/acted: {ce_seen}/{ce_acted}",
        f"- Overview calls: {overview}",
        f"- Distinct features accessed: {distinct}",
        f"- Exploration entropy: {entropy:.3f}",
        f"- Evidence efficiency: {evidence_eff:.3f}",
    ]


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
        *(_build_reasoning_metrics(insights)),
        "CONCLUSION",
        _build_conclusion(insights),
    ]
    return "\n".join(sections)
