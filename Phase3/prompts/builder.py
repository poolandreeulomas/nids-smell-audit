"""Prompt builder for MVP ReAct prompts with expandable overview support."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
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

_LOW_CARDINALITY_RATIO_THRESHOLD = 0.1
_HIGH_SKEW_THRESHOLD = 3.0
_DEPENDENCY_STRONG_THRESHOLD = 0.95
_DEPENDENCY_EXACT_THRESHOLD = 0.999
_MECHANISM_SOFT_BUDGET = 2
_SATURATED_COMPONENT_PENALTY = 2
_RECENT_MECHANISM_STREAK_THRESHOLD = 2
_RECENT_MECHANISM_COOLDOWN_PENALTY = 6
_RECENT_COMPONENT_COOLDOWN_PENALTY = 2

_MECHANISM_TO_SIGNAL_FAMILIES = {
    "dependency": {"redundancy / dependency"},
    "value_distribution": {
        "constant / low variance",
        "low entropy / dominant value",
        "distribution skew / collapse",
    },
}

_KNOWN_FACT_SIGNAL_TO_MECHANISM = {
    "constant": "value_distribution",
    "low_cardinality": "value_distribution",
    "low_entropy": "value_distribution",
    "high_skew": "value_distribution",
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
    "high skew": "distribution_analysis",
    "redundancy": "feature_relation",
}

_PROGRESS_MECHANISM_ORDER = (
    "dependency",
    "distribution",
    "cardinality",
    "duplication",
)

_STEP_ACTION_TO_MECHANISM = {
    "distribution_analysis": "distribution",
    "cardinality_analysis": "cardinality",
    "feature_relation": "relation",
    "duplication_analysis": "duplication",
}

_PROGRESS_ACTION_TO_MECHANISM = {
    "feature_summary": "distribution",
    "distribution_analysis": "distribution",
    "cardinality_analysis": "cardinality",
    "feature_relation": "dependency",
    "duplication_analysis": "duplication",
}

_MODE_TO_PROGRESS_MECHANISM = {
    "low cardinality": "cardinality",
    "high skew": "distribution",
    "redundancy": "dependency",
    "duplication": "duplication",
}

_PROGRESS_STATUS_ORDER = {
    "not explored": 0,
    "already observed": 1,
    "established": 2,
    "explored multiple times": 3,
}

_CANDIDATE_MODE_ORDER = {
    "duplication": 0,
    "low cardinality": 1,
    "high skew": 2,
    "redundancy": 3,
}

_STEP_SUMMARY_LIMIT = 10
_STEP_SUMMARY_DOMINANT_RATIO_THRESHOLD = 0.15
_STEP_SUMMARY_LOW_ENTROPY_THRESHOLD = 2.5


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
        "low_variance",
        "low_diversity",
    }:
        return "constant"
    if normalized in {"low_cardinality", "low_card"}:
        return "low_cardinality"
    if normalized in {"low_entropy", "dominant_value"}:
        return "low_entropy"
    if normalized in {"high_skew", "extreme_skew"}:
        return "high_skew"
    if normalized in {"high_redundancy", "redundancy_hint"}:
        return "redundancy_hint"
    if normalized.startswith("redundant_with="):
        return "redundancy_hint"
    return None


def _get_action_mechanism(action: str | None) -> str | None:
    if not isinstance(action, str):
        return None
    return _ACTION_TO_MECHANISM.get(action.strip().lower())


def _get_progress_action_mechanism(action: str | None) -> str | None:
    if not isinstance(action, str):
        return None
    return _PROGRESS_ACTION_TO_MECHANISM.get(action.strip().lower())


def _get_step_action_mechanism(action: str | None) -> str | None:
    if not isinstance(action, str):
        return None
    return _STEP_ACTION_TO_MECHANISM.get(action.strip().lower())


def _get_mode_action(mode: str | None) -> str | None:
    if not isinstance(mode, str):
        return None
    return _MODE_TO_ACTION.get(mode.strip().lower())


def _get_mode_mechanism(mode: str | None) -> str | None:
    return _get_action_mechanism(_get_mode_action(mode))


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_target_name(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip()
    if not normalized:
        return "unknown"
    if normalized in {"__dataset__", "dataset"}:
        return "dataset"
    return normalized


def _normalize_feature_stem(feature_name: str) -> str:
    normalized = _normalize_target_name(feature_name).lower()
    if normalized == "dataset":
        return normalized
    normalized = re.sub(r"\.\d+$", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _extract_metric_number(
    metrics: dict[str, Any],
    key: str,
    *,
    prefer: str = "max",
) -> float | None:
    value = metrics.get(key)
    numeric = _safe_float(value)
    if numeric is not None:
        return numeric
    if not isinstance(value, dict):
        return None

    numbers = [
        parsed
        for parsed in (_safe_float(item) for item in value.values())
        if parsed is not None
    ]
    if not numbers:
        return None
    if prefer == "min":
        return min(numbers)
    return max(numbers)


def _summary_looks_low_cardinality(summary: dict[str, Any]) -> bool:
    metrics = summary.get("metrics") or {}
    ratio = _extract_metric_number(metrics, "cardinality_ratio")
    if ratio is not None and ratio <= _LOW_CARDINALITY_RATIO_THRESHOLD:
        return True
    unique_values = _extract_metric_number(
        metrics, "unique_values", prefer="min")
    if unique_values is not None and unique_values <= 10:
        return True
    for signal in summary.get("signals") or []:
        family = _normalize_signal_family(signal)
        if family == "constant / low variance":
            return True
    return False


def _extract_feature_pair(feature_name: str) -> tuple[str, str] | None:
    parts = [part.strip() for part in feature_name.split("|")]
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def _get_dependency_strength(summary: dict[str, Any] | None) -> float | None:
    if not isinstance(summary, dict):
        return None

    strongest = 0.0
    found = False
    for partner in summary.get("redundancy") or []:
        if not isinstance(partner, dict):
            continue
        corr_value = _safe_float(partner.get("correlation"))
        if corr_value is None:
            continue
        strongest = max(strongest, abs(corr_value))
        found = True
    if not found:
        return None
    return strongest


def _build_redundancy_components(
    candidate_summaries: dict[str, Any] | None,
) -> dict[str, int]:
    if not candidate_summaries:
        return {}

    adjacency: dict[str, set[str]] = {
        str(feature_name): set() for feature_name in candidate_summaries
    }

    for feature_name, summary in candidate_summaries.items():
        normalized_feature = str(feature_name)
        for partner in summary.get("redundancy") or []:
            if not isinstance(partner, dict):
                continue
            partner_name = str(partner.get("feature") or "").strip()
            corr_value = _safe_float(partner.get("correlation"))
            if not partner_name or partner_name not in adjacency or corr_value is None:
                continue
            if abs(corr_value) < _DEPENDENCY_STRONG_THRESHOLD:
                continue
            adjacency[normalized_feature].add(partner_name)
            adjacency[partner_name].add(normalized_feature)

    component_by_feature: dict[str, int] = {}
    component_id = 0
    for feature_name, neighbors in adjacency.items():
        if not neighbors or feature_name in component_by_feature:
            continue
        stack = [feature_name]
        while stack:
            current = stack.pop()
            if current in component_by_feature:
                continue
            component_by_feature[current] = component_id
            stack.extend(
                neighbor
                for neighbor in adjacency.get(current, set())
                if neighbor not in component_by_feature
            )
        component_id += 1
    return component_by_feature


def _get_component_exploration(
    state: AgentState | None,
    component_by_feature: dict[str, int],
) -> dict[int, dict[str, float | int | bool]]:
    if state is None or not component_by_feature:
        return {}

    stats: dict[int, dict[str, float | int | bool]] = {}
    seen_pairs: set[tuple[int, tuple[str, str]]] = set()

    for feature_name, evidence_list in (state.evidence_by_feature or {}).items():
        if not isinstance(feature_name, str):
            continue
        pair = _extract_feature_pair(feature_name)
        if pair is None:
            continue
        component_ids = {
            component_by_feature.get(pair[0]),
            component_by_feature.get(pair[1]),
        }
        if None in component_ids or len(component_ids) != 1:
            continue

        component_id = next(iter(component_ids))
        normalized_pair = tuple(sorted(pair))
        if (component_id, normalized_pair) in seen_pairs:
            continue

        summary = render_evidence_summary(feature_name, evidence_list)
        corr_value = _safe_float(summary.get("metrics", {}).get("correlation"))
        if corr_value is None:
            continue

        strength = abs(corr_value)
        if strength < _DEPENDENCY_STRONG_THRESHOLD:
            continue

        seen_pairs.add((component_id, normalized_pair))
        record = stats.setdefault(
            component_id,
            {"strong_relations": 0, "has_exact": False, "strongest": 0.0},
        )
        record["strong_relations"] = int(record["strong_relations"]) + 1
        record["strongest"] = max(float(record["strongest"]), strength)
        if strength >= _DEPENDENCY_EXACT_THRESHOLD:
            record["has_exact"] = True

    return stats


def _is_component_saturated(component_stats: dict[str, float | int | bool] | None) -> bool:
    if not component_stats:
        return False
    if bool(component_stats.get("has_exact")):
        return True
    return int(component_stats.get("strong_relations", 0)) >= 2


def _get_candidate_component_penalty(
    feature_name: str,
    summary: dict[str, Any] | None,
    source_mode: str,
    state: AgentState | None,
    component_by_feature: dict[str, int],
    component_stats: dict[int, dict[str, float | int | bool]],
) -> int:
    if _get_mode_mechanism(source_mode) != "dependency":
        return 0
    if _feature_has_contradiction(state, feature_name):
        return 0

    component_id = component_by_feature.get(feature_name)
    if component_id is None:
        return 0

    explored = component_stats.get(component_id)
    if not _is_component_saturated(explored):
        return 0

    candidate_strength = _get_dependency_strength(summary)
    if candidate_strength is None:
        return _SATURATED_COMPONENT_PENALTY

    explored_strongest = float(explored.get("strongest", 0.0))
    if candidate_strength >= _DEPENDENCY_EXACT_THRESHOLD and not bool(explored.get("has_exact")):
        return 0
    if candidate_strength > explored_strongest:
        return 0
    return _SATURATED_COMPONENT_PENALTY


def _get_mechanism_usage_counts(state: AgentState | None) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    if state is None:
        return dict(counts)

    for step in state.history or []:
        if not isinstance(step, dict):
            continue
        mechanism = _get_action_mechanism(step.get("action"))
        if mechanism is None:
            continue
        status = str(step.get("execution_status") or "").upper()
        if status in {"PARSE_ERROR", "INVALID_JSON"}:
            continue
        counts[mechanism] += 1

    if any(counts.values()):
        return dict(counts)

    seen_records: set[tuple[str, str, object]] = set()
    for evidence_list in (state.evidence_by_feature or {}).values():
        for block in evidence_list or []:
            if isinstance(block, EvidenceBlock):
                payload = block.to_dict()
            elif isinstance(block, dict):
                payload = block
            else:
                continue
            provenance = payload.get("provenance") or {}
            tool_name = provenance.get("tool")
            mechanism = _get_action_mechanism(tool_name)
            if mechanism is None:
                continue
            record_id = (mechanism, str(tool_name), provenance.get("step"))
            if record_id in seen_records:
                continue
            seen_records.add(record_id)
            counts[mechanism] += 1

    return dict(counts)


def _get_mechanism_penalty(
    mechanisms: set[str],
    usage_counts: dict[str, int],
) -> int:
    if not mechanisms:
        return 0
    penalties = [
        max(0, int(usage_counts.get(mechanism, 0)) - _MECHANISM_SOFT_BUDGET)
        for mechanism in mechanisms
    ]
    return min(penalties) if penalties else 0


def _get_recent_successful_mechanisms(state: AgentState | None) -> list[str]:
    mechanisms: list[str] = []
    if state is None:
        return mechanisms

    for step in state.history or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("execution_status") or "").upper() != "OK":
            continue
        mechanism = _get_action_mechanism(step.get("action"))
        if mechanism is not None:
            mechanisms.append(mechanism)
    return mechanisms


def _get_recent_mechanism_streak(state: AgentState | None) -> tuple[str | None, int]:
    mechanisms = _get_recent_successful_mechanisms(state)
    if not mechanisms:
        return None, 0

    last_mechanism = mechanisms[-1]
    streak = 0
    for mechanism in reversed(mechanisms):
        if mechanism != last_mechanism:
            break
        streak += 1
    return last_mechanism, streak


def _mechanism_has_strong_evidence(
    state: AgentState | None,
    mechanism: str | None,
) -> bool:
    if state is None or mechanism is None:
        return False

    family_counts = _get_signal_family_counts(state)
    mechanism_families = _MECHANISM_TO_SIGNAL_FAMILIES.get(mechanism, set())
    total = sum(family_counts.get(family, 0) for family in mechanism_families)
    if total >= 2:
        return True

    if mechanism != "dependency":
        return False

    for feature_name, evidence_list in (state.evidence_by_feature or {}).items():
        summary = render_evidence_summary(feature_name, evidence_list)
        corr_value = _safe_float(summary.get("metrics", {}).get("correlation"))
        if corr_value is not None and abs(corr_value) >= _DEPENDENCY_EXACT_THRESHOLD:
            return True
    return False


def _get_recent_mechanism_cooldown(
    state: AgentState | None,
) -> dict[str, str | int | bool | None]:
    mechanism, streak = _get_recent_mechanism_streak(state)
    has_strong_evidence = _mechanism_has_strong_evidence(state, mechanism)
    is_active = (
        mechanism is not None
        and streak >= _RECENT_MECHANISM_STREAK_THRESHOLD
        and has_strong_evidence
    )
    return {
        "mechanism": mechanism,
        "streak": streak,
        "has_strong_evidence": has_strong_evidence,
        "active": is_active,
    }


def _get_recent_mechanism_penalty(
    mechanisms: set[str],
    cooldown: dict[str, str | int | bool | None],
    state: AgentState | None = None,
    feature_name: str | None = None,
) -> int:
    if not mechanisms or not bool(cooldown.get("active")):
        return 0
    if cooldown.get("mechanism") not in mechanisms:
        return 0
    if feature_name and _feature_has_contradiction(state, feature_name):
        return 0
    return _RECENT_MECHANISM_COOLDOWN_PENALTY


def _get_recent_component_penalty(
    feature_name: str,
    source_mode: str,
    cooldown: dict[str, str | int | bool | None],
    state: AgentState | None,
    component_by_feature: dict[str, int],
    component_stats: dict[int, dict[str, float | int | bool]],
) -> int:
    if not bool(cooldown.get("active")):
        return 0
    if cooldown.get("mechanism") != "dependency":
        return 0
    if _get_mode_mechanism(source_mode) != "dependency":
        return 0
    if _feature_has_contradiction(state, feature_name):
        return 0

    component_id = component_by_feature.get(feature_name)
    if component_id is None:
        return 0
    explored = component_stats.get(component_id)
    if not _is_component_saturated(explored):
        return 0
    return _RECENT_COMPONENT_COOLDOWN_PENALTY


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

    grouped_features: dict[str, list[str]] = {
        "redundancy_hint": [],
        "high_skew": [],
        "low_entropy": [],
        "low_cardinality": [],
        "constant": [],
    }
    for feature_name in sorted(facts):
        for fact_type in sorted(facts[feature_name]):
            if fact_type not in grouped_features:
                continue
            grouped_features[fact_type].append(feature_name)

    render_order = [
        ("redundancy_hint", "redundancy / dependency pattern"),
        ("high_skew", "strong distribution skew"),
        ("low_entropy", "dominant-value / low-entropy behavior"),
        ("low_cardinality", "low-cardinality behavior"),
        ("constant", "constant / near-constant behavior"),
    ]

    lines: list[str] = []
    for fact_type, label in render_order:
        features = grouped_features[fact_type]
        if not features:
            continue
        if len(features) == 1:
            lines.append(
                f"- One feature already suggests {label} ({features[0]})")
        else:
            examples = ", ".join(features[:2])
            lines.append(
                f"- {len(features)} features already suggest {label} (e.g., {examples})"
            )
        if len(lines) >= 5:
            break
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


def _format_next_step_guardrails(state: AgentState | None) -> str:
    cooldown = _get_recent_mechanism_cooldown(state)
    if not bool(cooldown.get("active")):
        return "NONE"

    mechanism = str(cooldown.get("mechanism") or "unknown")
    streak = int(cooldown.get("streak") or 0)
    return "\n".join(
        [
            f"- recent_focus={mechanism}",
            f"- recent_streak={streak}",
            "- guidance=switch mechanism unless contradiction or stronger unresolved evidence exists",
        ]
    )


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
        return ratio is not None and ratio <= _LOW_CARDINALITY_RATIO_THRESHOLD
    if normalized_mode == "high skew":
        skewness = _extract_signal_number(signals, "skewness=")
        return skewness is not None and abs(skewness) >= _HIGH_SKEW_THRESHOLD
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


def _get_available_feature_examples(
    available_features: list[str],
    state: AgentState | None,
    *,
    limit: int = 3,
) -> list[str]:
    if state is None or not available_features:
        return []

    available_set = {str(feature) for feature in available_features}
    ordered: list[str] = []
    seen: set[str] = set()

    def add_feature(feature_name: object) -> None:
        if not isinstance(feature_name, str) or not feature_name:
            return
        for part in feature_name.split("|"):
            candidate = part.strip()
            if not candidate or candidate not in available_set or candidate in seen:
                continue
            ordered.append(candidate)
            seen.add(candidate)
            if len(ordered) >= limit:
                return

    for feature_name in state.promising_features:
        add_feature(feature_name)
        if len(ordered) >= limit:
            return ordered

    for feature_name in (state.evidence_by_feature or {}).keys():
        add_feature(feature_name)
        if len(ordered) >= limit:
            return ordered

    for step in reversed(state.history or []):
        if not isinstance(step, dict):
            continue
        action_input = step.get("action_input") or {}
        if isinstance(action_input, dict):
            add_feature(action_input.get("feature_name"))
        if len(ordered) >= limit:
            return ordered

    for feature_name in available_features:
        add_feature(feature_name)
        if len(ordered) >= limit:
            break

    return ordered


def _format_available_features(
    available_features: list[str], state: AgentState | None = None
) -> str:
    if not available_features:
        return "NONE"

    has_local_context = bool(state and (
        state.evidence_by_feature or state.analyzed_features))
    if not has_local_context:
        return ", ".join(available_features)

    examples = _get_available_feature_examples(available_features, state)
    if not examples:
        return f"{len(available_features)} total features"

    return (
        f"{len(available_features)} total features. "
        f"Context examples: {', '.join(examples)}"
    )


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


def _summarize_history_outcome(observation: object, *, status: str) -> str:
    if not isinstance(observation, dict):
        text = str(observation).strip()
        return text or f"status={status}"

    error_code = observation.get("error_code")
    if error_code:
        return f"error_code={error_code}"

    parts: list[str] = []
    feature_name = observation.get("feature_name")
    if isinstance(feature_name, str) and feature_name:
        parts.append(f"feature_name={feature_name}")
    value = observation.get("value")
    if value is not None:
        parts.append(f"value={_format_metric_value(value)}")
    if not parts and observation.get("ok") is True:
        parts.append("ok")
    return ", ".join(parts) if parts else f"status={status}"


def _format_recent_history(history: list[dict], history_window: int) -> str:
    if not history:
        return "NONE"

    recent_steps = [step for step in history[-history_window:]
                    if isinstance(step, dict)]
    if not recent_steps:
        return "NONE"

    last_success = next(
        (
            step
            for step in reversed(recent_steps)
            if str(step.get("execution_status") or "").upper() == "OK"
        ),
        None,
    )
    last_failure = next(
        (
            step
            for step in reversed(recent_steps)
            if str(step.get("execution_status") or "").upper() != "OK"
        ),
        None,
    )

    lines: list[str] = []
    if last_success is not None:
        action = str(last_success.get("action") or "NONE")
        action_input = _format_action_input(
            last_success.get("action_input", {}))
        status = str(last_success.get("execution_status") or "UNKNOWN")
        outcome = _summarize_history_outcome(
            last_success.get("observation"), status=status
        )
        lines.append(f"- Last success: {action} {action_input} -> {outcome}")

    if last_failure is not None:
        action = str(last_failure.get("action") or "NONE")
        action_input = _format_action_input(
            last_failure.get("action_input", {}))
        status = str(last_failure.get("execution_status") or "UNKNOWN")
        outcome = _summarize_history_outcome(
            last_failure.get("observation"), status=status
        )
        lines.append(f"- Last failure: {action} {action_input} -> {outcome}")

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


def _extract_redundancy_partner(signals: list[str]) -> tuple[str | None, float | None]:
    for signal in signals:
        normalized = signal.strip()
        if not normalized.lower().startswith("redundant_with="):
            continue
        payload = normalized.split("=", 1)[1]
        partner = payload
        correlation: float | None = None
        if "@" in payload:
            partner, raw_correlation = payload.rsplit("@", 1)
            try:
                correlation = float(raw_correlation)
            except (TypeError, ValueError):
                correlation = None
        return partner, correlation
    return None, None


def _infer_candidate_mode(candidate: dict[str, Any]) -> str:
    preferred_mode = candidate.get("preferred_mode")
    if isinstance(preferred_mode, str) and preferred_mode:
        return preferred_mode

    sources = candidate.get("sources") or []
    if isinstance(sources, (set, list, tuple)):
        for mode_name in ("low cardinality", "high skew", "redundancy"):
            if mode_name in sources:
                return mode_name

    signals = [str(signal) for signal in (candidate.get("signals") or [])]
    if _extract_redundancy_partner(signals)[0] is not None:
        return "redundancy"
    if _extract_signal_number(signals, "skewness=") is not None:
        return "high skew"
    if _extract_signal_number(signals, "cardinality_ratio=") is not None:
        return "low cardinality"
    return "other"


def _normalize_selected_candidate(
    candidate: dict[str, Any], *, preferred_mode: str | None = None
) -> dict[str, Any]:
    normalized = dict(candidate)
    normalized["signals"] = [
        str(signal) for signal in (candidate.get("signals") or []) if signal is not None
    ]
    normalized["preferred_mode"] = preferred_mode or _infer_candidate_mode(
        normalized)
    return normalized


def _format_candidate_direction(candidate: dict[str, Any]) -> str:
    feature_name = str(candidate.get("feature_name") or "unknown")
    signals = [str(signal) for signal in (candidate.get("signals") or [])]
    mode = _infer_candidate_mode(candidate)

    if mode == "duplication":
        return "- Check dataset-level duplication (exact duplicate rows)"

    if mode == "redundancy":
        partner, correlation = _extract_redundancy_partner(signals)
        if partner:
            if correlation is not None:
                return (
                    f"- Test dependency between {feature_name} and {partner} "
                    f"(correlation={_format_metric_value(correlation)})"
                )
            return f"- Test dependency between {feature_name} and {partner}"
        return f"- Inspect dependency around {feature_name}"

    if mode == "high skew":
        skewness = _extract_signal_number(signals, "skewness=")
        if skewness is not None:
            return (
                f"- Check distribution anomaly in {feature_name} "
                f"(skewness={_format_metric_value(skewness)})"
            )
        return f"- Check distribution anomaly in {feature_name}"

    if mode == "low cardinality":
        ratio = _extract_signal_number(signals, "cardinality_ratio=")
        if ratio is not None:
            return (
                f"- Inspect low-cardinality behavior in {feature_name} "
                f"(cardinality_ratio={_format_metric_value(ratio)})"
            )
        return f"- Inspect low-cardinality behavior in {feature_name}"

    return f"- Inspect {feature_name}"


def _get_step_target(step: dict[str, Any]) -> str:
    observation = step.get("observation") or {}
    if isinstance(observation, dict):
        feature_name = observation.get("feature_name")
        if isinstance(feature_name, str) and feature_name:
            return _normalize_target_name(feature_name)

    action_input = step.get("action_input") or {}
    if isinstance(action_input, dict):
        feature_name = action_input.get("feature_name")
        if isinstance(feature_name, str) and feature_name:
            return _normalize_target_name(feature_name)

    return "unknown"


def _get_step_evidence_summaries(
    state: AgentState | None,
    step: dict[str, Any],
) -> list[dict[str, Any]]:
    if state is None:
        return []

    action = str(step.get("action") or "")
    step_id = step.get("step_id")
    target_names = {_get_step_target(step)}
    action_input = step.get("action_input") or {}
    if isinstance(action_input, dict):
        feature_name = action_input.get("feature_name")
        if isinstance(feature_name, str) and feature_name:
            target_names.add(feature_name.strip())
            target_names.add(_normalize_target_name(feature_name))
    observation = step.get("observation") or {}
    if isinstance(observation, dict):
        feature_name = observation.get("feature_name")
        if isinstance(feature_name, str) and feature_name:
            target_names.add(feature_name.strip())
            target_names.add(_normalize_target_name(feature_name))

    matches: list[dict[str, Any]] = []
    for feature_name, evidence_list in (state.evidence_by_feature or {}).items():
        normalized_feature = _normalize_target_name(feature_name)
        if feature_name not in target_names and normalized_feature not in target_names:
            continue

        has_matching_block = False
        for block in evidence_list or []:
            if isinstance(block, EvidenceBlock):
                payload = block.to_dict()
            elif isinstance(block, dict):
                payload = block
            else:
                continue
            provenance = payload.get("provenance") or {}
            block_tool = provenance.get("tool")
            block_step = provenance.get("step")
            if action and block_tool and block_tool != action:
                continue
            if step_id is not None and block_step not in {None, step_id}:
                continue
            has_matching_block = True
            break

        if has_matching_block or feature_name in target_names or normalized_feature in target_names:
            matches.append(render_evidence_summary(
                feature_name, evidence_list))

    return matches


def _get_step_surface_mechanism(
    step: dict[str, Any],
    summaries: list[dict[str, Any]],
) -> str | None:
    action = str(step.get("action") or "")
    mechanism = _get_step_action_mechanism(action)
    if mechanism is not None:
        return mechanism
    if action.strip().lower() != "feature_summary":
        return None
    if any(_summary_looks_low_cardinality(summary) for summary in summaries):
        return "cardinality"
    return "distribution"


def _get_step_signal_descriptor(
    step: dict[str, Any],
    mechanism: str,
    summaries: list[dict[str, Any]],
) -> tuple[str, str]:
    status = str(step.get("execution_status") or "UNKNOWN").upper()
    observation = step.get("observation") or {}
    error_code = ""
    if isinstance(observation, dict):
        error_code = str(observation.get("error_code") or "").upper()

    if status != "OK":
        if error_code == "REPEATED_FEATURE_BLOCKED":
            return "repeated target", "already observed"
        if error_code in {"PARSE_ERROR", "INVALID_JSON"}:
            return "invalid output", "not executed"
        return "failed step", "not executed"

    summary = summaries[0] if summaries else {}
    metrics = summary.get("metrics") or {}
    signals = [str(signal) for signal in (summary.get("signals") or [])]
    value = None
    if isinstance(observation, dict):
        value = _safe_float(observation.get("value"))

    if mechanism == "relation":
        correlation = _extract_metric_number(metrics, "correlation")
        if correlation is None:
            correlation = value
        if correlation is not None:
            absolute = abs(correlation)
            if absolute >= _DEPENDENCY_EXACT_THRESHOLD:
                return "strong correlation", "~1.0"
            if absolute >= _DEPENDENCY_STRONG_THRESHOLD:
                return "strong correlation", ">0.95"
        return "checked relation", "observed"

    if mechanism == "duplication":
        duplicate_ratio = _extract_metric_number(metrics, "duplicate_ratio")
        if duplicate_ratio is None:
            duplicate_ratio = value
        if duplicate_ratio is None:
            return "duplication checked", "observed"
        if duplicate_ratio <= 0:
            return "no duplication", "none observed"
        if duplicate_ratio < 0.1:
            return "low duplication", "rare duplicates"
        if duplicate_ratio < 0.25:
            return "moderate duplication", "some duplicates"
        return "high duplication", "many duplicates"

    if mechanism == "cardinality":
        if _summary_looks_low_cardinality(summary):
            return "low cardinality", "few unique values"
        return "cardinality checked", "observed"

    for signal in signals:
        family = _normalize_signal_family(signal)
        if family == "distribution skew / collapse":
            return "high skew", "non-uniform"

    dominant_ratio = _extract_metric_number(metrics, "dominant_ratio")
    if dominant_ratio is not None and dominant_ratio >= _STEP_SUMMARY_DOMINANT_RATIO_THRESHOLD:
        return "dominant value", "non-uniform"

    entropy = _extract_metric_number(metrics, "entropy", prefer="min")
    if entropy is not None and entropy <= _STEP_SUMMARY_LOW_ENTROPY_THRESHOLD:
        return "concentrated values", "non-uniform"

    return "distribution checked", "observed"


def _build_step_summary_records(
    state: AgentState | None,
    *,
    limit: int = _STEP_SUMMARY_LIMIT,
) -> list[dict[str, str]]:
    if state is None:
        return []

    steps = [step for step in (state.history or [])
             if isinstance(step, dict)][-limit:]
    records: list[dict[str, str]] = []
    for step in steps:
        summaries = _get_step_evidence_summaries(state, step)
        mechanism = _get_step_surface_mechanism(step, summaries)
        if mechanism is None:
            continue
        signal, descriptor = _get_step_signal_descriptor(
            step, mechanism, summaries)
        records.append(
            {
                "mechanism": mechanism,
                "progress_mechanism": "dependency" if mechanism == "relation" else mechanism,
                "target": _get_step_target(step),
                "signal": signal,
                "descriptor": descriptor,
                "status": str(step.get("execution_status") or "UNKNOWN").upper(),
            }
        )
    return records


def _format_step_summary(state: AgentState | None) -> str:
    records = _build_step_summary_records(state)
    if not records:
        return "NONE"
    return "\n".join(
        f"- {record['mechanism']}: {record['target']} -> {record['signal']} ({record['descriptor']})"
        for record in records
    )


def _get_current_progress_entries(
    state: AgentState | None,
) -> list[tuple[str, str, str | None]]:
    records = _build_step_summary_records(state)
    attempt_counts: dict[str, int] = defaultdict(int)
    success_counts: dict[str, int] = defaultdict(int)
    for record in records:
        mechanism = record["progress_mechanism"]
        attempt_counts[mechanism] += 1
        if record["status"] == "OK":
            success_counts[mechanism] += 1

    family_counts = _get_signal_family_counts(state)
    duplication_seen = bool(state and "__dataset__" in (
        state.evidence_by_feature or {}))
    entries: list[tuple[str, str, str | None]] = []

    for mechanism in _PROGRESS_MECHANISM_ORDER:
        attempts = int(attempt_counts.get(mechanism, 0))
        successes = int(success_counts.get(mechanism, 0))
        status = "not explored"
        note: str | None = None

        if mechanism == "dependency":
            observed = int(family_counts.get("redundancy / dependency", 0))
            if _mechanism_has_strong_evidence(state, "dependency") or observed >= 2:
                status = "established"
                if attempts >= 2:
                    note = "low additional value"
            elif attempts >= 2:
                status = "explored multiple times"
                note = "low additional value"
            elif attempts >= 1 or successes >= 1 or observed >= 1:
                status = "already observed"
        elif mechanism == "distribution":
            observed = int(family_counts.get("distribution skew / collapse", 0)) + int(
                family_counts.get("low entropy / dominant value", 0)
            )
            if attempts >= 2 or observed >= 2:
                status = "explored multiple times"
                note = "low additional value"
            elif attempts >= 1 or successes >= 1 or observed >= 1:
                status = "already observed"
        elif mechanism == "cardinality":
            observed = int(family_counts.get("constant / low variance", 0))
            if observed >= 2:
                status = "established"
                if attempts >= 2:
                    note = "low additional value"
            elif attempts >= 2:
                status = "explored multiple times"
                note = "low additional value"
            elif attempts >= 1 or successes >= 1 or observed >= 1:
                status = "already observed"
        else:
            if attempts >= 2:
                status = "explored multiple times"
                note = "low additional value"
            elif attempts >= 1 or successes >= 1 or duplication_seen:
                status = "already observed"
                note = "unlikely to add new information"

        entries.append((mechanism, status, note))

    return entries


def _format_current_progress(state: AgentState | None) -> str:
    entries = _get_current_progress_entries(state)
    lines = []
    for mechanism, status, note in entries:
        if note:
            lines.append(f"- {mechanism}: {status} ({note})")
        else:
            lines.append(f"- {mechanism}: {status}")
    return "\n".join(lines) if lines else "NONE"


def _format_active_patterns(state: AgentState | None) -> str:
    records = _build_step_summary_records(state)
    if not records:
        return ""

    lines: list[str] = []
    strong_relations = sum(
        1
        for record in records
        if record["mechanism"] == "relation"
        and record["status"] == "OK"
        and record["signal"] == "strong correlation"
    )
    if strong_relations >= 2:
        lines.append("- strong redundancy observed across multiple features")

    repeated_distribution = sum(
        1
        for record in records
        if record["mechanism"] == "distribution"
        and record["status"] == "OK"
        and record["signal"] in {"high skew", "dominant value", "concentrated values"}
    )
    if repeated_distribution >= 2 and len(lines) < 2:
        lines.append("- repeated distribution anomaly observed")

    repeated_cardinality = sum(
        1
        for record in records
        if record["mechanism"] == "cardinality"
        and record["status"] == "OK"
        and record["signal"] == "low cardinality"
    )
    if repeated_cardinality >= 2 and len(lines) < 2:
        lines.append("- repeated low-cardinality pattern observed")

    return "\n".join(lines[:2])


def _format_active_patterns_block(state: AgentState | None) -> str:
    active_patterns = _format_active_patterns(state)
    if not active_patterns:
        return ""
    return f"ACTIVE_PATTERNS:\n{active_patterns}\n\n"


def _get_candidate_neighborhood(
    feature_name: str,
    source_mode: str,
    component_by_feature: dict[str, int],
) -> str:
    normalized_mode = (source_mode or "").strip().lower()
    if normalized_mode == "duplication":
        return "dataset"
    if normalized_mode == "redundancy":
        component_id = component_by_feature.get(feature_name)
        if component_id is not None:
            return f"component:{component_id}"
    return f"stem:{_normalize_feature_stem(feature_name)}"


def _duplication_is_spent(state: AgentState | None) -> bool:
    if state is None:
        return False
    if "__dataset__" in (state.evidence_by_feature or {}):
        return True
    for step in state.history or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("action") or "").strip().lower() != "duplication_analysis":
            continue
        status = str(step.get("execution_status") or "").upper()
        if status not in {"PARSE_ERROR", "INVALID_JSON"}:
            return True
    return False


def _format_additional_candidates(
    candidate_summaries: dict | None,
    criteria: str,
    state: AgentState | None = None,
    known_facts: dict[str, set[str]] | None = None,
    tool_names: list[str] | None = None,
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
    mechanism_usage_counts = _get_mechanism_usage_counts(state)
    cooldown = _get_recent_mechanism_cooldown(state)
    component_by_feature = _build_redundancy_components(summaries)
    component_stats = _get_component_exploration(state, component_by_feature)
    current_progress = {
        mechanism: status
        for mechanism, status, _ in _get_current_progress_entries(state)
    }
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

    buckets: dict[str, list[dict[str, Any]]] = {}
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
        ranked_bucket: list[dict[str, Any]] = []
        for rank, candidate in enumerate(mode_candidates, start=1):
            if not _candidate_matches_mode(candidate, mode):
                continue
            feature_name = str(candidate.get("feature_name", ""))
            if not feature_name or feature_name in covered_features:
                continue
            candidate_summary = summaries.get(feature_name, {})
            mechanisms = {
                mechanism
                for mechanism in {_get_mode_mechanism(mode)}
                if mechanism is not None
            }
            mechanism_penalty = _get_mechanism_penalty(
                mechanisms, mechanism_usage_counts)
            cooldown_penalty = _get_recent_mechanism_penalty(
                mechanisms,
                cooldown,
                state,
                feature_name,
            )
            component_penalty = _get_candidate_component_penalty(
                feature_name,
                candidate_summary,
                mode,
                state,
                component_by_feature,
                component_stats,
            )
            component_penalty += _get_recent_component_penalty(
                feature_name,
                mode,
                cooldown,
                state,
                component_by_feature,
                component_stats,
            )
            families = _get_candidate_signal_families(candidate, mode)
            ranked_bucket.append(
                {
                    "feature_name": feature_name,
                    "preferred_mode": mode,
                    "signals": [
                        str(signal)
                        for signal in (candidate.get("signals") or [])
                        if signal is not None
                    ],
                    "score": max(1, 6 - rank),
                    "family_score": _score_candidate_families(
                        families, family_counts
                    ),
                    "component_penalty": component_penalty,
                    "mechanism_penalty": mechanism_penalty,
                    "cooldown_penalty": cooldown_penalty,
                    "families": families,
                    "mechanisms": mechanisms,
                    "sources": {mode},
                    "neighborhood": _get_candidate_neighborhood(
                        feature_name,
                        mode,
                        component_by_feature,
                    ),
                }
            )
        buckets[mode] = sorted(
            ranked_bucket,
            key=lambda item: (
                -int(item["family_score"]),
                int(item["cooldown_penalty"]),
                int(item["mechanism_penalty"]),
                int(item["component_penalty"]),
                -int(item["score"]),
                item["feature_name"],
            ),
        )

    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()
    selected_neighborhoods: set[str] = set()

    available_tools = {
        str(tool_name)
        for tool_name in (tool_names or [])
        if isinstance(tool_name, str)
    }
    duplication_candidate: dict[str, Any] | None = None
    if (not available_tools or "duplication_analysis" in available_tools) and not _duplication_is_spent(state):
        duplication_candidate = {
            "feature_name": "dataset",
            "preferred_mode": "duplication",
            "signals": ["dataset_level"],
            "score": 1,
            "family_score": 3,
            "component_penalty": 0,
            "mechanism_penalty": 0,
            "cooldown_penalty": 0,
            "families": set(),
            "mechanisms": {"duplication"},
            "sources": {"duplication"},
            "neighborhood": "dataset",
        }

    mode_sequence = []
    seen_selection_modes: set[str] = set()
    for mode in ("duplication", criteria, "low cardinality", "high skew", "redundancy"):
        normalized = (mode or "").strip().lower()
        if not normalized or normalized in seen_selection_modes:
            continue
        seen_selection_modes.add(normalized)
        mode_sequence.append(mode)

    def mode_sort_key(mode_name: str) -> tuple[int, int, int]:
        normalized = (mode_name or "").strip().lower()
        progress_mechanism = _MODE_TO_PROGRESS_MECHANISM.get(
            normalized, normalized)
        progress_status = current_progress.get(
            progress_mechanism, "not explored")
        return (
            _PROGRESS_STATUS_ORDER.get(progress_status, 99),
            0 if normalized == (criteria or "").strip().lower() else 1,
            _CANDIDATE_MODE_ORDER.get(normalized, 99),
        )

    for mode in sorted(mode_sequence, key=mode_sort_key):
        normalized = (mode or "").strip().lower()
        if normalized == "duplication":
            candidate = duplication_candidate
            if candidate is None or candidate["neighborhood"] in selected_neighborhoods:
                continue
            selected.append(_normalize_selected_candidate(
                candidate, preferred_mode="duplication"))
            selected_names.add(str(candidate["feature_name"]))
            selected_neighborhoods.add(str(candidate["neighborhood"]))
            continue

        for candidate in buckets.get(mode, []):
            feature_name = str(candidate.get("feature_name") or "")
            neighborhood = str(candidate.get("neighborhood") or "")
            if not feature_name or feature_name in covered_features or feature_name in selected_names:
                continue
            if neighborhood and neighborhood in selected_neighborhoods:
                continue
            selected.append(_normalize_selected_candidate(
                candidate, preferred_mode=mode))
            selected_names.add(feature_name)
            if neighborhood:
                selected_neighborhoods.add(neighborhood)
            break

    if not selected:
        return "NONE"

    lines: list[str] = []
    for candidate in selected:
        lines.append(_format_candidate_direction(candidate))
        if len(lines) >= 4:
            break

    if not lines:
        return "NONE"
    return "\n".join(lines)


def _format_previous_hypothesis(state: AgentState | None) -> str:
    """Return a short previous-hypothesis summary for the prompt.

    Uses `state.metadata['last_hypothesis']` and `hypothesis_revision_count`.
    """
    if state is None:
        return "NONE"
    cooldown = _get_recent_mechanism_cooldown(state)
    last = state.metadata.get("last_hypothesis")
    count = state.metadata.get("hypothesis_revision_count", 0)
    try:
        count = int(count)
    except Exception:
        count = 0
    if bool(cooldown.get("active")):
        mechanism = str(cooldown.get("mechanism") or "unknown")
        streak = int(cooldown.get("streak") or 0)
        return (
            "Previous Hypothesis: Current {mechanism} line of inquiry already has local support "
            "(recent_streak={streak}). Seek orthogonal evidence next unless resolving a contradiction "
            "or stronger unresolved evidence. (revisions={count})"
        ).format(mechanism=mechanism, streak=streak, count=count)
    if not last:
        return "NONE"
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
            state.available_features, state),
        analyzed_features=_format_evidence_memory(state, tool_names),
        pattern_coverage=_format_pattern_coverage(state),
        next_step_guardrails=_format_next_step_guardrails(state),
        current_progress=_format_current_progress(state),
        active_patterns_block=_format_active_patterns_block(state),
        step_summary=_format_step_summary(state),
        recent_history=_format_recent_history(state.history, history_window),
        additional_candidates=_format_additional_candidates(
            candidate_summaries,
            candidate_criteria,
            state,
            known_facts,
            tool_names,
        ),
        known_facts=_format_known_facts(known_facts),
        previous_hypothesis=_format_previous_hypothesis(state),
    )
