"""Tests for the Phase 3 Final Partition Audit Report Generator.

Phase 3a: Report generation, partition context, internal ID stripping.
Phase 3b: Dataset Merger — contracts, input resolver, parser, prompt, runner, report markdown.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from state.schema import CanonicalBatchState, InterpretiveHypothesis, StateRevisionRecord
from final_batch_report.input_resolver import (
    resolve_report_context,
    build_partition_audit_context,
    build_intended_behavioral_scenario,
    build_researcher_audit_context,
    build_finding_inventory,
    resolve_batch_reports,
    load_batch_report,
    load_coverage_data,
    _strip_internal_ids,
)
from final_batch_report.prompt_builder import (
    build_final_batch_report_prompt,
    build_merge_prompt,
    PROMPT_VERSION,
)
from final_batch_report.parser import parse_report, parse_merge_response
from final_batch_report.contracts import (
    FinalDatasetReport,
    BatchSummary,
    ArtifactPattern,
    RecurringFinding,
    PartitionSummary,
    Contradiction,
    ReportMetadata,
    CoverageSummary,
    SCHEMA_VERSION,
    MERGER_SCHEMA_VERSION,
    MERGER_PROMPT_VERSION,
)
from final_batch_report.runner import (
    generate_markdown_report,
    save_final_report,
    run_dataset_merger,
)
from final_batch_report.runtime_artifacts import (
    MergeRuntimeArtifacts,
    build_merger_artifact_paths,
    save_merger_artifacts,
    ensure_merger_runs_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_canonical_state(
    batch_id: str = "test_batch",
    hypotheses: list[InterpretiveHypothesis] | None = None,
    revision_log: list[StateRevisionRecord] | None = None,
) -> CanonicalBatchState:
    return CanonicalBatchState(
        batch_id=batch_id,
        state_version=1,
        structural_substrate={"compressed_regions": []},
        interpretive_hypotheses=hypotheses or [],
        revision_log=revision_log or [],
    )


def _make_hypothesis(
    hyp_id: str = "hyp_1",
    summary: str = "Test hypothesis summary",
    status: str = "unresolved",
    merged_findings: list[str] | None = None,
    open_gaps: list[str] | None = None,
    preserved_contradictions: list[str] | None = None,
    revision_count: int = 0,
) -> InterpretiveHypothesis:
    return InterpretiveHypothesis(
        hypothesis_id=hyp_id,
        summary=summary,
        status=status,
        merged_findings=merged_findings or [],
        open_gaps=open_gaps or [],
        preserved_contradictions=preserved_contradictions or [],
        revision_count=revision_count,
    )


def _make_valid_report_data() -> dict[str, Any]:
    """Create a valid FinalDatasetReport dict for testing."""
    return {
        "title": "Test Dataset Report",
        "dataset_overview": "Overview of test dataset.",
        "batch_summaries": [
            {
                "batch_id": "batch_1",
                "batch_label": "Monday-WorkingHours",
                "source_file": "Monday-WorkingHours.md",
                "total_findings": 5,
                "key_themes": ["Feature Redundancy", "Shortcuts"],
                "summary": "Summary for batch 1.",
            }
        ],
        "recurring_artifact_families": [
            {
                "pattern_name": "Artificial Dependency Structures",
                "description": "Structures that appear artificial.",
                "observed_in_batches": ["batch_1"],
                "severity": "high",
            }
        ],
        "recurring_findings": [
            {
                "finding_id": "finding_001",
                "description": "Recurring finding description.",
                "batch_ids": ["batch_1"],
                "finding_type": "redundancy",
                "consistency_note": "Consistent across batches.",
            }
        ],
        "coverage_interpretation": "Coverage indicates dataset-wide patterns.",
        "partition_summaries": [
            {
                "partition_id": "part_1",
                "partition_label": "Monday",
                "artifact_category_counts": {"Shortcut": 3},
                "notable_findings": ["Feature redundancy observed."],
                "summary": "Partition summary.",
            }
        ],
        "cross_partition_synthesis": "Cross-cutting analysis.",
        "contradictions": [
            {
                "contradiction_id": "contra_001",
                "batch_a": "batch_1",
                "finding_a": "Finding A",
                "batch_b": "batch_2",
                "finding_b": "Finding B",
                "description": "Contradiction between findings.",
                "resolution_status": "unresolved",
            }
        ],
        "final_recommendation": "Model With Caution",
        "metadata": {
            "report_version": "1.0",
            "generated_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            "batch_sources": ["Monday-WorkingHours.md"],
            "merger_version": "phase3.dataset_merger.v1",
        },
    }


# ===========================================================================
# Phase 3a Tests
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 1 — Report Generation
# ---------------------------------------------------------------------------

def test_report_generation_succeeds():
    """A report can be built using the prompt builder and parser with sample data."""
    hypothesis = _make_hypothesis(
        hyp_id="hyp_1",
        summary="Strong redundant feature clusters detected via e1 and e2.",
        status="unresolved",
        merged_findings=["Multiple feature pairs show correlation > 0.95"],
        open_gaps=["Unclear if class-conditioned or global"],
        preserved_contradictions=[],
        revision_count=3,
    )
    state = _make_canonical_state(
        batch_id="test_batch",
        hypotheses=[hypothesis],
        revision_log=[
            StateRevisionRecord(
                revision_type="state_update",
                state_version=1,
                round_id="round_1",
                hypothesis_id="hyp_1",
                applied_updates=[{"description": "Updated finding after investigation"}],
            )
        ],
    )

    report_context = resolve_report_context(state, "ddos")
    assert report_context is not None
    assert "investigated_findings" in report_context
    assert "additional_findings" in report_context

    prompt = build_final_batch_report_prompt(
        partition_name="ddos",
        partition_audit_context=report_context["partition_audit_context"],
        intended_behavioral_scenario=report_context["intended_behavioral_scenario"],
        researcher_audit_context=report_context["researcher_audit_context"],
        investigated_findings=report_context["investigated_findings"],
        additional_findings=report_context["additional_findings"],
    )
    assert prompt is not None
    assert len(prompt) > 100

    # Simulate an LLM response
    fake_response = "# Final Partition Audit Report\n\nTest content."
    parsed = parse_report(fake_response)
    assert parsed["report_markdown"] == fake_response


# ---------------------------------------------------------------------------
# Test 2 — Partition Context Present
# ---------------------------------------------------------------------------

def test_partition_context_present():
    """Prompt includes partition context (semantics, expected properties, etc.)."""
    hypothesis = _make_hypothesis(
        hyp_id="hyp_1",
        summary="Test",
        merged_findings=["Finding 1"],
        revision_count=2,
    )
    state = _make_canonical_state(
        batch_id="test_batch",
        hypotheses=[hypothesis],
    )

    report_context = resolve_report_context(state, "ddos")
    prompt = build_final_batch_report_prompt(
        partition_name="ddos",
        partition_audit_context=report_context["partition_audit_context"],
        intended_behavioral_scenario=report_context["intended_behavioral_scenario"],
        researcher_audit_context=report_context["researcher_audit_context"],
        investigated_findings=report_context["investigated_findings"],
        additional_findings=report_context["additional_findings"],
    )

    # Partition context section must be present
    assert "PARTITION AUDIT CONTEXT" in prompt
    assert "Partition Name: ddos" in prompt
    assert "INTENDED BEHAVIORAL SCENARIO" in prompt

    # Must include the researcher audit context
    assert "RESEARCHER AUDIT CONTEXT" in prompt

    # Critical rubric must appear
    assert "Independence of Impact and Confidence" in prompt


# ---------------------------------------------------------------------------
# Test 3 — No Internal IDs
# ---------------------------------------------------------------------------

def test_no_internal_ids_in_prompt():
    """No e1, e12, hyp_5, region_8 appear in the prompt or findings."""
    hypothesis = _make_hypothesis(
        hyp_id="hyp_5",  # internal ID that should be stripped
        summary="Strong redundant feature clusters detected via e1 and region_8 analysis.",
        merged_findings=[
            "Finding e12: high correlation between features",
            "Evidence e33 supports this conclusion",
        ],
        open_gaps=["region_8 needs more investigation"],
        revision_count=2,
    )
    state = _make_canonical_state(
        batch_id="test_batch",
        hypotheses=[hypothesis],
    )

    report_context = resolve_report_context(state, "ddos")

    # Check investigated findings - should have no internal IDs
    for finding in report_context["investigated_findings"]:
        summary = finding.get("summary", "")
        assert "e1" not in summary, f"Found e1 in: {summary}"
        assert "e12" not in summary, f"Found e12 in: {summary}"
        assert "hyp_5" not in summary, f"Found hyp_5 in: {summary}"
        assert "region_8" not in summary, f"Found region_8 in: {summary}"

        for mf in finding.get("merged_findings", []):
            assert "e1" not in mf, f"Found e1 in merged_finding: {mf}"
            assert "e12" not in mf, f"Found e12 in merged_finding: {mf}"
            assert "e33" not in mf, f"Found e33 in merged_finding: {mf}"

        for gap in finding.get("open_gaps", []):
            assert "region_8" not in gap, f"Found region_8 in open_gap: {gap}"

    # Build prompt and verify it too
    prompt = build_final_batch_report_prompt(
        partition_name="ddos",
        partition_audit_context=report_context["partition_audit_context"],
        intended_behavioral_scenario=report_context["intended_behavioral_scenario"],
        researcher_audit_context=report_context["researcher_audit_context"],
        investigated_findings=report_context["investigated_findings"],
        additional_findings=report_context["additional_findings"],
    )

    assert "e1" not in prompt
    assert "e12" not in prompt
    assert "e33" not in prompt
    assert "hyp_5" not in prompt
    assert "region_8" not in prompt


# ---------------------------------------------------------------------------
# Additional unit tests for input_resolver
# ---------------------------------------------------------------------------

def test_strip_internal_ids():
    """Internal ID stripping regex works correctly."""
    assert _strip_internal_ids("Evidence e33 suggests") == "Evidence [reference] suggests"
    assert _strip_internal_ids("hyp_5 is active") == "[reference] is active"
    assert _strip_internal_ids("region_8 analysis") == "[reference] analysis"
    assert _strip_internal_ids("task_1_step_03 output") == "[reference] output"
    assert _strip_internal_ids("Normal text") == "Normal text"


def test_finding_inventory_classifies_correctly():
    """Findings with revision_count > 0 or merged_findings are investigated."""
    h_investigated = _make_hypothesis(
        hyp_id="hyp_inv",
        summary="Investigated finding",
        merged_findings=["Finding A"],
        revision_count=2,
    )
    h_additional = _make_hypothesis(
        hyp_id="hyp_add",
        summary="Additional finding",
        merged_findings=[],
        revision_count=0,
    )
    state = _make_canonical_state(
        batch_id="test_batch",
        hypotheses=[h_investigated, h_additional],
    )

    inventory = build_finding_inventory(state)
    assert len(inventory["investigated_findings"]) == 1
    assert len(inventory["additional_findings"]) == 1
    assert inventory["investigated_findings"][0]["summary"] == "Investigated finding"
    assert inventory["additional_findings"][0]["summary"] == "Additional finding"


def test_researcher_audit_context():
    """Researcher audit context reports correct counts."""
    h1 = _make_hypothesis(hyp_id="h1", merged_findings=["f1"], revision_count=1)
    h2 = _make_hypothesis(hyp_id="h2", merged_findings=[], revision_count=0)
    h3 = _make_hypothesis(hyp_id="h3", merged_findings=["f2"], revision_count=0)
    state = _make_canonical_state(
        batch_id="test_batch",
        hypotheses=[h1, h2, h3],
        revision_log=[
            StateRevisionRecord(
                revision_type="state_update",
                state_version=1,
                round_id="round_1",
                hypothesis_id="h1",
            )
        ],
    )

    ctx = build_researcher_audit_context(state)
    assert ctx["total_hypotheses"] == 3
    # h1 has revision_count > 0, h3 has merged_findings non-empty
    assert ctx["investigated_hypotheses"] == 2
    assert ctx["less_explored_hypotheses"] == 1
    assert ctx["revision_rounds"] == 1


def test_intended_behavioral_scenario_ddos():
    """DDoS partitions get appropriate scenario."""
    scenario = build_intended_behavioral_scenario("ddos")
    assert "DDoS" in scenario
    assert "concentration patterns" in scenario


def test_intended_behavioral_scenario_unknown():
    """Unknown partitions get generic fallback."""
    scenario = build_intended_behavioral_scenario("nonexistent_partition")
    assert len(scenario) > 50
    assert "network traffic" in scenario.lower()


# ===========================================================================
# Phase 3b Tests — Dataset Merger
# ===========================================================================

# ---------------------------------------------------------------------------
# Test — Contracts Validation
# ---------------------------------------------------------------------------

def test_contracts_validation():
    """Pydantic models accept valid data, reject invalid."""
    # Valid data should work
    data = _make_valid_report_data()
    report = FinalDatasetReport(**data)
    assert report.title == "Test Dataset Report"
    assert len(report.batch_summaries) == 1
    assert len(report.contradictions) == 1

    # Missing required field should raise ValidationError
    with pytest.raises(ValidationError):
        FinalDatasetReport(**{})  # type: ignore[arg-type]

    # Wrong type should raise ValidationError
    with pytest.raises(ValidationError):
        FinalDatasetReport(**{**data, "title": 123})  # type: ignore[arg-type]

    # Empty lists are valid (no findings, no contradictions)
    no_data = dict(data)
    no_data["batch_summaries"] = []
    no_data["recurring_artifact_families"] = []
    no_data["recurring_findings"] = []
    no_data["partition_summaries"] = []
    no_data["contradictions"] = []
    report_empty = FinalDatasetReport(**no_data)
    assert report_empty.batch_summaries == []

    # Default values work
    meta = ReportMetadata(
        report_version="1.0",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        batch_sources=["test.md"],
        merger_version="v1",
    )
    assert meta.report_version == "1.0"

    # CoverageSummary defaults
    cs = CoverageSummary()
    assert cs.total_packets == 0
    assert cs.coverage_percentage == 0.0
    assert cs.uncovered_categories == []

    # Contradiction default resolution_status
    contra = Contradiction(
        contradiction_id="c1",
        batch_a="a", finding_a="fa",
        batch_b="b", finding_b="fb",
        description="desc",
    )
    assert contra.resolution_status == "unresolved"


# ---------------------------------------------------------------------------
# Test — Input Resolver: Finds Reports
# ---------------------------------------------------------------------------

def test_input_resolver_finds_reports():
    """Resolves .md files from batch_reports dir."""
    files = resolve_batch_reports("docs/batch_reports")
    assert len(files) >= 1
    assert all(f.endswith(".md") for f in files)
    # Should return absolute paths
    assert all(Path(f).is_absolute() for f in files)


def test_input_resolver_empty_dir():
    """Handles non-existent directory."""
    files = resolve_batch_reports("nonexistent_directory_xyz")
    assert files == []


def test_input_resolver_loads_content():
    """Loads file content correctly."""
    files = resolve_batch_reports("docs/batch_reports")
    assert len(files) >= 1
    content = load_batch_report(files[0])
    assert isinstance(content, str)
    assert len(content) > 0


# ---------------------------------------------------------------------------
# Test — Parser
# ---------------------------------------------------------------------------

def test_parser_extracts_json():
    """Parses JSON from LLM response (with fences)."""
    data = _make_valid_report_data()
    import json
    json_str = json.dumps(data, default=str)

    # With fences
    response = f"```json\n{json_str}\n```"
    report = parse_merge_response(response)
    assert isinstance(report, FinalDatasetReport)
    assert report.title == "Test Dataset Report"

    # Without fences
    report2 = parse_merge_response(json_str)
    assert report2.title == "Test Dataset Report"


def test_parser_rejects_invalid_json():
    """Raises on malformed JSON."""
    with pytest.raises(ValueError):
        parse_merge_response("not json at all")

    with pytest.raises(ValueError):
        parse_merge_response("```json\n{invalid json}\n```")


def test_parser_validates_schema():
    """Pydantic validation catches missing fields."""
    response = '{"title": "missing fields"}'
    with pytest.raises(ValidationError):
        parse_merge_response(response)


# ---------------------------------------------------------------------------
# Test — Prompt Builder
# ---------------------------------------------------------------------------

def test_prompt_includes_all_reports():
    """Prompt contains all batch report content."""
    batch_reports = [
        ("report1.md", "# Report 1 content"),
        ("report2.md", "# Report 2 content"),
    ]
    prompt = build_merge_prompt(batch_reports, {})
    assert "BEGIN BATCH REPORT: report1.md" in prompt
    assert "BEGIN BATCH REPORT: report2.md" in prompt
    assert "Report 1 content" in prompt
    assert "Report 2 content" in prompt


def test_prompt_includes_coverage():
    """Prompt includes coverage data."""
    coverage = {"artifact_family_coverage": [{"family": "Shortcut", "coverage": "5/7"}]}
    prompt = build_merge_prompt([("test.md", "content")], coverage)
    assert "COVERAGE DATA" in prompt
    assert "Shortcut" in prompt
    assert "5/7" in prompt


def test_prompt_contradiction_instruction():
    """Prompt explicitly mentions preserving contradictions."""
    prompt = build_merge_prompt([("test.md", "content")], {})
    assert "CONTRADICTION PRESERVATION" in prompt
    assert "Do NOT collapse" in prompt


def test_prompt_handles_empty_coverage():
    """Prompt handles missing coverage data gracefully."""
    prompt = build_merge_prompt([("test.md", "content")], {})
    assert "COVERAGE DATA:" in prompt
    assert "None provided" in prompt


# ---------------------------------------------------------------------------
# Test — Report Markdown
# ---------------------------------------------------------------------------

def test_report_markdown_has_all_sections():
    """Generated markdown has all required sections."""
    data = _make_valid_report_data()
    report = FinalDatasetReport(**data)
    md = generate_markdown_report(report)

    sections = [
        "# Test Dataset Report",
        "## Dataset Overview",
        "## Batch Summaries",
        "## Recurring Artifact Families",
        "## Recurring Findings",
        "## Coverage Interpretation",
        "## Partition Summaries",
        "## Cross-Partition Synthesis",
        "## Contradictions",
        "## Final Recommendation",
        "## Metadata",
    ]
    for section in sections:
        assert section in md, f"Missing section: {section}"


# ---------------------------------------------------------------------------
# Test — Save Report
# ---------------------------------------------------------------------------

def test_save_report_creates_files(tmp_path: Path):
    """JSON and Markdown files are created."""
    data = _make_valid_report_data()
    report = FinalDatasetReport(**data)
    output_dir = str(tmp_path / "dataset_report")

    saved_path = save_final_report(report, output_dir)

    json_file = Path(saved_path) / "final_dataset_report.json"
    md_file = Path(saved_path) / "final_dataset_report.md"

    assert json_file.exists()
    assert md_file.exists()

    # Verify JSON content
    import json
    loaded = json.loads(json_file.read_text(encoding="utf-8"))
    assert loaded["title"] == "Test Dataset Report"

    # Verify Markdown content
    md_content = md_file.read_text(encoding="utf-8")
    assert "# Test Dataset Report" in md_content


# ---------------------------------------------------------------------------
# Test — Runner
# ---------------------------------------------------------------------------

def test_runner_resolve_and_load():
    """Runner resolves and loads batch reports."""
    def mock_llm(prompt: str) -> str:
        import json
        return json.dumps(_make_valid_report_data(), default=str)

    artifacts = run_dataset_merger(
        batch_reports_dir="docs/batch_reports",
        output_dir=str(Path.cwd() / "final_dataset"),
        llm_callable=mock_llm,
    )

    assert isinstance(artifacts, MergeRuntimeArtifacts)
    assert len(artifacts.input_batch_files) >= 1
    assert len(artifacts.prompt) > 0
    assert artifacts.parsed_report is not None
    assert isinstance(artifacts.parsed_report, FinalDatasetReport)
    assert artifacts.success is True


def test_runner_handles_missing_llm():
    """Runner handles missing LLM callable gracefully."""
    artifacts = run_dataset_merger(
        batch_reports_dir="docs/batch_reports",
        llm_callable=None,
    )
    assert artifacts.success is False
    assert artifacts.error_message is not None
    assert "No LLM callable" in artifacts.error_message


def test_end_to_end_merge():
    """Full merge with mock LLM produces valid report with all sections."""
    def mock_llm(prompt: str) -> str:
        import json
        return json.dumps(_make_valid_report_data(), default=str)

    artifacts = run_dataset_merger(
        batch_reports_dir="docs/batch_reports",
        llm_callable=mock_llm,
    )

    assert artifacts.success is True
    assert artifacts.parsed_report is not None
    report = artifacts.parsed_report

    # Verify all top-level fields
    assert report.title
    assert report.dataset_overview
    assert isinstance(report.batch_summaries, list)
    assert isinstance(report.recurring_artifact_families, list)
    assert isinstance(report.recurring_findings, list)
    assert report.coverage_interpretation
    assert isinstance(report.partition_summaries, list)
    assert report.cross_partition_synthesis
    assert isinstance(report.contradictions, list)
    assert report.final_recommendation
    assert report.metadata is not None
    assert report.metadata.report_version
    assert report.metadata.generated_at
    assert report.metadata.batch_sources
    assert report.metadata.merger_version


# ---------------------------------------------------------------------------
# Test — MergeRuntimeArtifacts
# ---------------------------------------------------------------------------

def test_merge_runtime_artifacts_defaults():
    """MergeRuntimeArtifacts has correct default values."""
    now = datetime.now(timezone.utc)
    artifacts = MergeRuntimeArtifacts(
        run_id="test_001",
        timestamp=now,
        input_batch_files=["file1.md"],
        coverage_data_used={},
        prompt="prompt text",
        raw_response="response text",
    )
    assert artifacts.run_id == "test_001"
    assert artifacts.timestamp == now
    assert artifacts.validation_errors == []
    assert artifacts.parsed_report is None
    assert artifacts.output_path is None
    assert artifacts.success is False
    assert artifacts.error_message is None


# ---------------------------------------------------------------------------
# Test — Merger Artifact Persistence
# ---------------------------------------------------------------------------

def test_merger_artifact_paths_and_save(tmp_path: Path):
    """Merger artifact paths are created and save produces files."""
    # Build paths
    log_dir = str(tmp_path / "merger_logs")
    paths = build_merger_artifact_paths(log_dir=log_dir)

    # Verify paths exist
    for key, path in paths.items():
        if key != "run_dir":
            assert path.parent.exists()

    # Save artifacts
    now = datetime.now(timezone.utc)
    saved = save_merger_artifacts(
        artifact_paths=paths,
        component_run={"component": "dataset_merger", "created_at": now.isoformat()},
        report_json={"title": "Test Report"},
        report_markdown="# Test Report",
        rendered_prompt="prompt text",
        raw_response="response text",
        runtime_metrics={"status": "ok"},
    )

    # Verify all paths returned
    assert "report_json_path" in saved
    assert "report_md_path" in saved
    assert "prompt_path" in saved
    assert "raw_response_path" in saved
    assert "runtime_metrics_path" in saved

    # Verify files written
    assert Path(saved["report_json_path"]).exists()
    assert Path(saved["report_md_path"]).exists()
    assert Path(saved["prompt_path"]).exists()
    assert Path(saved["raw_response_path"]).exists()
    assert Path(saved["runtime_metrics_path"]).exists()


def test_ensure_merger_runs_dir(tmp_path: Path):
    """Merger runs directory is created."""
    log_dir = str(tmp_path / "new_merger_logs")
    created = ensure_merger_runs_dir(log_dir)
    assert Path(created).exists()
    assert Path(created).is_dir()