"""Post-run judge orchestration over JIF payloads."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable

from experiments.export_jif import export_jif
from judge.judge_parser import VALID_EVIDENCE_REFERENCES, parse_judge_response
from utils.run_logging import load_json, write_json


DEFAULT_JUDGE_DIR = Path(__file__).resolve(
).parent.parent / "reports" / "judge"
PROMPT_TEMPLATE_PATH = Path(__file__).with_name("judge_prompt.txt")
JudgeCallable = Callable[[str], str]


def _empty_jif_payload() -> dict[str, Any]:
    return {
        "header": {
            "schema_version": "jif.v2",
            "exported_at": datetime.now(UTC).isoformat(),
            "run_count": 0,
            "source_run_ids": [],
            "source_artifacts": [],
            "export_scope": {
                "selection_mode": "empty",
                "selection_value": 0,
            },
        },
        "cohort_context": {
            "objective_frequency": {},
            "dataset_frequency": {},
            "model_name_frequency": {},
            "model_version_frequency": {},
            "max_steps_frequency": {},
            "tool_set": [],
        },
        "aggregate": {
            "run_count": 0,
            "total_steps": 0,
            "tool_frequency": {},
            "step_type_frequency": {},
            "redundant_step_frequency": {},
            "signal_frequency": {},
        },
        "run_cards": [],
    }


def merge_jif_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple JIF payloads without recomputing metrics from raw cards."""
    if not payloads:
        return _empty_jif_payload()
    if len(payloads) == 1:
        return dict(payloads[0])

    merged = _empty_jif_payload()

    source_run_ids: list[Any] = []
    source_artifacts: list[Any] = []
    run_cards: list[Any] = []
    objective_frequency: Counter[str] = Counter()
    dataset_frequency: Counter[str] = Counter()
    model_name_frequency: Counter[str] = Counter()
    model_version_frequency: Counter[str] = Counter()
    max_steps_frequency: Counter[str] = Counter()
    tool_set: set[str] = set()

    aggregate_run_count = 0
    aggregate_total_steps = 0
    aggregate_tool_frequency: Counter[str] = Counter()
    aggregate_step_type_frequency: Counter[str] = Counter()
    aggregate_redundant_step_frequency: Counter[str] = Counter()
    aggregate_signal_frequency: Counter[str] = Counter()

    for payload in payloads:
        header = dict(payload.get("header", {}) or {})
        source_run_ids.extend(list(header.get("source_run_ids", []) or []))
        source_artifacts.extend(list(header.get("source_artifacts", []) or []))
        run_cards.extend(list(payload.get("run_cards", []) or []))

        cohort_context = dict(payload.get("cohort_context", {}) or {})
        objective_frequency.update(
            dict(cohort_context.get("objective_frequency", {}) or {}))
        dataset_frequency.update(
            dict(cohort_context.get("dataset_frequency", {}) or {}))
        model_name_frequency.update(
            dict(cohort_context.get("model_name_frequency", {}) or {}))
        model_version_frequency.update(
            dict(cohort_context.get("model_version_frequency", {}) or {}))
        max_steps_frequency.update(
            dict(cohort_context.get("max_steps_frequency", {}) or {}))
        tool_set.update(str(tool) for tool in list(
            cohort_context.get("tool_set", []) or []) if isinstance(tool, str))

        aggregate = dict(payload.get("aggregate", {}) or {})
        try:
            aggregate_run_count += int(aggregate.get("run_count", 0) or 0)
        except Exception:
            pass
        try:
            aggregate_total_steps += int(aggregate.get("total_steps", 0) or 0)
        except Exception:
            pass
        aggregate_tool_frequency.update(
            dict(aggregate.get("tool_frequency", {}) or {}))
        aggregate_step_type_frequency.update(
            dict(aggregate.get("step_type_frequency", {}) or {}))
        aggregate_redundant_step_frequency.update(
            dict(aggregate.get("redundant_step_frequency", {}) or {}))
        aggregate_signal_frequency.update(
            dict(aggregate.get("signal_frequency", {}) or {}))

    merged["header"] = {
        "schema_version": str(dict(payloads[0].get("header", {}) or {}).get("schema_version") or "jif.v2"),
        "exported_at": datetime.now(UTC).isoformat(),
        "run_count": aggregate_run_count,
        "source_run_ids": source_run_ids,
        "source_artifacts": source_artifacts,
        "export_scope": {
            "selection_mode": "existing_jif_files",
            "selection_value": len(payloads),
        },
    }
    merged["cohort_context"] = {
        "objective_frequency": dict(sorted(objective_frequency.items())),
        "dataset_frequency": dict(sorted(dataset_frequency.items())),
        "model_name_frequency": dict(sorted(model_name_frequency.items())),
        "model_version_frequency": dict(sorted(model_version_frequency.items())),
        "max_steps_frequency": dict(sorted(max_steps_frequency.items())),
        "tool_set": sorted(tool_set),
    }
    merged["aggregate"] = {
        "run_count": aggregate_run_count,
        "total_steps": aggregate_total_steps,
        "tool_frequency": dict(sorted(aggregate_tool_frequency.items())),
        "step_type_frequency": dict(sorted(aggregate_step_type_frequency.items())),
        "redundant_step_frequency": dict(sorted(aggregate_redundant_step_frequency.items())),
        "signal_frequency": dict(sorted(aggregate_signal_frequency.items())),
    }
    merged["run_cards"] = run_cards
    return merged


