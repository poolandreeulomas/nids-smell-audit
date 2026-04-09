"""Deterministic interpretation layer for agent run logs."""

from __future__ import annotations

from typing import Any


def _get_feature_name(step: dict[str, Any]) -> str | None:
    action_input = step.get("action_input") or {}
    feature_name = action_input.get("feature_name")
    return feature_name if isinstance(feature_name, str) and feature_name else None


def _extract_feature_evidence(analyzed_features: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    evidence_map: dict[str, dict[str, float | None]] = {}
    for feature_name, evidence in analyzed_features.items():
        if not isinstance(feature_name, str) or not isinstance(evidence, dict):
            continue
        correlation = evidence.get("correlation")
        wasserstein = evidence.get("wasserstein")
        evidence_map[feature_name] = {
            "correlation": float(correlation) if isinstance(correlation, (int, float)) else None,
            "wasserstein": float(wasserstein) if isinstance(wasserstein, (int, float)) else None,
        }
    return evidence_map


def extract_run_insights(run_json: dict[str, Any]) -> dict[str, Any]:
    """Convert raw run payload into structured deterministic insights."""
    history = list(run_json.get("history", []))
    analyzed_features = dict(run_json.get("analyzed_features", {}))
    top_features = list(run_json.get("promising_features", []))[:3]

    feature_evidence = _extract_feature_evidence(analyzed_features)
    strong_features = [
        feature_name
        for feature_name, evidence in analyzed_features.items()
        if isinstance(evidence, dict) and len(set(evidence.get("tools_used", []))) >= 2
    ]

    errors: list[dict[str, str | None]] = []
    failed_features: list[str] = []
    attempted_features: set[str] = set()
    successful_features: set[str] = set()
    tools_seen: set[str] = set()

    failure_counts: dict[str, int] = {}
    reacted_to_errors = False
    previous_failed_feature: str | None = None

    for step in history:
        feature_name = _get_feature_name(step)
        status = step.get("execution_status")
        action = step.get("action")
        observation = step.get("observation") or {}

        if isinstance(action, str) and action:
            tools_seen.add(action)
        if feature_name:
            attempted_features.add(feature_name)
        if status == "OK" and feature_name:
            successful_features.add(feature_name)

        if status == "TOOL_ERROR":
            error_code = observation.get("error_code")
            errors.append(
                {
                    "feature_name": feature_name,
                    "error_code": error_code if isinstance(error_code, str) else None,
                }
            )
            if feature_name:
                failed_features.append(feature_name)
                failure_counts[feature_name] = failure_counts.get(
                    feature_name, 0) + 1
                previous_failed_feature = feature_name
            continue

        if previous_failed_feature and feature_name and feature_name != previous_failed_feature:
            reacted_to_errors = True
        previous_failed_feature = None

    repeated_failures = sorted(
        feature_name for feature_name, count in failure_counts.items() if count > 1
    )
    confirmed_features = sorted(strong_features)

    return {
        "top_features": top_features,
        "strong_features": confirmed_features,
        "feature_evidence": feature_evidence,
        "errors": errors,
        "behavior": {
            "used_both_tools": len(tools_seen) >= 2,
            "num_steps": len(history),
            "num_errors": len(errors),
            "unique_features_attempted": len(attempted_features),
            "unique_features_successful": len(successful_features),
        },
        "patterns": {
            "confirmed_features": confirmed_features,
            "failed_features": failed_features,
            "repeated_failures": repeated_failures,
            "reacted_to_errors": reacted_to_errors,
        },
    }
