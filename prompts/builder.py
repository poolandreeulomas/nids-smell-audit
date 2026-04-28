"""Prompt builder for MVP ReAct prompts with expandable overview support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prompts.context_loader import (
    get_agent_partition_context,
    get_current_agent_partition_name,
)
from state.schema import AgentState, EvidenceBlock
from src.feature_index import get_candidate_features

PROMPT_TEMPLATE_PATH = Path(__file__).with_name("react_prompt.txt")

_SIGNAL_FAMILY_ORDER = (
    "constant / low variance",
    "low entropy / dominant value",
    "redundancy / dependency",
    "distribution skew / collapse",
)

_MODE_TO_SIGNAL_FAMILY = {
    "low cardinality": "constant / low variance",
    "high skew": "distribution skew / collapse",
    "redundancy": "redundancy / dependency",
}

_KNOWN_FACT_SIGNAL_TO_MECHANISM = {
    "constant": "value_distribution",
    "low_entropy": "value_distribution",
    "redundancy_hint": "dependency",
}

_ACTION_TO_MECHANISM = {
    "feature_summary": "value_distribution",
    "cardinality_analysis": "value_distribution",
    "distribution_analysis": "value_distribution",
    "feature_relation": "dependency",
}

_MODE_TO_ACTION = {
    "low cardinality": "cardinality_analysis",
    "redundancy": "feature_relation",
}


def _format_available_tools(tool_names: list[str]) -> str:
    if not tool_names:
        return "NONE"
    return "\n".join(f"- {tool_name}" for tool_name in tool_names)


def _format_metric_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.6g}"
    return str(value)


def _normalize_signal_family(signal: object) -> str | None:
    if not isinstance(signal, str):
        return None

    normalized = signal.strip().lower().replace("-", "_")
    if not normalized:
        return None
    if normalized in {
        "low_variance",
        "low_diversity",
        "low_cardinality",
        "near_constant",
    }:
        return "constant / low variance"
    if normalized in {"low_entropy", "dominant_value"}:
        return "low entropy / dominant value"
    if normalized in {"high_redundancy", "high_duplication"}:
        return "redundancy / dependency"
    if normalized in {"high_skew", "extreme_skew"}:
        return "distribution skew / collapse"
    if any(token in normalized for token in ("redund", "correl", "depend", "duplicat")):
        return "redundancy / dependency"
    if any(token in normalized for token in ("entropy", "dominant")):
        return "low entropy / dominant value"
    if any(token in normalized for token in ("cardinality", "constant", "variance", "diversity")):
        return "constant / low variance"
    if any(token in normalized for token in ("skew", "tail", "spike", "collapse")):
        return "distribution skew / collapse"
    return None


def _normalize_known_fact_signal(signal: object) -> str | None:
    if not isinstance(signal, str):
        return None

    normalized = signal.strip().lower().replace("-", "_")
    if not normalized:
        return None
    if normalized in {
        "constant",
        "near_constant",
        "low_cardinality",
        "low_variance",
        "low_diversity",
    }:
        return "constant"
    if normalized in {"low_entropy", "dominant_value"}:
        return "low_entropy"
    if normalized in {"high_redundancy", "redundancy_hint"}:
        return "redundancy_hint"
    if normalized.startswith("redundant_with="):
        return "redundancy_hint"
    return None


def _get_action_mechanism(action: str | None) -> str | None:
    if not isinstance(action, str):
        return None
    return _ACTION_TO_MECHANISM.get(action.strip().lower())


def _get_mode_action(mode: str | None) -> str | None:
    if not isinstance(mode, str):
        return None
    return _MODE_TO_ACTION.get(mode.strip().lower())


def _feature_has_contradiction(state: AgentState | None, feature: str) -> bool:
    if state is None or not feature:
        return False

    for record in state.contradiction_memory or []:
        if not isinstance(record, dict):
            continue
        if record.get("feature") == feature:
            return True
        if record.get("feature_a") == feature or record.get("feature_b") == feature:
            return True
        features = record.get("features") or record.get("feature_names") or []
        if isinstance(features, list) and feature in {str(item) for item in features}:
            return True
    return False


def extract_overview_facts(
    candidate_summaries: dict[str, Any] | None,
) -> dict[str, set[str]]:
    facts: dict[str, set[str]] = {}
    if not candidate_summaries:
        return facts

    for feature_name, summary in candidate_summaries.items():
        if not isinstance(summary, dict):
            continue
        normalized_feature = str(feature_name)
        fact_types: set[str] = set()

        if summary.get("unique_values") == 1:
            fact_types.add("constant")

        for signal in summary.get("signals") or []:
            fact_type = _normalize_known_fact_signal(signal)
            if fact_type is not None:
                fact_types.add(fact_type)

        redundancy = summary.get("redundancy") or []
        if isinstance(redundancy, list) and any(
            isinstance(partner, dict) and partner.get("feature")
            for partner in redundancy
        ):
            fact_types.add("redundancy_hint")

        if fact_types:
            facts[normalized_feature] = fact_types

    return facts


def is_reconfirming_known_fact(
    action: str,
    feature: str,
    facts: dict[str, set[str]] | None,
    state: AgentState | None = None,
) -> bool:
    if not isinstance(feature, str) or not feature:
        return False
    if not facts or feature not in facts:
        return False
    if _feature_has_contradiction(state, feature):
        return False

    if action.strip().lower() == "feature_relation":
        return False

    action_mechanism = _get_action_mechanism(action)
    if action_mechanism is None:
        return False

    for fact_type in facts.get(feature, set()):
        if _KNOWN_FACT_SIGNAL_TO_MECHANISM.get(fact_type) == action_mechanism:
            return True
    return False


def filter_candidates_by_reconfirmation(
    candidates: list[dict[str, Any]],
    mode: str,
    facts: dict[str, set[str]] | None,
    state: AgentState | None = None,
) -> list[dict[str, Any]]:
    action = _get_mode_action(mode)
    if action is None:
        return list(candidates)

    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        feature_name = candidate.get("feature_name")
        if not isinstance(feature_name, str):
            continue
        if is_reconfirming_known_fact(action, feature_name, facts, state):
            continue
        filtered.append(candidate)
    return filtered


def _format_known_facts(facts: dict[str, set[str]] | None) -> str:
    if not facts:
        return "NONE"

    lines: list[str] = []
    for feature_name in sorted(facts):
        for fact_type in sorted(facts[feature_name]):
            mechanism = _KNOWN_FACT_SIGNAL_TO_MECHANISM.get(fact_type)
            if mechanism is None:
                continue
            lines.append(
                f"- {feature_name}: {fact_type} from overview (mechanism={mechanism})"
            )
    return "\n".join(lines) if lines else "NONE"


def _get_signal_family_counts(state: AgentState | None) -> dict[str, int]:
    counts = {family: 0 for family in _SIGNAL_FAMILY_ORDER}
    if state is None:
        return counts

    for feature_name, evidence_list in (state.evidence_by_feature or {}).items():
        summary = render_evidence_summary(feature_name, evidence_list)
        families = {
            family
            for signal in summary.get("signals", [])
            if (family := _normalize_signal_family(signal)) is not None
        }
        for family in families:
            counts[family] += 1
    return counts


def _format_pattern_coverage(state: AgentState | None) -> str:
    counts = _get_signal_family_counts(state)
    if not any(counts.values()):
        return "NONE"

    lines = []
    for family in _SIGNAL_FAMILY_ORDER:
        count = counts[family]
        if count >= 2:
            status = "established"
        elif count == 1:
            status = "weak"
        else:
            status = "none"
        suffix = ""
        if count > 0:
            suffix = f" ({count} feature{'s' if count != 1 else ''})"
        lines.append(f"- {family}: {status}{suffix}")
    return "\n".join(lines)


def _get_candidate_signal_families(candidate: dict[str, Any], source_mode: str) -> set[str]:
    families: set[str] = set()
    mode_family = _MODE_TO_SIGNAL_FAMILY.get(
        (source_mode or "").strip().lower())
    if mode_family is not None:
        families.add(mode_family)

    for signal in candidate.get("signals") or []:
        family = _normalize_signal_family(signal)
        if family is not None:
            families.add(family)
            continue
        if not isinstance(signal, str):
            continue
        normalized = signal.strip().lower()
        if normalized.startswith("redundant_with="):
            families.add("redundancy / dependency")
    return families


def _score_candidate_families(
    families: set[str], family_counts: dict[str, int]
) -> int:
    if not families:
        return 0

    score = 0
    for family in families:
        count = family_counts.get(family, 0)
        if count <= 0:
            score += 3
        elif count == 1:
            score += 1
        else:
            score -= 2
    return score


def _extract_signal_number(signals: list[object], prefix: str) -> float | None:
    for signal in signals:
        if not isinstance(signal, str):
            continue
        normalized = signal.strip().lower()
        if not normalized.startswith(prefix):
            continue
        try:
            return float(normalized.split("=", 1)[1])
        except (TypeError, ValueError):
            return None
    return None


def _candidate_matches_mode(candidate: dict[str, Any], source_mode: str) -> bool:
    signals = list(candidate.get("signals") or [])
    normalized_mode = (source_mode or "").strip().lower()

    if normalized_mode == "low cardinality":
        ratio = _extract_signal_number(signals, "cardinality_ratio=")
        return ratio is not None and ratio <= 0.1
    if normalized_mode == "high skew":
        skewness = _extract_signal_number(signals, "skewness=")
        return skewness is not None and abs(skewness) >= 3.0
    if normalized_mode == "redundancy":
        return any(
            isinstance(signal, str) and signal.strip(
            ).lower().startswith("redundant_with=")
            for signal in signals
        )
    return True


def _format_analyzed_features(analyzed_features: dict, tool_names: list[str]) -> str:
    if not analyzed_features:
        return "NONE"

    ranked_features = sorted(
        analyzed_features.items(),
        key=lambda item: (
            len(item[1].get("tools_used", [])),
            item[0],
        ),
        reverse=True,
    )

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
            evidence_parts.append(f"{tool_name}={_format_metric_value(value)}")
        lines.append(f"- {feature_name} -> " + ", ".join(evidence_parts))
    return "\n".join(lines)


def _format_evidence_memory(state: AgentState, tool_names: list[str]) -> str:
    evidence_map = dict(state.evidence_by_feature or {})
    if evidence_map:
        ordered_features: list[str] = []
        seen: set[str] = set()
        for feature_name in state.promising_features:
            if feature_name in evidence_map and feature_name not in seen:
                ordered_features.append(feature_name)
                seen.add(feature_name)
        for feature_name in sorted(evidence_map):
            if feature_name not in seen:
                ordered_features.append(feature_name)

        lines = []
        for feature_name in ordered_features:
            summary = render_evidence_summary(
                feature_name, evidence_map.get(feature_name, []))
            signals = "; ".join(summary.get("signals", [])) or "none"
            metrics = ", ".join(
                f"{key}={_format_metric_value(value)}"
                for key, value in summary.get("metrics", {}).items()
            ) or "none"
            support = summary.get("support", {}) or {}
            total_samples = support.get("total_samples", 0)
            status = summary.get("status") or "unknown"
            lines.append(
                f"- {feature_name} -> signals=[{signals}], metrics: {metrics}, support: total_samples={total_samples}, status={status}"
            )
        return "\n".join(lines)

    return _format_analyzed_features(state.analyzed_features, tool_names)


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
        action_input = _format_action_input(step.get("action_input", {}))
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


def _format_action_input(action_input: object) -> str:
    try:
        return json.dumps(action_input, ensure_ascii=True, sort_keys=True)
    except TypeError:
        return json.dumps(str(action_input), ensure_ascii=True)


def render_evidence_summary(
    feature: str,
    evidence_list: list[EvidenceBlock | dict],
    *,
    max_signals: int = 3,
    max_metrics: int = 4,
) -> dict:
    """Return a compact summary dict for a feature suitable for prompt rendering.

    Preserves signals and metrics for the LLM to see.
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
    sorted_keys = sorted(key_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for k, _ in sorted_keys[: max_metrics]:
        val = None
        for b in reversed(norm_blocks):
            if k in (b.get("metrics") or {}):
                val = (b.get("metrics") or {}).get(k)
                break
        if isinstance(val, (int, float)):
            try:
                val = float(val)
                val = round(val, 3)
            except Exception:
                pass
        metric_keys.append((k, val))
    metrics = {k: v for k, v in metric_keys}

    # Support: use the most recent non-empty support block; do not accumulate.
    support: dict[str, Any] = {}
    for b in reversed(norm_blocks):
        s = b.get("support") or {}
        if not isinstance(s, dict) or not s:
            continue
        total_samples = s.get("total_samples", s.get("n_total"))
        if isinstance(total_samples, (int, float)):
            support["total_samples"] = int(total_samples)
        per_class = s.get("per_class", s.get("n_per_class"))
        if isinstance(per_class, dict) and per_class:
            support["per_class"] = per_class
        if support:
            break

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


def _format_additional_candidates(
    candidate_summaries: dict | None,
    criteria: str,
    state: AgentState | None = None,
    known_facts: dict[str, set[str]] | None = None,
) -> str:
    """Render a compact additional-candidates block using `get_candidate_features`.

    If no summaries are available, return "NONE".
    """
    summaries = candidate_summaries
    if summaries is None and state is not None:
        summaries = state.metadata.get("compact_feature_index")

    if not summaries:
        return "NONE"

    covered_features: set[str] = set()
    family_counts = _get_signal_family_counts(state)
    if state is not None:
        covered_features.update(str(feature)
                                for feature in state.evidence_by_feature.keys())
        covered_features.update(str(feature)
                                for feature in state.promising_features)

    modes: list[str] = []
    seen_modes: set[str] = set()
    for mode in (criteria, "low cardinality", "high skew", "redundancy"):
        normalized = (mode or "").strip().lower()
        if not normalized or normalized in seen_modes:
            continue
        seen_modes.add(normalized)
        modes.append(mode)

    ranked_candidates: dict[str, dict[str, Any]] = {}
    for mode in modes:
        try:
            mode_candidates = get_candidate_features(
                mode, summaries=summaries, top_k=5)
        except Exception:
            continue
        mode_candidates = filter_candidates_by_reconfirmation(
            mode_candidates,
            mode,
            known_facts,
            state,
        )
        for rank, candidate in enumerate(mode_candidates, start=1):
            if not _candidate_matches_mode(candidate, mode):
                continue
            feature_name = str(candidate.get("feature_name", ""))
            if not feature_name or feature_name in covered_features:
                continue
            record = ranked_candidates.setdefault(
                feature_name,
                {
                    "feature_name": feature_name,
                    "signals": [],
                    "score": 0,
                    "family_score": 0,
                    "families": set(),
                    "sources": set(),
                },
            )
            for signal in candidate.get("signals") or []:
                if signal not in record["signals"]:
                    record["signals"].append(signal)
            record["families"].update(
                _get_candidate_signal_families(candidate, mode))
            record["score"] += max(1, 6 - rank)
            record["family_score"] = _score_candidate_families(
                record["families"], family_counts
            )
            record["sources"].add(mode)

    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()

    def add_candidate(candidate: dict[str, Any]) -> None:
        feature_name = candidate.get("feature_name")
        if not isinstance(feature_name, str) or not feature_name:
            return
        if feature_name in selected_names or feature_name in covered_features:
            return
        selected.append(candidate)
        selected_names.add(feature_name)

    strongest = sorted(
        ranked_candidates.values(),
        key=lambda item: (
            -int(item["family_score"]),
            -int(item["score"]),
            -len(item["sources"]),
            item["feature_name"],
        ),
    )[:3]
    for candidate in strongest:
        add_candidate(candidate)

    bucket_limits = sorted(
        (("low cardinality", 2), ("high skew", 2), ("redundancy", 2)),
        key=lambda item: (
            family_counts.get(_MODE_TO_SIGNAL_FAMILY[item[0]], 0),
            item[0],
        ),
    )
    for mode, limit in bucket_limits:
        try:
            bucket = get_candidate_features(mode, summaries=summaries, top_k=5)
        except Exception:
            continue
        bucket = filter_candidates_by_reconfirmation(
            bucket,
            mode,
            known_facts,
            state,
        )
        ranked_bucket = sorted(
            [
                (index, candidate)
                for index, candidate in enumerate(bucket)
                if _candidate_matches_mode(candidate, mode)
            ],
            key=lambda entry: (
                -_score_candidate_families(
                    _get_candidate_signal_families(
                        entry[1], mode), family_counts
                ),
                entry[0],
            ),
        )
        added = 0
        for _, candidate in ranked_bucket:
            before = len(selected)
            add_candidate(candidate)
            if len(selected) > before:
                added += 1
            if added >= limit or len(selected) >= 10:
                break
        if len(selected) >= 10:
            break

    if not selected:
        return "NONE"

    lines = ["Candidates for mixed structural signals:"]
    for candidate in selected[:10]:
        sig = "; ".join(str(s)
                        for s in (candidate.get("signals") or [])) or "none"
        lines.append(f"- {candidate['feature_name']}: {sig}")
    return "\n".join(lines)


def _format_previous_hypothesis(state: AgentState | None) -> str:
    """Return a short previous-hypothesis summary for the prompt.

    Uses `state.metadata['last_hypothesis']` and `hypothesis_revision_count`.
    """
    if state is None:
        return "NONE"
    last = state.metadata.get("last_hypothesis")
    if not last:
        return "NONE"
    count = state.metadata.get("hypothesis_revision_count", 0)
    try:
        count = int(count)
    except Exception:
        count = 0
    # Keep the displayed hypothesis compact (single-line)
    single = " ".join(str(last).splitlines())
    return f"Previous Hypothesis: {single} (revisions={count})"


def _format_partition_context() -> str:
    partition_name = get_current_agent_partition_name()
    return get_agent_partition_context(partition_name)


def build_prompt(
    state: AgentState,
    tool_names: list[str],
    history_window: int = 5,
    *,
    candidate_summaries: dict | None = None,
    candidate_criteria: str = "low cardinality",
) -> str:
    """Build prompt from state, tools, recent history, and optional candidate summaries."""
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    known_facts = extract_overview_facts(
        candidate_summaries or state.metadata.get("compact_feature_index")
    )
    return template.format(
        objective=state.objective,
        partition_context=_format_partition_context(),
        available_tools=_format_available_tools(tool_names),
        available_features=_format_available_features(
            state.available_features),
        analyzed_features=_format_evidence_memory(state, tool_names),
        pattern_coverage=_format_pattern_coverage(state),
        recent_history=_format_recent_history(state.history, history_window),
        additional_candidates=_format_additional_candidates(
            candidate_summaries, candidate_criteria, state, known_facts),
        known_facts=_format_known_facts(known_facts),
        previous_hypothesis=_format_previous_hypothesis(state),
    )
