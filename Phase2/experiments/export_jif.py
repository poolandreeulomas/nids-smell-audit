"""Export neutral Judge Input Format payloads from persisted run logs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
from typing import Any

from tools.registry import get_tool_registry
from utils.run_logging import DEFAULT_RUNS_DIR, load_json, write_json


DEFAULT_JIF_DIR = Path(__file__).resolve().parent.parent / "reports" / "jif"
_PAIR_SEPARATOR = "|"
_CONTRADICTION_PATTERN = re.compile(
    r"Hypothesis revised from '(?P<from>.*)' to '(?P<to>.*)'\.",
    re.DOTALL,
)


def _resolve_run_paths(run_paths: list[str] | None, latest: int) -> list[Path]:
    if run_paths:
        return [Path(path) for path in run_paths]

    candidates = sorted(
        path
        for path in DEFAULT_RUNS_DIR.glob("run_*.json")
        if not path.name.endswith("_metrics.json") and path.name != "run_test_metrics.json"
    )
    if latest <= 0:
        return []
    return candidates[-latest:]


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        try:
            return math.isfinite(float(value))
        except Exception:
            return False
    return False


def _round_number(value: Any) -> float:
    return round(float(value), 6)


def _reduce_numeric_values(values: list[float]) -> float:
    if not values:
        raise ValueError("values must not be empty")
    rounded = [_round_number(value) for value in values]
    if len(set(rounded)) == 1:
        return rounded[0]
    return _round_number(sum(rounded) / len(rounded))


def _extract_metric_anchors(metrics: dict[str, Any] | None) -> dict[str, float]:
    anchors: dict[str, float] = {}
    if not isinstance(metrics, dict):
        return anchors

    def visit(value: Any, key_path: str) -> None:
        if _is_number(value):
            anchors[key_path] = _round_number(value)
            return
        if not isinstance(value, dict) or not value:
            return

        numeric_values = [float(item)
                          for item in value.values() if _is_number(item)]
        if len(numeric_values) == len(value):
            anchors[key_path] = _reduce_numeric_values(numeric_values)
            return

        for child_key, child_value in sorted(value.items()):
            child_path = f"{key_path}.{child_key}" if key_path else str(
                child_key)
            visit(child_value, child_path)

    for metric_name, metric_value in sorted(metrics.items()):
        visit(metric_value, str(metric_name))
    return anchors


def _normalize_target_key(feature_name: str | None, action: str | None) -> tuple[str, str, list[str]]:
    raw_name = feature_name or ""
    if action == "duplication_analysis" or raw_name == "__dataset__":
        return "__dataset__", "dataset", []

    if _PAIR_SEPARATOR in raw_name:
        parts = [part.strip()
                 for part in raw_name.split(_PAIR_SEPARATOR) if part.strip()]
        canonical_parts = sorted(dict.fromkeys(parts))
        if len(canonical_parts) >= 2:
            return _PAIR_SEPARATOR.join(canonical_parts), "pair", canonical_parts

    if raw_name:
        return raw_name.strip(), "feature", [raw_name.strip()]

    return "__unknown__", "feature", ["__unknown__"]


def _select_observed_target(step: dict[str, Any]) -> tuple[str, str, list[str], str | None, str | None]:
    action = step.get("action") if isinstance(
        step.get("action"), str) else None
    action_input = step.get("action_input") or {}
    observation = step.get("observation") or {}
    evidence = observation.get("evidence") or {}

    input_feature = action_input.get("feature_name") if isinstance(
        action_input.get("feature_name"), str) else None
    observed_feature = None
    if isinstance(evidence, dict) and isinstance(evidence.get("feature"), str):
        observed_feature = evidence.get("feature")
    elif isinstance(observation.get("feature_name"), str):
        observed_feature = observation.get("feature_name")
    else:
        observed_feature = input_feature

    target_key, target_type, features = _normalize_target_key(
        observed_feature, action)
    return target_key, target_type, features, input_feature, observed_feature


def _extract_step_signals(step: dict[str, Any]) -> list[str]:
    observation = step.get("observation") or {}
    evidence = observation.get("evidence") or {}
    signals = evidence.get("signals") if isinstance(evidence, dict) else None
    if not isinstance(signals, list):
        return []
    return [str(signal) for signal in signals if isinstance(signal, str) and signal]


def _extract_step_metric_anchors(step: dict[str, Any]) -> dict[str, float]:
    observation = step.get("observation") or {}
    evidence = observation.get("evidence") or {}
    metrics = evidence.get("metrics") if isinstance(evidence, dict) else None
    anchors = _extract_metric_anchors(
        metrics if isinstance(metrics, dict) else {})
    if anchors:
        return anchors
    if _is_number(observation.get("value")):
        return {"value": _round_number(observation.get("value"))}
    return {}


def _build_key_result_short(step: dict[str, Any], signal_labels: list[str]) -> str:
    if signal_labels:
        return "; ".join(signal_labels[:2])
    observation = step.get("observation") or {}
    error_code = observation.get("error_code")
    if isinstance(error_code, str) and error_code:
        return error_code
    status = step.get("execution_status")
    if isinstance(status, str) and status:
        return status
    return "ok"


def _support_summary(support: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(support, dict):
        return {}

    total_samples = support.get("total_samples", support.get("n_total"))
    per_class = support.get("per_class", support.get("n_per_class"))
    summary: dict[str, int] = {}
    if isinstance(total_samples, int):
        summary["total_samples"] = total_samples
    if isinstance(per_class, dict):
        summary["class_count"] = len(per_class)
    return summary


def _extract_run_metadata(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    metadata = payload.get("metadata") or {}
    reproducibility = metadata.get(
        "reproducibility") if isinstance(metadata, dict) else {}
    if not isinstance(reproducibility, dict):
        reproducibility = {}

    dataset_path = reproducibility.get("dataset_path")
    dataset_basename = Path(dataset_path).name if isinstance(
        dataset_path, str) and dataset_path else "unknown"
    dataset_hash = reproducibility.get("dataset_hash") if isinstance(
        reproducibility.get("dataset_hash"), str) else "unknown"
    model_name = reproducibility.get("model_name") if isinstance(
        reproducibility.get("model_name"), str) else "unknown"
    model_version = reproducibility.get("model_version") if isinstance(reproducibility.get(
        "model_version"), str) and reproducibility.get("model_version") else "unknown"
    return dataset_basename, dataset_hash, model_name, model_version


def _collect_step_trace(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter, Counter, Counter, Counter]:
    history = list(payload.get("history", []) or [])
    seen_target_signals: dict[str, set[str]] = defaultdict(set)
    seen_target_metrics: dict[str, set[tuple[str, float]]] = defaultdict(set)

    step_trace: list[dict[str, Any]] = []
    tool_frequency: Counter[str] = Counter()
    step_type_frequency: Counter[str] = Counter()
    signal_frequency: Counter[str] = Counter()
    redundant_step_frequency: Counter[str] = Counter()

    for index, step in enumerate(history, start=1):
        action = step.get("action") if isinstance(
            step.get("action"), str) else None
        if action:
            tool_frequency[action] += 1

        target_key, target_type, features, input_feature, observed_feature = _select_observed_target(
            step)
        signal_labels = _extract_step_signals(step)
        metric_anchors = _extract_step_metric_anchors(step)

        new_signals = [
            signal for signal in signal_labels if signal not in seen_target_signals[target_key]]
        metric_items = {(name, value)
                        for name, value in metric_anchors.items()}
        new_metric_items = [item for item in sorted(
            metric_items) if item not in seen_target_metrics[target_key]]

        if action == "feature_relation" or target_type == "pair":
            step_type = "relation"
        elif target_key not in {entry["target_key"] for entry in step_trace}:
            step_type = "exploration"
        elif new_signals or new_metric_items:
            step_type = "confirmation"
        else:
            step_type = "validation"

        redundant_step = bool(step_trace and step_type !=
                              "exploration" and not new_signals and not new_metric_items)
        if redundant_step:
            information_gain = "low"
        elif new_signals and new_metric_items:
            information_gain = "high"
        elif new_signals or new_metric_items:
            information_gain = "medium"
        else:
            information_gain = "low"

        step_record = {
            "step_index": int(step.get("step_id") or index),
            "target_key": target_key,
            "target_type": target_type,
            "features": features,
            "input_feature": input_feature,
            "observed_feature": observed_feature,
            "tool": action,
            "step_type": step_type,
            "status": step.get("execution_status"),
            "signal_labels": signal_labels,
            "metric_anchors": metric_anchors,
            "key_result_short": _build_key_result_short(step, signal_labels),
            "novelty_sources": {
                "new_signals": len(new_signals),
                "new_metrics": len(new_metric_items),
            },
            "information_gain": information_gain,
            "redundant_step": redundant_step,
        }
        step_trace.append(step_record)
        step_type_frequency[step_type] += 1
        redundant_step_frequency[str(redundant_step).lower()] += 1
        signal_frequency.update(signal_labels)
        seen_target_signals[target_key].update(new_signals)
        seen_target_metrics[target_key].update(new_metric_items)

    return step_trace, tool_frequency, step_type_frequency, signal_frequency, redundant_step_frequency


def _build_feature_cards(
    payload: dict[str, Any], step_trace: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}

    def ensure_card(target_key: str, target_type: str, features: list[str]) -> dict[str, Any]:
        card = cards.get(target_key)
        if card is None:
            card = {
                "target_key": target_key,
                "target_type": target_type,
                "features": features,
                "first_seen_step": None,
                "last_seen_step": None,
                "step_indices": [],
                "observation_count": 0,
                "tool_frequency": Counter(),
                "status_frequency": Counter(),
                "signal_frequency": Counter(),
                "metric_anchors": {},
                "support_variants": [],
                "contradiction_step_indices": [],
            }
            cards[target_key] = card
        return card

    for step in step_trace:
        card = ensure_card(step["target_key"],
                           step["target_type"], list(step["features"]))
        step_index = int(step["step_index"])
        card["step_indices"].append(step_index)
        card["observation_count"] += 1
        card["first_seen_step"] = step_index if card["first_seen_step"] is None else min(
            card["first_seen_step"], step_index)
        card["last_seen_step"] = step_index if card["last_seen_step"] is None else max(
            card["last_seen_step"], step_index)
        tool_name = step.get("tool")
        if isinstance(tool_name, str) and tool_name:
            card["tool_frequency"][tool_name] += 1

    evidence_by_feature = payload.get("evidence_by_feature") or {}
    for raw_feature, blocks in sorted(dict(evidence_by_feature).items()):
        if not isinstance(blocks, list):
            continue
        target_key, target_type, features = _normalize_target_key(
            str(raw_feature), None)
        card = ensure_card(target_key, target_type, features)
        if not card["step_indices"]:
            provenance_steps = []
            for block in blocks:
                if isinstance(block, dict):
                    step_value = (block.get("provenance") or {}).get("step")
                    if isinstance(step_value, int):
                        provenance_steps.append(step_value)
            if provenance_steps:
                card["first_seen_step"] = min(provenance_steps)
                card["last_seen_step"] = max(provenance_steps)
                card["step_indices"] = sorted(set(provenance_steps))
                card["observation_count"] = len(provenance_steps)
        for block in blocks:
            if not isinstance(block, dict):
                continue
            status = block.get("status")
            if isinstance(status, str) and status:
                card["status_frequency"][status] += 1
            for signal in block.get("signals") or []:
                if isinstance(signal, str) and signal:
                    card["signal_frequency"][signal] += 1
            for metric_name, metric_value in _extract_metric_anchors(block.get("metrics") or {}).items():
                card["metric_anchors"].setdefault(metric_name, metric_value)
            support_summary = _support_summary(block.get("support") or {})
            if support_summary and support_summary not in card["support_variants"]:
                card["support_variants"].append(support_summary)
            tool_name = (block.get("provenance") or {}).get("tool")
            if isinstance(tool_name, str) and tool_name:
                card["tool_frequency"][tool_name] += 0

    for contradiction in list(payload.get("contradiction_memory", []) or []):
        if not isinstance(contradiction, dict):
            continue
        feature_name = contradiction.get("feature")
        if not isinstance(feature_name, str) or not feature_name:
            continue
        target_key, _, _ = _normalize_target_key(feature_name, None)
        card = cards.get(target_key)
        if card is None:
            continue
        step_value = contradiction.get("step")
        if isinstance(step_value, int) and step_value not in card["contradiction_step_indices"]:
            card["contradiction_step_indices"].append(step_value)

    result = []
    for target_key in sorted(cards):
        card = cards[target_key]
        result.append(
            {
                "target_key": card["target_key"],
                "target_type": card["target_type"],
                "features": card["features"],
                "first_seen_step": card["first_seen_step"],
                "last_seen_step": card["last_seen_step"],
                "step_indices": sorted(card["step_indices"]),
                "observation_count": int(card["observation_count"]),
                "tool_frequency": dict(sorted(card["tool_frequency"].items())),
                "status_frequency": dict(sorted(card["status_frequency"].items())),
                "signal_frequency": dict(sorted(card["signal_frequency"].items())),
                "metric_anchors": dict(sorted(card["metric_anchors"].items())),
                "support_variants": sorted(card["support_variants"], key=lambda item: json.dumps(item, sort_keys=True)),
                "contradiction_step_indices": sorted(card["contradiction_step_indices"]),
            }
        )
    return result


def _build_contradictions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    contradictions = []
    for item in list(payload.get("contradiction_memory", []) or []):
        if not isinstance(item, dict):
            continue
        reason = item.get("reason") if isinstance(
            item.get("reason"), str) else ""
        match = _CONTRADICTION_PATTERN.search(reason)
        contradictions.append(
            {
                "step_index": item.get("step"),
                "from_hypothesis": match.group("from") if match else None,
                "to_hypothesis": match.group("to") if match else None,
                "has_evidence_refs": bool(item.get("evidence_refs")),
            }
        )
    return contradictions


def _build_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors = []
    for item in list(payload.get("errors", []) or []):
        if not isinstance(item, dict):
            continue
        errors.append(
            {
                "step_index": item.get("step_id"),
                "error_code": item.get("error_code"),
                "error_message": item.get("error_message"),
            }
        )
    return errors


def _build_run_card(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    dataset_basename, dataset_hash, model_name, model_version = _extract_run_metadata(
        payload)
    step_trace, tool_frequency, step_type_frequency, signal_frequency, _ = _collect_step_trace(
        payload)
    feature_cards = _build_feature_cards(payload, step_trace)
    error_steps = sum(1 for step in step_trace if step.get(
        "status") not in {None, "OK"})

    return {
        "run_id": payload.get("run_id"),
        "artifact_name": path.name,
        "objective": payload.get("objective"),
        "dataset": {
            "path_basename": dataset_basename,
            "path_hash": dataset_hash,
        },
        "model": {
            "name": model_name,
            "version": model_version,
        },
        "limits": {
            "max_steps": payload.get("max_steps"),
        },
        "run_counts": {
            "total_steps": len(step_trace),
            "error_steps": error_steps,
            "contradiction_count": len(list(payload.get("contradiction_memory", []) or [])),
            "target_card_count": len(feature_cards),
        },
        "tool_frequency": dict(sorted(tool_frequency.items())),
        "step_type_frequency": dict(sorted(step_type_frequency.items())),
        "signal_frequency": dict(sorted(signal_frequency.items())),
        "step_trace": step_trace,
        "feature_cards": feature_cards,
        "contradictions": _build_contradictions(payload),
        "errors": _build_errors(payload),
    }


def export_jif(
    run_paths: list[str] | None = None,
    latest: int = 5,
    *,
    exported_at: str | None = None,
) -> dict[str, Any]:
    resolved_paths = _resolve_run_paths(run_paths, latest)
    payloads = [(path, load_json(path)) for path in resolved_paths]

    run_cards = [_build_run_card(path, payload) for path, payload in payloads]
    objective_frequency = Counter()
    dataset_frequency = Counter()
    model_name_frequency = Counter()
    model_version_frequency = Counter()
    max_steps_frequency = Counter()

    aggregate_tool_frequency = Counter()
    aggregate_step_type_frequency = Counter()
    aggregate_redundant_step_frequency = Counter()
    aggregate_signal_frequency = Counter()
    total_steps = 0

    for run_card in run_cards:
        objective_frequency.update([str(run_card.get("objective") or "")])
        dataset_frequency.update(
            [str(dict(run_card.get("dataset", {})).get("path_basename") or "unknown")])
        model_name_frequency.update(
            [str(dict(run_card.get("model", {})).get("name") or "unknown")])
        model_version_frequency.update(
            [str(dict(run_card.get("model", {})).get("version") or "unknown")])
        max_steps_frequency.update(
            [str(dict(run_card.get("limits", {})).get("max_steps"))])
        total_steps += int(dict(run_card.get("run_counts", {})
                                ).get("total_steps", 0) or 0)
        aggregate_tool_frequency.update(
            dict(run_card.get("tool_frequency", {})))
        aggregate_step_type_frequency.update(
            dict(run_card.get("step_type_frequency", {})))
        aggregate_signal_frequency.update(
            dict(run_card.get("signal_frequency", {})))
        for step in list(run_card.get("step_trace", [])):
            aggregate_redundant_step_frequency.update(
                [str(bool(step.get("redundant_step"))).lower()])

    export_timestamp = exported_at or datetime.now(UTC).isoformat()
    return {
        "header": {
            "schema_version": "jif.v2",
            "exported_at": export_timestamp,
            "run_count": len(run_cards),
            "source_run_ids": [run_card.get("run_id") for run_card in run_cards],
            "source_artifacts": [run_card.get("artifact_name") for run_card in run_cards],
            "export_scope": {
                "selection_mode": "explicit_paths" if run_paths else "latest_n",
                "selection_value": len(resolved_paths) if run_paths else latest,
            },
        },
        "cohort_context": {
            "objective_frequency": dict(sorted(objective_frequency.items())),
            "dataset_frequency": dict(sorted(dataset_frequency.items())),
            "model_name_frequency": dict(sorted(model_name_frequency.items())),
            "model_version_frequency": dict(sorted(model_version_frequency.items())),
            "max_steps_frequency": dict(sorted(max_steps_frequency.items())),
            "tool_set": sorted(get_tool_registry().keys()),
        },
        "aggregate": {
            "run_count": len(run_cards),
            "total_steps": total_steps,
            "tool_frequency": dict(sorted(aggregate_tool_frequency.items())),
            "step_type_frequency": dict(sorted(aggregate_step_type_frequency.items())),
            "redundant_step_frequency": dict(sorted(aggregate_redundant_step_frequency.items())),
            "signal_frequency": dict(sorted(aggregate_signal_frequency.items())),
        },
        "run_cards": run_cards,
    }


def save_jif_artifact(
    payload: dict[str, Any],
    output_dir: str | Path | None = None,
    prefix: str = "jif",
) -> dict[str, str]:
    target_dir = Path(output_dir) if output_dir else DEFAULT_JIF_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    json_path = target_dir / f"{prefix}_{timestamp}.json"
    write_json(json_path, payload)
    return {"jif_json_path": str(json_path)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export neutral Judge Input Format payloads from persisted run logs."
    )
    parser.add_argument("run_paths", nargs="*",
                        help="Optional explicit run JSON paths")
    parser.add_argument("--latest", type=int, default=5,
                        help="Use the latest N runs when no paths are provided")
    parser.add_argument("--save", action="store_true",
                        help="Save the JIF JSON under reports/jif")
    parser.add_argument(
        "--output-dir", help="Optional custom output directory for the JIF JSON")
    parser.add_argument("--prefix", default="jif",
                        help="Filename prefix for saved JIF artifacts")
    args = parser.parse_args()

    payload = export_jif(run_paths=args.run_paths or None, latest=args.latest)
    print(json.dumps(payload, indent=2, ensure_ascii=True))

    if args.save:
        artifact_paths = save_jif_artifact(
            payload, output_dir=args.output_dir, prefix=args.prefix)
        print()
        print(json.dumps(artifact_paths, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
