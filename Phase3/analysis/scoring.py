"""Deterministic heuristic scoring for interpreted run insights."""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Any

from utils.metrics import collect_numeric_values as _collect_numeric_metrics


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _extract_signal_strength(insights: dict[str, Any]) -> dict[str, float]:
    feature_evidence = dict(insights.get("feature_evidence", {}))
    max_signal_count = 0.0
    max_anchor_count = 0.0
    max_abs_correlation = 0.0
    max_wasserstein = 0.0

    for evidence in feature_evidence.values():
        if not isinstance(evidence, dict):
            continue
        signals = list(evidence.get("signals", []) or [])
        metrics = dict(evidence.get("metrics", {}) or {})
        max_signal_count = max(max_signal_count, float(len(signals)))
        max_anchor_count = max(max_anchor_count, float(
            len(_collect_numeric_metrics(metrics))))

        correlation = metrics.get("correlation")
        wasserstein = metrics.get("wasserstein")
        if correlation is None:
            correlation = evidence.get("correlation")
        if wasserstein is None:
            wasserstein = evidence.get("wasserstein")
        if isinstance(correlation, (int, float)):
            max_abs_correlation = max(
                max_abs_correlation, abs(float(correlation)))
        if isinstance(wasserstein, (int, float)):
            max_wasserstein = max(max_wasserstein, float(wasserstein))

    return {
        "max_signal_count": max_signal_count,
        "max_anchor_count": max_anchor_count,
        "max_abs_correlation": max_abs_correlation,
        "max_wasserstein": max_wasserstein,
    }


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

    evidence_strength = _extract_signal_strength(insights)
    max_signal_count = evidence_strength["max_signal_count"]
    max_anchor_count = evidence_strength["max_anchor_count"]
    max_abs_correlation = evidence_strength["max_abs_correlation"]
    max_wasserstein = evidence_strength["max_wasserstein"]

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
    signal_score += 12.5 * _clamp(max_signal_count / 3.0, 0.0, 1.0)
    signal_score += 12.5 * _clamp(max_anchor_count / 4.0, 0.0, 1.0)

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
    if max_signal_count >= 2 or max_anchor_count >= 2:
        strengths.append(
            "collected structured evidence with signals and numeric anchors")

    if num_errors > 0:
        risks.append(f"encountered {num_errors} tool error(s)")
    if repeated_failures:
        risks.append("repeated failures for: " + ", ".join(repeated_failures))
    if unique_attempted <= 2:
        risks.append("exploration was narrow")
    if not confirmed_features:
        risks.append("no feature was fully confirmed")
    if max_signal_count < 1 or max_anchor_count < 1:
        risks.append("structured evidence remained weak")

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
            "max_signal_tags": int(max_signal_count),
            "max_numeric_anchors": int(max_anchor_count),
            "max_abs_correlation": round(max_abs_correlation, 4),
            "max_wasserstein": round(max_wasserstein, 4),
            "num_confirmed_features": len(confirmed_features),
            "num_errors": num_errors,
            "unique_features_attempted": unique_attempted,
            "unique_features_successful": unique_successful,
        },
        "strengths": strengths,
        "risks": risks,
        # Extended deterministic reasoning components (PROMPT 7)
        "reasoning_components": {
            "hypothesis_revision": compute_hypothesis_revision(insights),
            "counterevidence_usage": compute_counterevidence_usage(insights),
            "overview_dependence": compute_overview_dependence(insights),
            "exploration_diversity": compute_exploration_diversity(insights),
            "evidence_efficiency": compute_evidence_efficiency(insights),
        },
    }


def compute_hypothesis_revision(insights: dict[str, Any]) -> dict[str, float]:
    """Return counts and ratios for hypothesis revisions.

    Expects an `events` list in insights where hypothesis events look like:
      {"type": "hypothesis", "action": "create"|"update", "beneficial": bool}
    """
    events = list(insights.get("events", []))
    revisions = [e for e in events if e.get(
        "type") == "hypothesis" and e.get("action") in ("create", "update")]
    total = len(revisions)
    beneficial = sum(1 for e in revisions if e.get("beneficial"))
    ratio = _safe_ratio(beneficial, total)
    return {"total_revisions": float(total), "beneficial_revisions": float(beneficial), "beneficial_revision_ratio": round(ratio, 3)}


