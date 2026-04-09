"""Deterministic heuristic scoring for interpreted run insights."""

from __future__ import annotations

from typing import Any


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _extract_signal_strength(insights: dict[str, Any]) -> tuple[float, float]:
    feature_evidence = dict(insights.get("feature_evidence", {}))
    max_abs_correlation = 0.0
    max_wasserstein = 0.0

    for evidence in feature_evidence.values():
        if not isinstance(evidence, dict):
            continue
        correlation = evidence.get("correlation")
        wasserstein = evidence.get("wasserstein")
        if isinstance(correlation, (int, float)):
            max_abs_correlation = max(
                max_abs_correlation, abs(float(correlation)))
        if isinstance(wasserstein, (int, float)):
            max_wasserstein = max(max_wasserstein, float(wasserstein))

    return max_abs_correlation, max_wasserstein


def score_run(insights: dict[str, Any]) -> dict[str, Any]:
    """Score one run out of 100 using a transparent deterministic heuristic."""
    behavior = dict(insights.get("behavior", {}))
    patterns = dict(insights.get("patterns", {}))
    top_features = list(insights.get("top_features", []))
    errors = list(insights.get("errors", []))

    num_steps = int(behavior.get("num_steps", 0) or 0)
    num_errors = int(behavior.get("num_errors", 0) or 0)
    unique_attempted = int(behavior.get("unique_features_attempted", 0) or 0)
    unique_successful = int(behavior.get("unique_features_successful", 0) or 0)
    used_both_tools = bool(behavior.get("used_both_tools", False))
    strong_features = list(insights.get("strong_features", []))
    confirmed_features = list(patterns.get("confirmed_features", []))
    repeated_failures = list(patterns.get("repeated_failures", []))
    reacted_to_errors = bool(patterns.get("reacted_to_errors", False))

    max_abs_correlation, max_wasserstein = _extract_signal_strength(insights)

    execution_score = 0.0
    execution_score += 10.0 * _clamp(_safe_ratio(num_steps, 5.0), 0.0, 1.0)
    execution_score += 15.0 * \
        _safe_ratio(num_steps - num_errors, max(num_steps, 1))

    reasoning_score = 0.0
    if used_both_tools:
        reasoning_score += 8.0
    reasoning_score += min(float(len(confirmed_features)) * 9.0, 9.0)
    if num_errors == 0:
        reasoning_score += 8.0
    elif reacted_to_errors:
        reasoning_score += 8.0

    exploration_score = 0.0
    exploration_score += min(unique_attempted * 2.0, 8.0)
    exploration_score += min(unique_successful * (7.0 / 3.0), 7.0)

    signal_score = 0.0
    signal_score += 12.5 * _clamp(max_abs_correlation / 0.40, 0.0, 1.0)
    signal_score += 12.5 * _clamp(max_wasserstein / 0.80, 0.0, 1.0)

    penalty_score = 0.0
    if not repeated_failures:
        penalty_score += 5.0
    if top_features:
        penalty_score += 5.0
    penalty_score -= min(float(len(errors)) * 3.0, 10.0)
    penalty_score = _clamp(penalty_score, 0.0, 10.0)

    total_score = execution_score + reasoning_score + \
        exploration_score + signal_score + penalty_score
    total_score = round(_clamp(total_score, 0.0, 100.0), 1)

    if total_score >= 85.0:
        verdict = "strong"
    elif total_score >= 70.0:
        verdict = "promising"
    elif total_score >= 50.0:
        verdict = "mixed"
    else:
        verdict = "weak"

    strengths: list[str] = []
    risks: list[str] = []

    if strong_features:
        strengths.append(
            "confirmed features with both tools: " + ", ".join(strong_features)
        )
    if used_both_tools:
        strengths.append("used both tools during the run")
    if reacted_to_errors:
        strengths.append("adapted after a tool error")
    if max_abs_correlation >= 0.30 or max_wasserstein >= 0.50:
        strengths.append("found at least one strong signal")

    if num_errors > 0:
        risks.append(f"encountered {num_errors} tool error(s)")
    if repeated_failures:
        risks.append("repeated failures for: " + ", ".join(repeated_failures))
    if unique_attempted <= 2:
        risks.append("exploration was narrow")
    if not confirmed_features:
        risks.append("no feature was fully confirmed")
    if max_abs_correlation < 0.15 and max_wasserstein < 0.20:
        risks.append("signal strength remained weak")

    return {
        "score": total_score,
        "verdict": verdict,
        "breakdown": {
            "execution": round(execution_score, 1),
            "reasoning": round(reasoning_score, 1),
            "exploration": round(exploration_score, 1),
            "signal": round(signal_score, 1),
            "stability_bonus": round(penalty_score, 1),
        },
        "evidence": {
            "max_abs_correlation": round(max_abs_correlation, 4),
            "max_wasserstein": round(max_wasserstein, 4),
            "num_confirmed_features": len(confirmed_features),
            "num_errors": num_errors,
            "unique_features_attempted": unique_attempted,
            "unique_features_successful": unique_successful,
        },
        "strengths": strengths,
        "risks": risks,
    }
