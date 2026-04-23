"""Prompt builder for rigid MVP ReAct prompts."""

from __future__ import annotations

import json
from pathlib import Path

from state.schema import AgentState, EvidenceBlock

PROMPT_TEMPLATE_PATH = Path(__file__).with_name("react_prompt.txt")


def _format_available_tools(tool_names: list[str]) -> str:
    if not tool_names:
        return "NONE"
    return "\n".join(f"- {tool_name}" for tool_name in tool_names)


def _format_metric_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return str(value)


def _format_analyzed_features(analyzed_features: dict, tool_names: list[str]) -> str:
    if not analyzed_features:
        return "NONE"

    ranked_features = sorted(
        analyzed_features.items(),
        key=lambda item: (
            len(item[1].get("tools_used", [])),
            abs(float(item[1].get("correlation", 0.0) or 0.0)),
            float(item[1].get("wasserstein", 0.0) or 0.0),
            item[0],
        ),
        reverse=True,
    )


def render_evidence_summary(
    feature: str,
    evidence_list: list[EvidenceBlock | dict],
    *,
    max_signals: int = 3,
    max_metrics: int = 4,
) -> dict:
    """Return a compact summary dict for a feature suitable for prompt rendering.

    - `signals`: up to `max_signals` unique signal names (preserve order).
    - `metrics`: compact map of up to `max_metrics` keys with representative numeric values (rounded).
    - `support`: minimal support info: `total_samples` and optional `per_class` summary.
    - `status`: optional status from the latest evidence block.

    This helper preserves both `signals` and `metrics` (fingerprint_preserve=True)
    so downstream prompt templates will receive them verbatim (no compression).
    """
    # Normalize blocks to dicts
    norm_blocks: list[dict] = []
    for b in evidence_list or []:
        if isinstance(b, EvidenceBlock):
            norm_blocks.append(b.to_dict())
        elif isinstance(b, dict):
            norm_blocks.append(b)
        else:
            try:
                norm_blocks.append(dict(b))
            except Exception:
                continue

    # Signals: collect unique signals in order
    seen = set()
    signals: list[str] = []
    for b in norm_blocks:
        for s in (b.get("signals") or []):
            try:
                if s in seen:
                    continue
                seen.add(s)
                signals.append(s)
                if len(signals) >= max_signals:
                    break
            except Exception:
                continue
        if len(signals) >= max_signals:
            break

    # Metrics: pick keys by recency and availability
    metric_keys = []
    key_counts: dict = {}
    for b in norm_blocks:
        for k, v in (b.get("metrics") or {}).items():
            key_counts[k] = key_counts.get(k, 0) + 1
    # sort keys by count desc
    sorted_keys = sorted(key_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for k, _ in sorted_keys[: max_metrics]:
        # pick most recent value for key
        val = None
        for b in reversed(norm_blocks):
            if k in (b.get("metrics") or {}):
                val = (b.get("metrics") or {}).get(k)
                break
        # Compact numeric values
        if isinstance(val, (int, float)):
            try:
                val = float(val)
                # round to 3 significant decimals for compactness
                val = round(val, 3)
            except Exception:
                pass
        metric_keys.append((k, val))
    metrics = {k: v for k, v in metric_keys}

    # Support
    total_samples = 0
    per_class = None
    for b in norm_blocks:
        s = b.get("support") or {}
        if isinstance(s, dict) and isinstance(s.get("total_samples"), (int, float)):
            try:
                total_samples += int(s.get("total_samples", 0))
            except Exception:
                pass
        if isinstance(s, dict) and s.get("per_class") and per_class is None:
            per_class = s.get("per_class")

    support = {"total_samples": total_samples}
    if per_class is not None:
        support["per_class"] = per_class

    # Status: from last block if present
    status = None
    if norm_blocks:
        status = norm_blocks[-1].get("status")

    summary = {
        "feature": feature,
        "signals": signals,
        "metrics": metrics,
        "support": support,
        "status": status,
        "fingerprint_preserve": True,
    }
    return summary
    lines = []
    for feature_name, evidence in ranked_features:
        tools_used = [
            tool_name
            for tool_name in evidence.get("tools_used", [])
            if isinstance(tool_name, str) and tool_name
        ]
        evidence_parts = [f"tools_used=[{', '.join(tools_used)}]"]
        for tool_name in tool_names:
            if tool_name not in tools_used:
                continue
            value = evidence.get(tool_name)
            if value is None:
                continue
            evidence_parts.append(
                f"{tool_name}={_format_metric_value(value)}"
            )
        lines.append(f"- {feature_name} -> " + ", ".join(evidence_parts))
    return "\n".join(lines)


def _format_available_features(available_features: list[str]) -> str:
    if not available_features:
        return "NONE"
    return ", ".join(available_features)


def _format_observation(observation: object) -> str:
    if not isinstance(observation, dict):
        return str(observation)

    compact = {
        "ok": observation.get("ok"),
        "tool": observation.get("tool"),
        "feature_name": observation.get("feature_name"),
        "value": observation.get("value"),
        "error_code": observation.get("error_code"),
    }
    meta = observation.get("meta")
    if isinstance(meta, dict) and observation.get("ok") is False:
        compact["meta"] = {
            key: meta[key]
            for key in (
                "n_valid_rows",
                "feature_variance",
                "label_variance",
                "n_unique_feature_values",
            )
            if key in meta
        }
    return json.dumps(compact, ensure_ascii=True, sort_keys=True)


def _format_recent_history(history: list[dict], history_window: int) -> str:
    if not history:
        return "NONE"

    recent_steps = history[-history_window:]
    lines = []
    for step in recent_steps:
        step_id = step.get("step_id", "NA")
        thought = step.get("thought", "")
        action = step.get("action", "")
        action_input = step.get("action_input", {})
        observation = _format_observation(step.get("observation", ""))
        status = step.get("execution_status", "UNKNOWN")
        lines.append(
            "Step {step_id} | STATUS: {status} | THOUGHT: {thought} | ACTION: {action} | "
            "ACTION_INPUT: {action_input} | OBSERVATION: {observation}".format(
                step_id=step_id,
                status=status,
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
            )
        )
    return "\n".join(lines)


def build_prompt(
    state: AgentState,
    tool_names: list[str],
    history_window: int = 5,
) -> str:
    """Build prompt from state, tools, and recent history."""
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.format(
        objective=state.objective,
        available_tools=_format_available_tools(tool_names),
        available_features=_format_available_features(
            state.available_features),
        analyzed_features=_format_analyzed_features(
            state.analyzed_features, tool_names),
        recent_history=_format_recent_history(state.history, history_window),
    )