def compute_counterevidence_usage(insights: dict[str, Any]) -> dict[str, float]:
    """Measure how often counterevidence was seen and acted upon.

    Expects `counterevidence` dict: {"seen": int, "acted": int}
    """
    ce = dict(insights.get("counterevidence", {}))
    seen = int(ce.get("seen", 0) or 0)
    acted = int(ce.get("acted", 0) or 0)
    acted_ratio = _safe_ratio(acted, seen)
    return {"seen": float(seen), "acted": float(acted), "acted_ratio": round(acted_ratio, 3)}


def compute_overview_dependence(insights: dict[str, Any]) -> dict[str, float]:
    """How often the agent relied on overview content vs direct exploration.

    Expects `overview_usage` int and `behavior.num_steps`.
    """
    overview = int(insights.get("overview_usage", 0) or 0)
    num_steps = int(dict(insights.get("behavior", {})
                         ).get("num_steps", 0) or 0)
    dependence = _safe_ratio(overview, max(num_steps, 1))
    return {"overview_calls": float(overview), "num_steps": float(num_steps), "overview_dependence": round(dependence, 3)}


def compute_exploration_diversity(insights: dict[str, Any]) -> dict[str, float]:
    """Compute Shannon entropy over accessed features as diversity metric.

    Expects `feature_accesses` as a list of feature names accessed during the run.
    """
    accesses = list(insights.get("feature_accesses", []))
    if not accesses:
        return {"distinct_features": 0.0, "shannon_entropy": 0.0}
    counts = Counter(accesses)
    total = sum(counts.values())
    entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
    return {"distinct_features": float(len(counts)), "shannon_entropy": round(entropy, 3)}


def compute_evidence_efficiency(insights: dict[str, Any]) -> dict[str, float]:
    """Estimate evidence gained per tool call.

    Expects `evidence_signals` numeric aggregate and `tool_calls` int.
    """
    evidence_score = float(insights.get("evidence_signals", 0.0) or 0.0)
    tool_calls = int(insights.get("tool_calls", 0) or 0)
    efficiency = _safe_ratio(evidence_score, max(tool_calls, 1))
    return {"evidence_score": round(evidence_score, 3), "tool_calls": float(tool_calls), "evidence_efficiency": round(efficiency, 4)}


def baseline_deterministic(insights: dict[str, Any]) -> dict[str, Any]:
    """A simple deterministic heuristic baseline producing comparable scoring outputs."""
    # Use a lightweight rule: fewer steps and more confirmed features -> higher
    confirmed = len(dict(insights.get("patterns", {})
                         ).get("confirmed_features", []))
    num_steps = int(dict(insights.get("behavior", {})
                         ).get("num_steps", 0) or 0)
    score = 50.0 + min(confirmed * 8.0, 24.0) - min(num_steps, 10) * 1.0
    return {"baseline": "deterministic", "score": round(_clamp(score, 0.0, 100.0), 1)}


def baseline_random(insights: dict[str, Any], seed: int = 1, budget: int | None = None) -> dict[str, Any]:
    """A budget-matched random baseline (deterministic given seed).

    Returns a simple score summary. `budget` is a hint for number of calls.
    """
    rng = random.Random(seed)
    budget = int(budget if budget is not None else int(
        dict(insights.get("behavior", {})).get("num_steps", 1) or 1))
    # produce a deterministic pseudo-random score in a narrow band
    base = 40.0
    variance = rng.random() * 20.0
    penalty = min(max(0, budget - 5), 10) * 0.5
    score = base + variance - penalty
    return {"baseline": "random", "seed": int(seed), "budget": int(budget), "score": round(_clamp(score, 0.0, 100.0), 1)}
