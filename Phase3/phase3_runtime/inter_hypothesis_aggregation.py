"""Canonical round-level aggregation for Phase 3A.

This module replaces the old deterministic round reducer with an LLM-backed
component that preserves source hypothesis records as the canonical artifact.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from time import perf_counter
import re
from typing import Any, Callable

from instrumentation import exception, phase_end, phase_start, validation_result
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from utils.run_logging import load_json, write_json


SCHEMA_VERSION = "phase3a.inter_hypothesis_aggregation.v1"
PROMPT_VERSION = "phase3a.inter_hypothesis_aggregation.prompt.v1"
DEFAULT_INTER_HYPOTHESIS_DIR = Path(__file__).resolve(
).parent.parent / "logs" / "inter_hypothesis_aggregation_runs"
_RUN_INDEX_PATTERN = re.compile(
    r"^inter_hypothesis_aggregation_run_(?P<index>\d{3})_")


def _string_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string_list(values: object, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        stripped = _string_value(value)
        if stripped:
            normalized.append(stripped)
    if not allow_empty and not normalized:
        return []
    return list(dict.fromkeys(normalized))


def _json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _format_round_tag(round_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_",
                        str(round_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_round"


def _format_batch_tag(batch_id: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_",
                        str(batch_id or "").strip().lower()).strip("_")
    return normalized[:40] or "unknown_batch"


def _llm_callable_for(model_name: str, temperature: float = 0.0) -> Callable[[str], str]:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run the inter-hypothesis aggregator."
            ) from exc

        client = OpenAI()
        response = client.responses.create(
            **build_responses_create_kwargs(
                model_name=model_name,
                prompt_text=prompt_text,
                temperature=temperature,
            )
        )
        return extract_response_text(response)

    return _call_llm


def _report_error(field: str, message: str) -> dict[str, Any]:
    return {"ok": False, "errors": [{"field": field, "message": message}], "warnings": []}


def ensure_inter_hypothesis_aggregation_runs_dir(
    log_dir: str | Path | None = None,
) -> Path:
    target = Path(log_dir) if log_dir else DEFAULT_INTER_HYPOTHESIS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_inter_hypothesis_aggregation_run_index(log_dir: str | Path | None = None) -> int:
    runs_dir = ensure_inter_hypothesis_aggregation_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def build_inter_hypothesis_aggregation_run_basename(
    batch_id: str,
    round_id: str,
    *,
    timestamp: datetime | None = None,
    run_index: int | None = None,
    log_dir: str | Path | None = None,
) -> str:
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_inter_hypothesis_aggregation_run_index(
        log_dir)
    return "inter_hypothesis_aggregation_run_{index:03d}_{day_month}_{batch_tag}_{round_tag}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        batch_tag=_format_batch_tag(batch_id),
        round_tag=_format_round_tag(round_id),
    )


def build_inter_hypothesis_aggregation_artifact_paths(
    *,
    batch_id: str,
    round_id: str,
    log_dir: str | Path | None = None,
) -> dict[str, Path]:
    runs_dir = ensure_inter_hypothesis_aggregation_runs_dir(log_dir)
    run_dir = runs_dir / build_inter_hypothesis_aggregation_run_basename(
        batch_id,
        round_id,
        log_dir=log_dir,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "component_run_path": run_dir / "component_run.json",
        "rendered_prompt_path": run_dir / "rendered_prompt.txt",
        "raw_response_path": run_dir / "raw_response.txt",
        "parsed_output_path": run_dir / "parsed_output.json",
        "validation_report_path": run_dir / "validation_report.json",
        "runtime_metrics_path": run_dir / "runtime_metrics.json",
        "replay_metadata_path": run_dir / "replay_metadata.json",
    }


def _source_record_lists(bundle: dict[str, Any]) -> dict[str, list[str]]:
    handoff = dict(bundle.get("aggregation_handoff", {}) or {})
    normalized_inputs = dict(bundle.get("normalized_inputs", {}) or {})
    confidence_signals = bundle.get("confidence_signals")
    source_confidence_signals = _string_list(
        confidence_signals) if confidence_signals is not None else []
    return {
        "merged_findings": [str(item).strip() for item in handoff.get("merged_findings", []) if str(item).strip()],
        "evidence_refs": [str(item).strip() for item in handoff.get("evidence_refs", []) if str(item).strip()],
        "preserved_contradictions": [str(item).strip() for item in handoff.get("preserved_contradictions", []) if str(item).strip()],
        "open_gaps": [str(item).strip() for item in handoff.get("open_gaps", []) if str(item).strip()],
        "limitations": [str(item).strip() for item in normalized_inputs.get("source_limitations", []) if str(item).strip()],
        "confidence_signals": source_confidence_signals,
    }


def build_source_hypothesis_records(
    *,
    batch_id: str,
    round_id: str,
    selected_hypothesis_ids: list[str],
    source_aggregation_bundles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    aggregation_by_hypothesis_id = {
        str(dict(bundle.get("component_run", {}) or {}).get("hypothesis_id") or "").strip(): bundle
        for bundle in source_aggregation_bundles
        if str(dict(bundle.get("component_run", {}) or {}).get("hypothesis_id") or "").strip()
    }

    source_records: list[dict[str, Any]] = []
    for source_order, hypothesis_id in enumerate(selected_hypothesis_ids):
        bundle = aggregation_by_hypothesis_id.get(hypothesis_id, {})
        component_run = dict(bundle.get("component_run", {}) or {})
        artifact_paths = dict(bundle.get("artifact_paths", {}) or {})
        normalized_inputs = dict(bundle.get("normalized_inputs", {}) or {})
        handoff = dict(bundle.get("aggregation_handoff", {}) or {})
        source_lists = _source_record_lists(bundle)
        source_run_dirs = [str(item).strip() for item in normalized_inputs.get(
            "source_run_dirs", []) if str(item).strip()]
        record = {
            "hypothesis_id": hypothesis_id,
            "aggregation_run_path": str(artifact_paths.get("component_run_path", "") or "").strip(),
            "merged_findings": source_lists["merged_findings"],
            "evidence_refs": source_lists["evidence_refs"],
            "preserved_contradictions": source_lists["preserved_contradictions"],
            "open_gaps": source_lists["open_gaps"],
            "limitations": source_lists["limitations"],
            "update_focus": str(handoff.get("update_focus") or "").strip(),
            "provenance": {
                "batch_id": batch_id,
                "round_id": round_id,
                "source_order": source_order,
                "source_aggregation_component_run_path": str(artifact_paths.get("component_run_path", "") or "").strip(),
                "source_worker_result_set_path": str(artifact_paths.get("worker_result_set_path", "") or "").strip(),
                "source_normalized_inputs_path": str(artifact_paths.get("normalized_inputs_path", "") or "").strip(),
                "source_run_dirs": source_run_dirs,
                "source_validation_ok": bool(dict(bundle.get("validation_report", {}) or {}).get("ok", False)),
                "source_status": str(component_run.get("status") or "").strip(),
            },
        }
        confidence_signals = source_lists.get("confidence_signals", [])
        if confidence_signals:
            record["confidence_signals"] = confidence_signals
        source_records.append(record)
    return source_records


def build_inter_hypothesis_prompt(
    *,
    batch_id: str,
    round_id: str,
    selected_hypothesis_ids: list[str],
    source_hypothesis_records: list[dict[str, Any]],
) -> str:
    sections = [
        "",
        "=== CRITICAL OUTPUT COMPLIANCE REQUIREMENT ===",
        "",
        "THE OUTPUT CONTRACT IS THE HIGHEST PRIORITY REQUIREMENT IN THIS PROMPT.",
        "",
        "BEFORE RETURNING ANY RESPONSE:",
        "",
        "1. VERIFY THAT THE RESPONSE EXACTLY MATCHES THE REQUIRED OUTPUT SCHEMA.",
        "2. VERIFY THAT NO REQUIRED FIELD IS MISSING.",
        "3. VERIFY THAT NO EXTRA FIELD IS PRESENT.",
        "4. VERIFY THAT ALL ENUM VALUES ARE VALID.",
        "5. VERIFY THAT ALL REQUIRED LISTS ARE PRESENT AND CORRECTLY TYPED.",
        "6. IF ANY PART OF THE RESPONSE WOULD VIOLATE THE OUTPUT CONTRACT, REVISE THE RESPONSE BEFORE RETURNING IT.",
        "",
        "OUTPUT CONTRACT COMPLIANCE TAKES PRIORITY OVER REASONING COMPLETENESS.",
        "",
        "DO NOT RETURN AN APPROXIMATE RESPONSE.",
        "DO NOT RETURN A PARTIALLY VALID RESPONSE.",
        "DO NOT RETURN ADDITIONAL EXPLANATIONS.",
        "DO NOT RETURN MARKDOWN.",
        "DO NOT RETURN CODE FENCES.",
        "",
        "DO NOT INFER PERMITTED OUTPUTS.",
        "DO NOT GENERALIZE THE SCHEMA.",
        "ONLY EMIT FIELDS AND VALUES EXPLICITLY ALLOWED.",
        "",
        "FINAL CHECK:",
        "",
        "IMMEDIATELY BEFORE PRODUCING THE RESPONSE,",
        "PERFORM A SELF-CHECK AGAINST THE OUTPUT RULES.",
        "",
        "IF THE RESPONSE DOES NOT SATISFY EVERY OUTPUT RULE,",
        "REWRITE IT BEFORE RETURNING IT.",
        "",
        "OUTPUT VALIDITY IS MORE IMPORTANT THAN ANALYSIS QUALITY.",
        "",
        "RETURN ONLY A FULLY VALID OUTPUT OBJECT.",
        "",
        "ROLE:",
        "You are the Inter-Hypothesis Aggregator.",
        "Preserve semantic information, provenance, uncertainty, contradictions, gaps, limitations, and evidence references.",
        "Do not compress aggressively.",
        "Do not generate a human summary first.",
        "The JSON you return is the canonical source of truth for this round.",
        "",
        "TASK:",
        _json_block(
            {
                "batch_id": batch_id,
                "round_id": round_id,
                "selected_hypothesis_ids": selected_hypothesis_ids,
            }
        ),
        "",
        "SOURCE_HYPOTHESIS_RECORDS:",
        _json_block(source_hypothesis_records),
        "",
        "OUTPUT_RULES:",
        "Return exactly one JSON object.",
        "The object must contain exactly batch_id, round_id, selected_hypothesis_ids, and source_hypothesis_records.",
        "Keep source_hypothesis_records in the same order as selected_hypothesis_ids.",
        "Preserve findings, contradictions, limitations, open gaps, confidence signals, evidence references, and provenance.",
        "Only remove exact redundancy when meaning, provenance, and uncertainty remain fully preserved.",
        "Do not create graphs, edges, inference networks, or topology layers.",
        "Do not flatten all hypotheses into a single list of findings.",
        _json_block(
            {
                "batch_id": batch_id,
                "round_id": round_id,
                "selected_hypothesis_ids": selected_hypothesis_ids,
                "source_hypothesis_records": [
                    {
                        "hypothesis_id": "hypothesis_id",
                        "aggregation_run_path": "source/aggregation/component_run.json",
                        "merged_findings": ["preserved merged finding"],
                        "evidence_refs": ["preserved_evidence_ref"],
                        "preserved_contradictions": ["preserved contradiction"],
                        "open_gaps": ["preserved gap"],
                        "limitations": ["preserved limitation"],
                        "update_focus": "preserved focus",
                        "provenance": {
                            "batch_id": batch_id,
                            "round_id": round_id,
                            "source_order": 0,
                            "source_aggregation_component_run_path": "source/aggregation/component_run.json",
                            "source_worker_result_set_path": "source/aggregation/worker_result_set.json",
                            "source_normalized_inputs_path": "source/aggregation/normalized_inputs.json",
                            "source_run_dirs": ["source/worker/run_dir"],
                            "source_validation_ok": True,
                            "source_status": "ok",
                        },
                    }
                ],
            }
        ),
    ]
    return "\n".join(sections).strip() + "\n"


def parse_inter_hypothesis_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError(
            "inter-hypothesis aggregation response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "inter-hypothesis aggregation response must be a JSON object")

    required_fields = {
        "batch_id",
        "round_id",
        "selected_hypothesis_ids",
        "source_hypothesis_records",
    }
    if set(payload.keys()) != required_fields:
        raise ValueError(
            "inter-hypothesis aggregation response must contain exactly batch_id, round_id, selected_hypothesis_ids, source_hypothesis_records"
        )
    return payload


def validate_inter_hypothesis_artifact(
    parsed_output: dict[str, Any],
    *,
    expected_batch_id: str,
    expected_round_id: str,
    selected_hypothesis_ids: list[str],
    source_aggregation_bundles: list[dict[str, Any]],
) -> dict[str, Any]:
    raw = parsed_output if isinstance(parsed_output, dict) else {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    expected_fields = {
        "batch_id",
        "round_id",
        "selected_hypothesis_ids",
        "source_hypothesis_records",
    }
    unsupported_fields = sorted(set(raw.keys()) - expected_fields)
    if unsupported_fields:
        errors.append(
            {"field": "parsed_output",
                "message": f"parsed_output contains unsupported fields: {unsupported_fields}."}
        )

    if _string_value(raw.get("batch_id")) != expected_batch_id:
        errors.append(
            {"field": "batch_id", "message": f"batch_id must match '{expected_batch_id}'."})
    if _string_value(raw.get("round_id")) != expected_round_id:
        errors.append(
            {"field": "round_id", "message": f"round_id must match '{expected_round_id}'."})

    output_selected_ids = _string_list(
        raw.get("selected_hypothesis_ids"), allow_empty=False)
    expected_selected_ids = _string_list(
        selected_hypothesis_ids, allow_empty=False)
    if not output_selected_ids:
        errors.append({"field": "selected_hypothesis_ids",
                      "message": "selected_hypothesis_ids must be a non-empty list of strings."})
    elif output_selected_ids != expected_selected_ids:
        errors.append({"field": "selected_hypothesis_ids",
                      "message": "selected_hypothesis_ids must preserve the selected hypothesis ordering."})

    source_records = raw.get("source_hypothesis_records")
    if not isinstance(source_records, list) or not source_records:
        errors.append({"field": "source_hypothesis_records",
                      "message": "source_hypothesis_records must be a non-empty list."})
        source_records = []

    expected_records = build_source_hypothesis_records(
        batch_id=expected_batch_id,
        round_id=expected_round_id,
        selected_hypothesis_ids=expected_selected_ids,
        source_aggregation_bundles=source_aggregation_bundles,
    )
    expected_by_id = {
        str(record.get("hypothesis_id") or "").strip(): record
        for record in expected_records
    }
    source_bundle_by_hypothesis_id = {
        str(dict(bundle.get("component_run", {}) or {}).get("hypothesis_id") or "").strip(): bundle
        for bundle in source_aggregation_bundles
        if str(dict(bundle.get("component_run", {}) or {}).get("hypothesis_id") or "").strip()
    }

    seen_hypothesis_ids: set[str] = set()
    preservation_errors: list[dict[str, str]] = []
    provenance_errors: list[dict[str, str]] = []
    coverage_missing: list[str] = []

    for index, record in enumerate(source_records):
        field_prefix = f"source_hypothesis_records[{index}]"
        if not isinstance(record, dict):
            errors.append(
                {"field": field_prefix, "message": "Each source_hypothesis_record must be an object."})
            continue

        allowed_fields = {
            "hypothesis_id",
            "aggregation_run_path",
            "merged_findings",
            "evidence_refs",
            "preserved_contradictions",
            "open_gaps",
            "limitations",
            "update_focus",
            "provenance",
            "confidence_signals",
        }
        unsupported_record_fields = sorted(set(record.keys()) - allowed_fields)
        if unsupported_record_fields:
            errors.append(
                {"field": field_prefix, "message": f"source_hypothesis_record contains unsupported fields: {unsupported_record_fields}."}
            )

        hypothesis_id = _string_value(record.get("hypothesis_id"))
        if not hypothesis_id:
            errors.append({"field": f"{field_prefix}.hypothesis_id",
                          "message": "hypothesis_id must be a non-empty string."})
            continue
        if hypothesis_id in seen_hypothesis_ids:
            errors.append({"field": f"{field_prefix}.hypothesis_id",
                          "message": f"Duplicate hypothesis_id '{hypothesis_id}'."})
        seen_hypothesis_ids.add(hypothesis_id)
        if index >= len(expected_selected_ids) or expected_selected_ids[index] != hypothesis_id:
            errors.append({"field": f"{field_prefix}.hypothesis_id",
                          "message": "source_hypothesis_records must preserve selected_hypothesis_ids order."})

        source_bundle = source_bundle_by_hypothesis_id.get(hypothesis_id)
        expected_record = expected_by_id.get(hypothesis_id)
        if source_bundle is None or expected_record is None:
            coverage_missing.append(hypothesis_id)
            continue

        record_lists = {
            "merged_findings": _string_list(record.get("merged_findings"), allow_empty=False),
            "evidence_refs": _string_list(record.get("evidence_refs"), allow_empty=False),
            "preserved_contradictions": _string_list(record.get("preserved_contradictions")),
            "open_gaps": _string_list(record.get("open_gaps")),
            "limitations": _string_list(record.get("limitations")),
            "confidence_signals": _string_list(record.get("confidence_signals")) if "confidence_signals" in record else [],
        }
        for field_name in ("merged_findings", "evidence_refs", "preserved_contradictions", "open_gaps", "limitations"):
            if not isinstance(record.get(field_name), list):
                errors.append({"field": f"{field_prefix}.{field_name}",
                              "message": f"{field_name} must be a list of strings."})
            elif field_name in {"merged_findings", "evidence_refs"} and not record_lists[field_name]:
                errors.append({"field": f"{field_prefix}.{field_name}",
                              "message": f"{field_name} must be a non-empty list of strings."})

        if not _string_value(record.get("update_focus")):
            errors.append({"field": f"{field_prefix}.update_focus",
                          "message": "update_focus must be a non-empty string."})

        provenance = record.get("provenance")
        if not isinstance(provenance, dict):
            errors.append({"field": f"{field_prefix}.provenance",
                          "message": "provenance must be an object."})
            provenance = {}
        else:
            try:
                source_order = int(provenance.get("source_order", -1))
            except (TypeError, ValueError):
                source_order = -1
            if source_order != index:
                provenance_errors.append({"field": f"{field_prefix}.provenance.source_order",
                                         "message": "source_order must preserve source ordering."})
            if _string_value(provenance.get("batch_id")) != expected_batch_id:
                provenance_errors.append({"field": f"{field_prefix}.provenance.batch_id",
                                         "message": "provenance batch_id must match the round batch_id."})
            if _string_value(provenance.get("round_id")) != expected_round_id:
                provenance_errors.append({"field": f"{field_prefix}.provenance.round_id",
                                         "message": "provenance round_id must match the round round_id."})
            if _string_value(provenance.get("source_aggregation_component_run_path")) != _string_value(dict(source_bundle.get("artifact_paths", {}) or {}).get("component_run_path", "")):
                provenance_errors.append({"field": f"{field_prefix}.provenance.source_aggregation_component_run_path",
                                         "message": "provenance must reference the source aggregation component run path."})
            if _string_value(provenance.get("source_worker_result_set_path")) != _string_value(dict(source_bundle.get("artifact_paths", {}) or {}).get("worker_result_set_path", "")):
                provenance_errors.append({"field": f"{field_prefix}.provenance.source_worker_result_set_path",
                                         "message": "provenance must reference the source worker_result_set path."})
            if _string_value(provenance.get("source_normalized_inputs_path")) != _string_value(dict(source_bundle.get("artifact_paths", {}) or {}).get("normalized_inputs_path", "")):
                provenance_errors.append({"field": f"{field_prefix}.provenance.source_normalized_inputs_path",
                                         "message": "provenance must reference the source normalized_inputs path."})

        source_lists = _source_record_lists(source_bundle)
        if not set(source_lists["merged_findings"]).issubset(set(record_lists["merged_findings"])):
            preservation_errors.append({"field": f"{field_prefix}.merged_findings",
                                       "message": "source merged_findings were not fully preserved."})
        if not set(source_lists["evidence_refs"]).issubset(set(record_lists["evidence_refs"])):
            preservation_errors.append({"field": f"{field_prefix}.evidence_refs",
                                       "message": "source evidence_refs were not fully preserved."})
        if not set(source_lists["preserved_contradictions"]).issubset(set(record_lists["preserved_contradictions"])):
            preservation_errors.append({"field": f"{field_prefix}.preserved_contradictions",
                                       "message": "source contradictions were not fully preserved."})
        if not set(source_lists["open_gaps"]).issubset(set(record_lists["open_gaps"])):
            preservation_errors.append(
                {"field": f"{field_prefix}.open_gaps", "message": "source open gaps were not fully preserved."})
        if not set(source_lists["limitations"]).issubset(set(record_lists["limitations"])):
            preservation_errors.append(
                {"field": f"{field_prefix}.limitations", "message": "source limitations were not fully preserved."})
        if source_lists["confidence_signals"] and not set(source_lists["confidence_signals"]).issubset(set(record_lists["confidence_signals"])):
            preservation_errors.append({"field": f"{field_prefix}.confidence_signals",
                                       "message": "source confidence signals were not fully preserved."})

    missing_selected_ids = [
        hypothesis_id for hypothesis_id in expected_selected_ids if hypothesis_id not in seen_hypothesis_ids]
    if missing_selected_ids:
        coverage_missing.extend(missing_selected_ids)
    if coverage_missing:
        errors.append({"field": "source_hypothesis_records",
                      "message": f"Missing source_hypothesis_records for selected hypotheses: {sorted(set(coverage_missing))}."})

    if preservation_errors:
        errors.extend(preservation_errors)
    if provenance_errors:
        errors.extend(provenance_errors)

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "selected_hypothesis_count": len(output_selected_ids),
            "source_record_count": len(source_records),
            "source_aggregation_count": len(source_aggregation_bundles),
            "preserved_finding_count": sum(len(_string_list(record.get("merged_findings"), allow_empty=False)) for record in source_records),
            "preserved_contradiction_count": sum(len(_string_list(record.get("preserved_contradictions"))) for record in source_records),
            "preserved_open_gap_count": sum(len(_string_list(record.get("open_gaps"))) for record in source_records),
            "preserved_limitation_count": sum(len(_string_list(record.get("limitations"))) for record in source_records),
            "preserved_evidence_ref_count": sum(len(_string_list(record.get("evidence_refs"), allow_empty=False)) for record in source_records),
        },
    }


def save_inter_hypothesis_artifacts(
    *,
    artifact_paths: dict[str, Path],
    component_run: dict[str, Any],
    rendered_prompt: str,
    raw_response: str,
    parsed_output: dict[str, Any],
    validation_report: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, str]:
    write_json(artifact_paths["parsed_output_path"], parsed_output)
    write_json(artifact_paths["validation_report_path"], validation_report)
    write_json(artifact_paths["runtime_metrics_path"], runtime_metrics)
    write_json(artifact_paths["replay_metadata_path"], replay_metadata)
    artifact_paths["rendered_prompt_path"].write_text(
        rendered_prompt, encoding="utf-8")
    artifact_paths["raw_response_path"].write_text(
        raw_response, encoding="utf-8")

    component_payload = dict(component_run)
    component_payload["artifact_paths"] = {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
    }
    write_json(artifact_paths["component_run_path"], component_payload)

    return {
        key: str(path)
        for key, path in artifact_paths.items()
        if key != "run_dir"
    }


def load_inter_hypothesis_bundle(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir)
    component_run = load_json(path / "component_run.json")
    artifact_paths = dict(component_run.get("artifact_paths", {}) or {})
    return {
        "component_run": component_run,
        "artifact_paths": artifact_paths,
        "rendered_prompt": Path(artifact_paths["rendered_prompt_path"]).read_text(encoding="utf-8"),
        "raw_response": Path(artifact_paths["raw_response_path"]).read_text(encoding="utf-8"),
        "parsed_output": load_json(artifact_paths["parsed_output_path"]),
        "validation_report": load_json(artifact_paths["validation_report_path"]),
        "runtime_metrics": load_json(artifact_paths["runtime_metrics_path"]),
        "replay_metadata": load_json(artifact_paths["replay_metadata_path"]),
    }


def _build_persisted_canonical_artifact(
    *,
    core_output: dict[str, Any],
    validation_report: dict[str, Any],
    component_run: dict[str, Any],
    runtime_metrics: dict[str, Any],
    replay_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "batch_id": core_output.get("batch_id", "unknown_batch"),
        "round_id": core_output.get("round_id", "unknown_round"),
        "selected_hypothesis_ids": list(core_output.get("selected_hypothesis_ids", [])),
        "source_hypothesis_records": list(core_output.get("source_hypothesis_records", [])),
        "validation_report": validation_report,
        "component_run": component_run,
        "runtime_metrics": runtime_metrics,
        "replay_metadata": replay_metadata,
    }


def run_inter_hypothesis_aggregation(
    *,
    batch_id: str,
    round_id: str,
    selected_hypothesis_ids: list[str],
    source_aggregation_bundles: list[dict[str, Any]],
    llm_callable: Callable[[str], str] | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    replay_of: str | None = None,
    caller_mode: str = "cli",
) -> dict[str, Any]:
    normalized_batch_id = _string_value(batch_id) or "unknown_batch"
    normalized_round_id = _string_value(round_id) or "unknown_round"
    normalized_selected_ids = _string_list(
        selected_hypothesis_ids, allow_empty=False)
    source_hypothesis_records = build_source_hypothesis_records(
        batch_id=normalized_batch_id,
        round_id=normalized_round_id,
        selected_hypothesis_ids=normalized_selected_ids,
        source_aggregation_bundles=source_aggregation_bundles,
    )

    prompt_text = ""
    raw_response_text = ""
    parsed_core: dict[str, Any] = {}
    parse_validation: dict[str, Any] = _report_error(
        "raw_response", "Model response was not produced.")
    core_validation: dict[str, Any] = _report_error(
        "parsed_output", "Parsed output was not produced.")

    start_time = perf_counter()
    phase_start("inter_hypothesis_aggregation",
                batch_id=normalized_batch_id, round_id=normalized_round_id)
    try:
        prompt_text = build_inter_hypothesis_prompt(
            batch_id=normalized_batch_id,
            round_id=normalized_round_id,
            selected_hypothesis_ids=normalized_selected_ids,
            source_hypothesis_records=source_hypothesis_records,
        )
        callable_to_use = llm_callable or _llm_callable_for(
            model_name, temperature)
        raw_response_text = str(callable_to_use(prompt_text) or "")
        parsed_core = parse_inter_hypothesis_response(raw_response_text)
        parse_validation = {"ok": True, "errors": [], "warnings": []}
        core_validation = validate_inter_hypothesis_artifact(
            parsed_core,
            expected_batch_id=normalized_batch_id,
            expected_round_id=normalized_round_id,
            selected_hypothesis_ids=normalized_selected_ids,
            source_aggregation_bundles=source_aggregation_bundles,
        )
    except ValueError as exc:
        parse_validation = _report_error("raw_response", str(exc))
        exception("inter_hypothesis_aggregation",
                  exc, round_id=normalized_round_id)
    except Exception as exc:  # pragma: no cover
        parse_validation = _report_error("runtime", str(exc))
        exception("inter_hypothesis_aggregation",
                  exc, round_id=normalized_round_id)

    canonical_ok = bool(parse_validation.get("ok", False)) and bool(
        core_validation.get("ok", False))
    component_run = {
        "component": "inter_hypothesis_aggregation",
        "created_at": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "status": "ok" if canonical_ok else "error",
        "validation_ok": canonical_ok,
        "authoritative_status": canonical_ok,
        "selected_hypothesis_count": len(normalized_selected_ids),
        "source_hypothesis_count": len(source_hypothesis_records),
        "model_name": model_name,
        "temperature": temperature,
        "caller_mode": caller_mode,
        "replay_of": replay_of,
    }
    runtime_metrics = {
        "batch_id": normalized_batch_id,
        "round_id": normalized_round_id,
        "selected_hypothesis_count": len(normalized_selected_ids),
        "source_hypothesis_count": len(source_hypothesis_records),
        "model_name": model_name,
        "temperature": temperature,
        "duration_ms": round((perf_counter() - start_time) * 1000.0, 3),
        "status": component_run["status"],
        "fresh_execution": replay_of is None,
        "replay_of": replay_of,
        "caller_mode": caller_mode,
        "schema_version": SCHEMA_VERSION,
        "source_aggregation_count": len(source_aggregation_bundles),
        "source_record_count": len(source_hypothesis_records),
        "preserved_finding_count": sum(len(record.get("merged_findings", [])) for record in source_hypothesis_records),
        "preserved_contradiction_count": sum(len(record.get("preserved_contradictions", [])) for record in source_hypothesis_records),
        "preserved_open_gap_count": sum(len(record.get("open_gaps", [])) for record in source_hypothesis_records),
        "preserved_limitation_count": sum(len(record.get("limitations", [])) for record in source_hypothesis_records),
        "preserved_evidence_ref_count": sum(len(record.get("evidence_refs", [])) for record in source_hypothesis_records),
    }
    replay_metadata = {
        "request_id": f"inter_hypothesis_aggregation_{datetime.now(UTC).timestamp():.0f}",
        "prompt_version": PROMPT_VERSION,
        "replay_of": replay_of,
        "fresh_execution": replay_of is None,
        "deterministic": False,
        "source_aggregation_count": len(source_aggregation_bundles),
    }
    validation_report = {
        "ok": canonical_ok,
        "schema_version": SCHEMA_VERSION,
        "parse_validation": parse_validation,
        "core_validation": core_validation,
        "selected_hypothesis_count": len(normalized_selected_ids),
        "source_record_count": len(source_hypothesis_records),
        "source_aggregation_count": len(source_aggregation_bundles),
    }
    canonical_artifact = _build_persisted_canonical_artifact(
        core_output=parsed_core or {
            "batch_id": normalized_batch_id,
            "round_id": normalized_round_id,
            "selected_hypothesis_ids": normalized_selected_ids,
            "source_hypothesis_records": source_hypothesis_records,
        },
        validation_report=validation_report,
        component_run=component_run,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    artifact_paths = build_inter_hypothesis_aggregation_artifact_paths(
        batch_id=normalized_batch_id,
        round_id=normalized_round_id,
        log_dir=log_dir,
    )
    persisted_paths = save_inter_hypothesis_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        parsed_output=canonical_artifact,
        validation_report=validation_report,
        runtime_metrics=runtime_metrics,
        replay_metadata=replay_metadata,
    )

    validation_result(
        "inter_hypothesis_aggregation",
        validation_report,
        batch_id=normalized_batch_id,
        round_id=normalized_round_id,
    )
    phase_end(
        "inter_hypothesis_aggregation",
        elapsed_s=runtime_metrics["duration_ms"] / 1000.0,
        batch_id=normalized_batch_id,
        round_id=normalized_round_id,
    )

    return {
        "component_run": component_run,
        "artifact_paths": persisted_paths,
        "rendered_prompt": prompt_text,
        "raw_response": raw_response_text,
        "parsed_output": canonical_artifact,
        "validation_report": validation_report,
        "runtime_metrics": runtime_metrics,
        "replay_metadata": replay_metadata,
        "source_hypothesis_records": source_hypothesis_records,
    }
