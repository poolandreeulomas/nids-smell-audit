"""Execution wrapper for the Phase 3 Final Partition Audit Report Generator.

Phase 3a: Per-partition final batch report generation (existing).
Phase 3b: Dataset Merger execution (run_dataset_merger).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from state.schema import CanonicalBatchState

from final_batch_report.contracts import (
    FinalDatasetReport,
    MERGER_SCHEMA_VERSION,
    SCHEMA_VERSION,
)
from data.dataset_config import DatasetConfig
from final_batch_report.input_resolver import (
    resolve_batch_reports,
    load_batch_report,
    load_coverage_data,
    resolve_report_context,
)
from final_batch_report.parser import parse_report, parse_merge_response
from final_batch_report.prompt_builder import (
    MERGER_PROMPT_VERSION,
    PROMPT_VERSION,
    build_final_batch_report_prompt,
    build_merge_prompt,
)
from final_batch_report.runtime_artifacts import (
    MergeRuntimeArtifacts,
    build_final_batch_report_artifact_paths,
    build_merger_artifact_paths,
    save_final_batch_report_artifacts,
    save_merger_artifacts,
)
from utils.openai_response import build_responses_create_kwargs, extract_response_text
from instrumentation import phase_start, phase_end


# ── Phase 3a — Per-partition final batch report runner ─────────────────────

FinalBatchReportCallable = Callable[[str], str]


def _build_openai_final_batch_report_callable(
    model_name: str,
    temperature: float = 0.0,
) -> FinalBatchReportCallable:
    def _call_llm(prompt_text: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI package is not installed. Install 'openai' to run final_batch_report."
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


def run_final_batch_report(
    final_state: CanonicalBatchState,
    partition_name: str,
    *,
    llm_callable: FinalBatchReportCallable | None = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    log_dir: str | None = None,
    dataset_config: DatasetConfig | None = None,
) -> dict[str, Any]:
    """Generate a Final Partition Audit Report from the Final Updated State.

    Flow:
        Load Final Updated State
            ↓
        Resolve Report Context
            ↓
        Build Prompt
            ↓
        Call LLM
            ↓
        Capture Markdown
            ↓
        Persist Artifacts
            ↓
        Return Results

    Args:
        final_state: CanonicalBatchState (the Final Updated State).
        partition_name: Human-readable partition name.
        llm_callable: Optional custom LLM callable.
        model_name: OpenAI model name (default: gpt-4.1-mini).
        temperature: LLM temperature (default: 0.0).
        log_dir: Optional log directory override.

    Returns:
        Dict with report_markdown, runtime_metrics, artifact_paths.
    """
    request_id = f"final_batch_report_{uuid4().hex}"
    batch_id = final_state.batch_id or "unknown_batch"
    state_version = final_state.state_version

    # Step 1: Resolve Report Context
    report_context = resolve_report_context(final_state, partition_name, dataset_config=dataset_config)

    partition_audit_context = report_context["partition_audit_context"]
    intended_behavioral_scenario = report_context["intended_behavioral_scenario"]
    researcher_audit_context = report_context["researcher_audit_context"]
    investigated_findings = report_context["investigated_findings"]
    additional_findings = report_context["additional_findings"]

    # Step 2: Build Prompt
    prompt_text = build_final_batch_report_prompt(
        partition_name=partition_name,
        partition_audit_context=partition_audit_context,
        intended_behavioral_scenario=intended_behavioral_scenario,
        researcher_audit_context=researcher_audit_context,
        investigated_findings=investigated_findings,
        additional_findings=additional_findings,
    )

    report_markdown = ""
    raw_response_text = ""

    start_time = perf_counter()
    phase_start(
        "final_batch_report",
        batch_id=batch_id,
        state_version=state_version,
    )

    try:
        callable_to_use = llm_callable or _build_openai_final_batch_report_callable(
            model_name,
            temperature,
        )
        raw_response_text = str(callable_to_use(prompt_text) or "")
        parsed = parse_report(raw_response_text)
        report_markdown = parsed["report_markdown"]
    except Exception as exc:
        raw_response_text = f"Error: {exc}"
        report_markdown = f"Report generation failed: {exc}"

    duration_ms = round((perf_counter() - start_time) * 1000.0, 3)
    status = "ok" if report_markdown else "error"

    phase_end(
        "final_batch_report",
        elapsed_s=duration_ms / 1000.0,
        batch_id=batch_id,
        state_version=state_version,
    )

    # Step 3: Build runtime metrics
    runtime_metrics = {
        "request_id": request_id,
        "batch_id": batch_id,
        "state_version": state_version,
        "prompt_version": PROMPT_VERSION,
        "model_name": model_name,
        "temperature": temperature,
        "duration_ms": duration_ms,
        "status": status,
        "investigated_findings_count": len(investigated_findings),
        "additional_findings_count": len(additional_findings),
        "report_length_chars": len(report_markdown),
        "schema_version": SCHEMA_VERSION,
    }

    # Step 4: Build component run metadata
    component_run = {
        "component": "final_batch_report",
        "created_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "state_version": state_version,
        "status": status,
        "model_name": model_name,
        "temperature": temperature,
        "investigated_findings_count": len(investigated_findings),
        "additional_findings_count": len(additional_findings),
    }

    # Step 5: Persist artifacts
    artifact_paths = build_final_batch_report_artifact_paths(
        batch_id=batch_id,
        log_dir=log_dir,
    )
    persisted_paths = save_final_batch_report_artifacts(
        artifact_paths=artifact_paths,
        component_run=component_run,
        report_markdown=report_markdown,
        rendered_prompt=prompt_text,
        raw_response=raw_response_text,
        runtime_metrics=runtime_metrics,
    )

    return {
        "report_markdown": report_markdown,
        "runtime_metrics": runtime_metrics,
        "artifact_paths": persisted_paths,
    }


# ── Phase 3b — Dataset Merger runner ───────────────────────────────────────

MergerCallable = Callable[[str], str]


def generate_markdown_report(report: FinalDatasetReport) -> str:
    """Generate a human-readable Markdown version of the final dataset report.

    The Markdown includes ALL sections defined in the concept plan.
    """
    lines: list[str] = []

    # Title
    lines.append(f"# {report.title}")
    lines.append("")

    # Dataset Overview
    lines.append("## Dataset Overview")
    lines.append(report.dataset_overview)
    lines.append("")

    # Batch Summaries
    lines.append("## Batch Summaries")
    for bs in report.batch_summaries:
        lines.append(f"### {bs.batch_label}")
        lines.append(f"- **Batch ID:** {bs.batch_id}")
        lines.append(f"- **Source File:** {bs.source_file}")
        lines.append(f"- **Total Findings:** {bs.total_findings}")
        if bs.key_themes:
            lines.append(f"- **Key Themes:** {', '.join(bs.key_themes)}")
        lines.append(bs.summary)
        lines.append("")

    # Recurring Artifact Families
    lines.append("## Recurring Artifact Families")
    if report.recurring_artifact_families:
        for af in report.recurring_artifact_families:
            lines.append(f"### {af.pattern_name}")
            lines.append(af.description)
            lines.append(f"- **Observed in batches:** {', '.join(af.observed_in_batches)}")
            if af.severity:
                lines.append(f"- **Severity:** {af.severity}")
            lines.append("")
    else:
        lines.append("No recurring artifact families identified.")
        lines.append("")

    # Recurring Findings
    lines.append("## Recurring Findings")
    if report.recurring_findings:
        for rf in report.recurring_findings:
            lines.append(f"### {rf.finding_id}")
            lines.append(rf.description)
            lines.append(f"- **Type:** {rf.finding_type}")
            lines.append(f"- **Observed in batches:** {', '.join(rf.batch_ids)}")
            if rf.consistency_note:
                lines.append(f"- **Consistency:** {rf.consistency_note}")
            lines.append("")
    else:
        lines.append("No recurring findings identified.")
        lines.append("")

    # Coverage Interpretation
    lines.append("## Coverage Interpretation")
    lines.append(report.coverage_interpretation)
    lines.append("")

    # Partition Summaries
    lines.append("## Partition Summaries")
    for ps in report.partition_summaries:
        lines.append(f"### {ps.partition_label}")
        lines.append(f"- **Partition ID:** {ps.partition_id}")
        if ps.artifact_category_counts:
            lines.append(f"- **Artifact Categories:**")
            for category, count in ps.artifact_category_counts.items():
                lines.append(f"  - {category}: {count}")
        if ps.notable_findings:
            lines.append(f"- **Notable Findings:**")
            for nf in ps.notable_findings:
                lines.append(f"  - {nf}")
        lines.append(ps.summary)
        lines.append("")

    # Cross-Partition Synthesis
    lines.append("## Cross-Partition Synthesis")
    lines.append(report.cross_partition_synthesis)
    lines.append("")

    # Contradictions
    lines.append("## Contradictions")
    if report.contradictions:
        for c in report.contradictions:
            lines.append(f"### {c.contradiction_id}")
            lines.append(c.description)
            lines.append(f"- **Between:** {c.batch_a} and {c.batch_b}")
            lines.append(f"  - Finding A: {c.finding_a}")
            lines.append(f"  - Finding B: {c.finding_b}")
            lines.append(f"- **Resolution Status:** {c.resolution_status}")
            lines.append("")
    else:
        lines.append("No contradictions identified.")
        lines.append("")

    # Final Recommendation
    lines.append("## Final Recommendation")
    lines.append(report.final_recommendation)
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append(f"- **Report Version:** {report.metadata.report_version}")
    lines.append(f"- **Generated At:** {report.metadata.generated_at.isoformat()}")
    lines.append(f"- **Merger Version:** {report.metadata.merger_version}")
    if report.metadata.batch_sources:
        lines.append(f"- **Batch Sources:**")
        for src in report.metadata.batch_sources:
            lines.append(f"  - {src}")

    return "\n".join(lines).strip()


def save_final_report(
    report: FinalDatasetReport,
    output_dir: str,
) -> str:
    """Save the final dataset report to disk.

    Produces:
        {output_dir}/final_dataset_report.json  — structured data
        {output_dir}/final_dataset_report.md    — human-readable markdown

    Args:
        report: FinalDatasetReport instance.
        output_dir: Directory to save the report files.

    Returns:
        Path to the output directory.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = output_path / "final_dataset_report.json"
    json_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # Save Markdown
    md_path = output_path / "final_dataset_report.md"
    md_content = generate_markdown_report(report)
    md_path.write_text(md_content, encoding="utf-8")

    return str(output_path.resolve())