def load_jif_payloads(jif_paths: list[str]) -> list[dict[str, Any]]:
    return [load_json(path) for path in jif_paths]


def build_jif_from_run_paths(run_paths: list[str] | None = None, latest: int = 5) -> dict[str, Any]:
    return export_jif(run_paths=run_paths, latest=latest)


def _resolve_judge_mode(payload: dict[str, Any], requested_mode: str | None = None) -> str:
    run_count = len(list(payload.get("run_cards", []) or []))
    if requested_mode == "single_run" and run_count > 1:
        raise ValueError(
            "single-run mode requires exactly one run in the JIF payload")
    if requested_mode in {"single_run", "multi_run"}:
        return requested_mode
    return "single_run" if run_count <= 1 else "multi_run"


def _build_openai_judge_callable(model_name: str, temperature: float = 0.0) -> JudgeCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run the judge.") from exc

        client = OpenAI()
        response = client.responses.create(
            model=model_name,
            input=prompt_text,
            temperature=temperature,
        )
        return response.output_text

    return _call_llm


def build_judge_prompt(payload: dict[str, Any], mode: str) -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{{VALID_EVIDENCE_REFERENCES}}", json.dumps(
            sorted(VALID_EVIDENCE_REFERENCES), ensure_ascii=True))
        .replace("{{JUDGE_MODE}}", mode)
        .replace("{{JIF_JSON}}", json.dumps(payload, indent=2, ensure_ascii=True))
    )


def render_judge_report_text(payload: dict[str, Any], report: dict[str, Any], mode: str, model_name: str) -> str:
    aggregate = dict(payload.get("aggregate", {}) or {})
    lines = [
        "JUDGE REPORT",
        f"- mode: {mode}",
        f"- model: {model_name}",
        f"- runs: {aggregate.get('run_count', 0)}",
        f"- total_steps: {aggregate.get('total_steps', 0)}",
        "",
        "Behavior Summary",
        report.get("behavior_summary", "No behavior summary available."),
        "",
    ]

    def add_claim_section(title: str, items: list[dict[str, Any]]) -> None:
        lines.append(title)
        if not items:
            lines.append("- none")
            lines.append("")
            return
        for item in items:
            lines.append(f"- {item.get('statement', '')}")
            lines.append(f"  confidence: {item.get('confidence', 'low')}")
            lines.append("  evidence: " + ", ".join(item.get("evidence", [])))
        lines.append("")

    add_claim_section("Key Patterns", list(report.get("key_patterns", [])))
    add_claim_section("Weaknesses", list(report.get("weaknesses", [])))
    add_claim_section("Strengths", list(report.get("strengths", [])))
    add_claim_section("Recommendations", list(
        report.get("recommendations", [])))
    return "\n".join(lines).rstrip()


def save_judge_artifacts(
    report: dict[str, Any],
    report_text: str,
    output_dir: str | Path | None = None,
    prefix: str = "judge",
) -> dict[str, str]:
    target_dir = Path(output_dir) if output_dir else DEFAULT_JUDGE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    text_path = target_dir / f"{prefix}_{timestamp}.txt"
    json_path = target_dir / f"{prefix}_{timestamp}.json"
    text_path.write_text(report_text, encoding="utf-8")
    write_json(json_path, report)
    return {
        "report_text_path": str(text_path),
        "report_json_path": str(json_path),
    }


def run_judge(
    payload: dict[str, Any],
    *,
    model_name: str,
    mode: str | None = None,
    llm_callable: JudgeCallable | None = None,
    output_dir: str | Path | None = None,
    prefix: str = "judge",
) -> dict[str, Any]:
    resolved_mode = _resolve_judge_mode(payload, requested_mode=mode)
    prompt_text = build_judge_prompt(payload, resolved_mode)
    judge_callable = llm_callable or _build_openai_judge_callable(model_name)
    raw_response = judge_callable(prompt_text)
    parsed_report = parse_judge_response(raw_response)
    report_text = render_judge_report_text(
        payload, parsed_report, resolved_mode, model_name)
    artifact_paths = save_judge_artifacts(
        parsed_report, report_text, output_dir=output_dir, prefix=prefix)
    return {
        "mode": resolved_mode,
        "model_name": model_name,
        "report": parsed_report,
        "report_text": report_text,
        "artifact_paths": artifact_paths,
    }
