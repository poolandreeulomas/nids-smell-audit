"""Evaluate and compare multiple run logs with deterministic heuristics."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from analysis.interpreter import extract_run_insights
from analysis.scoring import score_run
from utils.metrics import compute_overlap_score
from utils.run_logging import DEFAULT_RUNS_DIR, load_json


DEFAULT_EVALUATIONS_DIR = Path(__file__).resolve(
).parent.parent / "reports" / "evaluations"


def _resolve_run_paths(run_paths: list[str] | None, latest: int) -> list[Path]:
    if run_paths:
        return [Path(path) for path in run_paths]

    candidates = sorted(
        path
        for path in DEFAULT_RUNS_DIR.glob("run_*.json")
        if not path.name.endswith("_metrics.json") and path.name != "run_test_metrics.json"
    )
    return candidates[-latest:]


def _summarize_scores(scores: list[float]) -> dict[str, float]:
    if not scores:
        return {"average": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}
    return {
        "average": round(mean(scores), 1),
        "median": round(median(scores), 1),
        "min": round(min(scores), 1),
        "max": round(max(scores), 1),
        "std": round(pstdev(scores), 1),
    }


def _summarize_numeric_values(values: list[float]) -> dict[str, float]:
    if not values:
        return {"average": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "average": round(mean(values), 2),
        "median": round(median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def _build_run_metrics_summary(run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    steps = [
        float(dict(summary.get("insights", {})).get(
            "behavior", {}).get("num_steps", 0) or 0)
        for summary in run_summaries
    ]
    errors = [
        float(dict(summary.get("insights", {})).get(
            "behavior", {}).get("num_errors", 0) or 0)
        for summary in run_summaries
    ]
    features_attempted = [
        float(dict(summary.get("insights", {})).get(
            "behavior", {}).get("unique_features_attempted", 0) or 0)
        for summary in run_summaries
    ]
    features_successful = [
        float(dict(summary.get("insights", {})).get(
            "behavior", {}).get("unique_features_successful", 0) or 0)
        for summary in run_summaries
    ]
    valid_action_rates = [
        float(dict(summary.get("metrics", {})).get(
            "valid_action_rate", 0.0) or 0.0)
        for summary in run_summaries
    ]
    tool_error_rates = [
        float(dict(summary.get("metrics", {})).get(
            "tool_error_rate", 0.0) or 0.0)
        for summary in run_summaries
    ]

    return {
        "steps": _summarize_numeric_values(steps),
        "errors": _summarize_numeric_values(errors),
        "features_attempted": _summarize_numeric_values(features_attempted),
        "features_successful": _summarize_numeric_values(features_successful),
        "valid_action_rate": _summarize_numeric_values(valid_action_rates),
        "tool_error_rate": _summarize_numeric_values(tool_error_rates),
    }


def _compute_consistency(run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    top1_values = [
        summary["insights"]["top_features"][0]
        for summary in run_summaries
        if summary["insights"].get("top_features")
    ]
    top1_counter = Counter(top1_values)
    most_common_top1, top1_count = top1_counter.most_common(
        1)[0] if top1_counter else (None, 0)

    top3_lists = [summary["insights"].get(
        "top_features", []) for summary in run_summaries]
    pairwise_overlaps = []
    for left, right in combinations(top3_lists, 2):
        pairwise_overlaps.append(compute_overlap_score(left, right))

    return {
        "most_common_top1": most_common_top1,
        "top1_stability": round(top1_count / len(run_summaries), 2) if run_summaries else 0.0,
        "average_top3_overlap": round(mean(pairwise_overlaps), 2) if pairwise_overlaps else 1.0,
    }


def _collect_feature_frequency(run_summaries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    top_feature_counter: Counter[str] = Counter()
    confirmed_feature_counter: Counter[str] = Counter()

    for summary in run_summaries:
        top_feature_counter.update(summary.get("top_features", []))
        confirmed_feature_counter.update(
            summary.get("insights", {}).get(
                "patterns", {}).get("confirmed_features", [])
        )

    return {
        "top_features": dict(top_feature_counter.most_common()),
        "confirmed_features": dict(confirmed_feature_counter.most_common()),
    }


def _collect_error_frequency(run_summaries: list[dict[str, Any]]) -> dict[str, int]:
    error_counter: Counter[str] = Counter()
    for summary in run_summaries:
        for error in summary.get("insights", {}).get("errors", []):
            feature_name = error.get("feature_name")
            error_code = error.get("error_code")
            key = f"{feature_name}:{error_code}"
            error_counter[key] += 1
    return dict(error_counter.most_common())


def _build_executive_summary(run_summaries: list[dict[str, Any]], aggregate: dict[str, Any]) -> dict[str, Any]:
    run_count = len(run_summaries)
    score_summary = dict(aggregate.get("score_summary", {}))
    consistency = dict(aggregate.get("consistency", {}))
    verdict_counts = dict(aggregate.get("verdict_counts", {}))
    feature_frequency = _collect_feature_frequency(run_summaries)
    error_frequency = _collect_error_frequency(run_summaries)

    strong_or_promising = verdict_counts.get(
        "strong", 0) + verdict_counts.get("promising", 0)
    if run_count == 0:
        trust_label = "no-data"
    elif strong_or_promising == run_count and score_summary.get("average", 0.0) >= 80.0:
        trust_label = "high"
    elif score_summary.get("average", 0.0) >= 70.0:
        trust_label = "moderate"
    else:
        trust_label = "low"

    dominant_top_feature = consistency.get("most_common_top1")
    common_confirmed_feature = next(
        iter(feature_frequency.get("confirmed_features", {})), None)
    common_error = next(iter(error_frequency), None)

    discoveries: list[str] = []
    if dominant_top_feature:
        discoveries.append(
            f"Most recurrent top discovery: {dominant_top_feature}."
        )
    if common_confirmed_feature:
        discoveries.append(
            f"Most frequently confirmed feature: {common_confirmed_feature}."
        )
    if aggregate.get("both_tools_rate", 0.0) >= 0.8:
        discoveries.append(
            "The agent consistently used both tools across runs.")
    if consistency.get("top1_stability", 0.0) >= 0.6:
        discoveries.append(
            "Top-1 feature stability is moderate to good across runs.")

    limitations: list[str] = []
    if common_error:
        limitations.append(f"Most common failure pattern: {common_error}.")
    if consistency.get("average_top3_overlap", 0.0) < 0.4:
        limitations.append(
            "Top-3 overlap is still low, so exploration is not fully stable yet.")
    if aggregate.get("error_reaction_rate", 0.0) < 1.0:
        limitations.append(
            "The agent reacts to many errors, but not all of them.")

    headline = (
        f"Across {run_count} run(s), the agent achieved an average score of "
        f"{score_summary.get('average', 0.0)}/100 with {trust_label} trust for exploratory use."
    )

    return {
        "headline": headline,
        "trust_label": trust_label,
        "discoveries": discoveries,
        "limitations": limitations,
        "feature_frequency": feature_frequency,
        "error_frequency": error_frequency,
    }


def evaluate_runs(run_paths: list[str] | None = None, latest: int = 5) -> dict[str, Any]:
    resolved_paths = _resolve_run_paths(run_paths, latest)
    run_summaries = []

    for path in resolved_paths:
        payload = load_json(path)
        insights = extract_run_insights(payload)
        scoring = score_run(insights)
        metrics = dict(payload.get("metrics", {}))
        run_summaries.append(
            {
                "path": str(path),
                "run_id": payload.get("run_id"),
                "top_features": insights.get("top_features", []),
                "score": scoring,
                "metrics": metrics,
                "insights": insights,
            }
        )

    run_summaries.sort(
        key=lambda summary: (
            float(summary["score"]["score"]),
            len(summary.get("top_features", [])),
        ),
        reverse=True,
    )

    scores = [summary["score"]["score"] for summary in run_summaries]
    both_tools_rate = _safe_rate(
        sum(1 for summary in run_summaries if summary["insights"]["behavior"].get(
            "used_both_tools")),
        len(run_summaries),
    )
    error_reaction_rate = _safe_rate(
        sum(1 for summary in run_summaries if summary["insights"]["patterns"].get(
            "reacted_to_errors")),
        len(run_summaries),
    )
    verdict_counts = Counter(summary["score"]["verdict"]
                             for summary in run_summaries)
    top1_counter = Counter(
        summary["top_features"][0]
        for summary in run_summaries
        if summary.get("top_features")
    )

    aggregate = {
        "run_count": len(run_summaries),
        "score_summary": _summarize_scores(scores),
        "run_metrics_summary": _build_run_metrics_summary(run_summaries),
        "consistency": _compute_consistency(run_summaries),
        "both_tools_rate": round(both_tools_rate, 2),
        "error_reaction_rate": round(error_reaction_rate, 2),
        "verdict_counts": dict(verdict_counts),
        "top1_frequency": dict(top1_counter.most_common()),
    }
    aggregate["executive_summary"] = _build_executive_summary(
        run_summaries, aggregate)
    return {"runs": run_summaries, "aggregate": aggregate}


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _format_run_block(run_summary: dict[str, Any]) -> list[str]:
    scoring = dict(run_summary.get("score", {}))
    insights = dict(run_summary.get("insights", {}))
    behavior = dict(insights.get("behavior", {}))
    breakdown = dict(scoring.get("breakdown", {}))
    strengths = list(scoring.get("strengths", []))
    risks = list(scoring.get("risks", []))

    lines = [
        f"RUN: {Path(run_summary['path']).name}",
        f"- Score: {scoring.get('score', 0.0)}/100 ({scoring.get('verdict', 'unknown')})",
        f"- Top features: {', '.join(run_summary.get('top_features', [])) or 'none'}",
        f"- Steps: {behavior.get('num_steps', 0)} | Errors: {behavior.get('num_errors', 0)} | Both tools: {behavior.get('used_both_tools', False)}",
        "- Breakdown: "
        f"execution={breakdown.get('execution', 0.0)}, "
        f"reasoning={breakdown.get('reasoning', 0.0)}, "
        f"exploration={breakdown.get('exploration', 0.0)}, "
        f"signal={breakdown.get('signal', 0.0)}, "
        f"stability_bonus={breakdown.get('stability_bonus', 0.0)}",
    ]
    if strengths:
        lines.append("- Strengths: " + "; ".join(strengths))
    if risks:
        lines.append("- Risks: " + "; ".join(risks))
    return lines


def _format_ranking(result: dict[str, Any]) -> list[str]:
    lines = ["RANKING"]
    for index, run_summary in enumerate(result.get("runs", []), start=1):
        score = run_summary.get("score", {})
        lines.append(
            f"{index}. {Path(run_summary['path']).name} -> {score.get('score', 0.0)}/100 ({score.get('verdict', 'unknown')})"
        )
    lines.append("")
    return lines


def _format_aggregate_findings(aggregate: dict[str, Any]) -> list[str]:
    verdict_counts = dict(aggregate.get("verdict_counts", {}))
    top1_frequency = dict(aggregate.get("top1_frequency", {}))

    lines = [
        "AGGREGATE FINDINGS",
        "- Verdict counts: " +
        (json.dumps(verdict_counts, ensure_ascii=True) if verdict_counts else "{}"),
        "- Top-1 frequency: " +
        (json.dumps(top1_frequency, ensure_ascii=True) if top1_frequency else "{}"),
        "",
    ]
    return lines


def _format_executive_summary(aggregate: dict[str, Any]) -> list[str]:
    executive_summary = dict(aggregate.get("executive_summary", {}))
    discoveries = list(executive_summary.get("discoveries", []))
    limitations = list(executive_summary.get("limitations", []))

    lines = [
        "EXECUTIVE SUMMARY",
        executive_summary.get("headline", "No executive summary available."),
    ]

    if discoveries:
        lines.append("Key discoveries:")
        lines.extend(f"- {item}" for item in discoveries)

    if limitations:
        lines.append("Main limitations:")
        lines.extend(f"- {item}" for item in limitations)

    lines.append("")
    return lines


def save_evaluation_artifacts(
    result: dict[str, Any],
    report_text: str,
    output_dir: str | Path | None = None,
    prefix: str = "evaluation",
) -> dict[str, str]:
    target_dir = Path(output_dir) if output_dir else DEFAULT_EVALUATIONS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")

    text_path = target_dir / f"{prefix}_{timestamp}.txt"
    json_path = target_dir / f"{prefix}_{timestamp}.json"

    text_path.write_text(report_text, encoding="utf-8")
    json_path.write_text(json.dumps(
        result, indent=2, ensure_ascii=True), encoding="utf-8")
    return {
        "report_text_path": str(text_path),
        "report_json_path": str(json_path),
    }


def render_evaluation_report(result: dict[str, Any]) -> str:
    aggregate = dict(result.get("aggregate", {}))
    score_summary = dict(aggregate.get("score_summary", {}))
    consistency = dict(aggregate.get("consistency", {}))

    lines = [
        "RUN EVALUATION REPORT",
        f"- Runs analyzed: {aggregate.get('run_count', 0)}",
        f"- Average score: {score_summary.get('average', 0.0)}/100",
        f"- Score range: {score_summary.get('min', 0.0)} to {score_summary.get('max', 0.0)}",
        f"- Score std: {score_summary.get('std', 0.0)}",
        f"- Most common Top-1: {consistency.get('most_common_top1') or 'none'}",
        f"- Top-1 stability: {consistency.get('top1_stability', 0.0)}",
        f"- Average Top-3 overlap: {consistency.get('average_top3_overlap', 0.0)}",
        f"- Both tools rate: {aggregate.get('both_tools_rate', 0.0)}",
        f"- Error reaction rate: {aggregate.get('error_reaction_rate', 0.0)}",
        "",
    ]

    lines.extend(_format_executive_summary(aggregate))
    lines.extend(_format_ranking(result))
    lines.extend(_format_aggregate_findings(aggregate))

    for run_summary in result.get("runs", []):
        lines.extend(_format_run_block(run_summary))
        lines.append("")

    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate and compare multiple run logs with deterministic heuristics."
    )
    parser.add_argument("run_paths", nargs="*",
                        help="Optional explicit run JSON paths")
    parser.add_argument("--latest", type=int, default=5,
                        help="Use the latest N runs when no paths are provided")
    parser.add_argument("--json", action="store_true",
                        help="Print raw JSON instead of a text report")
    parser.add_argument("--save", action="store_true",
                        help="Save the text report and JSON result under reports/evaluations")
    parser.add_argument(
        "--output-dir", help="Optional custom directory for saved evaluation artifacts")
    parser.add_argument("--prefix", default="evaluation",
                        help="Filename prefix for saved evaluation artifacts")
    args = parser.parse_args()

    result = evaluate_runs(
        run_paths=args.run_paths or None, latest=args.latest)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return

    report_text = render_evaluation_report(result)
    print(report_text)

    if args.save:
        artifact_paths = save_evaluation_artifacts(
            result,
            report_text,
            output_dir=args.output_dir,
            prefix=args.prefix,
        )
        print()
        print("Saved evaluation artifacts:")
        print(json.dumps(artifact_paths, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
