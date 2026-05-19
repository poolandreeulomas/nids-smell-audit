"""Deterministic interpretation layer for agent run logs."""

from __future__ import annotations

from typing import Any

from utils.metrics import collect_numeric_values as _collect_numeric_metrics


def _get_feature_name(step: dict[str, Any]) -> str | None:
    action_input = step.get("action_input") or {}
    feature_name = action_input.get("feature_name")
    return feature_name if isinstance(feature_name, str) and feature_name else None


def _extract_feature_evidence(run_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence_map: dict[str, dict[str, Any]] = {}

    evidence_by_feature = dict(run_json.get("evidence_by_feature", {}) or {})
    for feature_name, blocks in evidence_by_feature.items():
        if not isinstance(feature_name, str) or not isinstance(blocks, list) or not blocks:
            continue

        signals: list[str] = []
        metrics: dict[str, Any] = {}
        support: dict[str, Any] = {}
        tools_used: list[str] = []
        status = None
        seen_signals: set[str] = set()
        seen_tools: set[str] = set()

        for block in blocks:
            if not isinstance(block, dict):
                continue
            for signal in block.get("signals", []) or []:
                if isinstance(signal, str) and signal not in seen_signals:
                    seen_signals.add(signal)
                    signals.append(signal)
            block_metrics = block.get("metrics") or {}
            if isinstance(block_metrics, dict):
                metrics.update(block_metrics)
            block_support = block.get("support") or {}
            if isinstance(block_support, dict) and block_support:
                support = dict(block_support)
            provenance = block.get("provenance") or {}
            if isinstance(provenance, dict):
                tool_name = provenance.get("tool")
                if isinstance(tool_name, str) and tool_name and tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    tools_used.append(tool_name)
            if block.get("status"):
                status = block.get("status")

        evidence_map[feature_name] = {
            "signals": signals,
            "metrics": metrics,
            "support": support,
            "status": status,
            "tools_used": tools_used,
            "anchor_count": len(_collect_numeric_metrics(metrics)),
        }

    if evidence_map:
        return evidence_map

    analyzed_features = dict(run_json.get("analyzed_features", {}) or {})
    for feature_name, evidence in analyzed_features.items():
        if not isinstance(feature_name, str) or not isinstance(evidence, dict):
            continue
        metrics: dict[str, Any] = {}
        if isinstance(evidence.get("correlation"), (int, float)):
            metrics["correlation"] = float(evidence["correlation"])
        if isinstance(evidence.get("wasserstein"), (int, float)):
            metrics["wasserstein"] = float(evidence["wasserstein"])
        evidence_map[feature_name] = {
            "signals": [],
            "metrics": metrics,
            "support": {},
            "status": None,
            "tools_used": list(evidence.get("tools_used", []) or []),
            "anchor_count": len(_collect_numeric_metrics(metrics)),
        }
    return evidence_map


def extract_run_insights(run_json: dict[str, Any]) -> dict[str, Any]:
    """Convert raw run payload into structured deterministic insights."""
    history = list(run_json.get("history", []))
    analyzed_features = dict(run_json.get("analyzed_features", {}))
    top_features = list(run_json.get("promising_features", []))[:3]

    feature_evidence = _extract_feature_evidence(run_json)
    strong_features = [
        feature_name
        for feature_name, evidence in feature_evidence.items()
        if isinstance(evidence, dict) and len(set(evidence.get("tools_used", []))) >= 2
    ]

    errors: list[dict[str, str | None]] = []
    failed_features: list[str] = []
    attempted_features: set[str] = set()
    successful_features: set[str] = set()
    tools_seen: set[str] = set()
    feature_accesses: list[str] = []
    tool_call_count: int = 0

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
        # record feature accesses for exploration diversity
        if feature_name:
            feature_accesses.append(feature_name)
        # count tool calls (any executed step with an action and status)
        if isinstance(action, str) and action and status:
            tool_call_count += 1
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

    # Aggregated signals for PROMPT 7 evaluation
    # evidence_signals: a deterministic numeric summary of available evidence
    evidence_score = 0.0
    for ev in feature_evidence.values():
        if not isinstance(ev, dict):
            continue
        evidence_score += float(len(ev.get("signals", []) or []))
        evidence_score += float(ev.get("anchor_count", 0)) * 0.25

    # counterevidence: derive from contradiction memory if present
    contradiction_memory = list(run_json.get("contradiction_memory", []))
    ce_seen = len(contradiction_memory)
    ce_acted = sum(1 for r in contradiction_memory if r.get("evidence_refs"))

    # events: synthesize hypothesis events from metadata.hypothesis_history when available
    events: list[dict[str, Any]] = []
    metadata = dict(run_json.get("metadata", {}) or {})
    hyp_hist = list(metadata.get("hypothesis_history", []) or [])
    for i, entry in enumerate(hyp_hist):
        try:
            step_id = int(entry.get("step", i))
        except Exception:
            step_id = i
        beneficial = False
        if i > 0:
            beneficial = any(
                int(record.get("step", -1) or -1) <= step_id
                for record in contradiction_memory
                if isinstance(record, dict)
            )
        events.append({"type": "hypothesis", "action": "create" if i ==
                      0 else "update", "step": step_id, "hypothesis": entry.get("hypothesis"), "beneficial": beneficial})

    overview_usage = int(metadata.get(
        "overview_usage", run_json.get("overview_usage", 0)) or 0)

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
        # PROMPT 7 instrumentation fields
        "events": events,
        "counterevidence": {"seen": ce_seen, "acted": ce_acted},
        "overview_usage": overview_usage,
        "feature_accesses": feature_accesses,
        "evidence_signals": round(evidence_score, 3),
        "tool_calls": int(tool_call_count),
    }