def run_dataset_merger(
    batch_reports_dir: str = "docs/batch_reports",
    coverage_file: str = "",
    output_dir: str = "final_dataset",
    llm_callable: Callable[[str], str] | None = None,
) -> MergeRuntimeArtifacts:
    """Execute the full dataset merge process.

    Steps:
    1. Resolve batch report files.
    2. Load all batch report contents.
    3. Load coverage data.
    4. Build merge prompt.
    5. Call LLM (or raise if no callable provided).
    6. Parse response into FinalDatasetReport.
    7. Validate schema.
    8. Save report (JSON + Markdown).
    9. Return runtime artifacts.

    Args:
        batch_reports_dir: Directory containing .md batch report files.
        coverage_file: Path to coverage JSON file. If empty, uses default path.
        output_dir: Directory to save the final report.
        llm_callable: Function that takes prompt str and returns response str.
            If None, raises ValueError.

    Returns:
        MergeRuntimeArtifacts with full execution trace.
    """
    run_id = f"dataset_merger_{uuid4().hex}"
    timestamp = datetime.now(UTC)

    artifacts = MergeRuntimeArtifacts(
        run_id=run_id,
        timestamp=timestamp,
        input_batch_files=[],
        coverage_data_used={},
        prompt="",
        raw_response="",
    )

    try:
        # Step 1: Resolve batch report files
        batch_files = resolve_batch_reports(batch_reports_dir)
        artifacts.input_batch_files = list(batch_files)

        if not batch_files:
            artifacts.error_message = f"No batch report files found in {batch_reports_dir}"
            artifacts.success = False
            return artifacts

        # Step 2: Load all batch report contents
        batch_reports: list[tuple[str, str]] = []
        for file_path in batch_files:
            content = load_batch_report(file_path)
            filename = Path(file_path).name
            batch_reports.append((filename, content))

        # Step 3: Load coverage data
        cov_file = coverage_file or str(
            Path(__file__).resolve().parent.parent
            / "coverage_builder"
            / "coverage_output"
            / "coverage.json"
        )
        coverage_data = load_coverage_data(cov_file)
        artifacts.coverage_data_used = dict(coverage_data)

        # Step 4: Build merge prompt
        prompt_text = build_merge_prompt(batch_reports, coverage_data)
        artifacts.prompt = prompt_text

        # Step 5: Call LLM
        if llm_callable is None:
            artifacts.error_message = (
                "No LLM callable provided. "
                "Dataset merger requires an LLM callable to function."
            )
            artifacts.success = False
            return artifacts

        raw_response = str(llm_callable(prompt_text) or "")
        artifacts.raw_response = raw_response

        # Step 6: Parse response into FinalDatasetReport
        parsed_report = parse_merge_response(raw_response)
        artifacts.parsed_report = parsed_report

        # Step 7: Save report
        output_path = save_final_report(parsed_report, output_dir)
        artifacts.output_path = output_path

        # Also persist to run directory
        run_artifact_paths = build_merger_artifact_paths()
        component_run = {
            "component": "dataset_merger",
            "created_at": timestamp.isoformat(),
            "request_id": run_id,
            "prompt_version": MERGER_PROMPT_VERSION,
            "schema_version": MERGER_SCHEMA_VERSION,
            "status": "ok",
        }
        runtime_metrics = {
            "run_id": run_id,
            "timestamp": timestamp.isoformat(),
            "batch_report_count": len(batch_files),
            "coverage_available": bool(coverage_data),
            "status": "ok",
            "merger_schema_version": MERGER_SCHEMA_VERSION,
            "merger_prompt_version": MERGER_PROMPT_VERSION,
        }
        save_merger_artifacts(
            artifact_paths=run_artifact_paths,
            component_run=component_run,
            report_json=parsed_report.model_dump(mode="json"),
            report_markdown=generate_markdown_report(parsed_report),
            rendered_prompt=prompt_text,
            raw_response=raw_response,
            runtime_metrics=runtime_metrics,
        )

        artifacts.success = True

    except Exception as exc:
        artifacts.success = False
        artifacts.error_message = f"Dataset merger failed: {exc}"

    return artifacts