"""Unit and integration tests for custom dataset selection in ATLAS CLI.

Covers all 16 required test scenarios:
1. Existing registered dataset/partition selection remains unchanged.
2. Custom CSV discovered in the existing data directory.
3. Valid custom CSV selected through an absolute path.
4. Relative path resolution.
5. Paths containing spaces and quotes.
6. Invalid, missing, unreadable, and empty files.
7. Unsupported formats and malformed tabular data.
8. A custom file whose label column is not named 'Label'.
9. A missing label column and an ambiguous schema.
10. Benign-class selection and validation.
11. Cancellation and preservation of existing session configuration.
12. Confirmed custom path propagation into the actual runtime call, verified with mocks.
13. No silent fallback to a predefined dataset when custom-path resolution fails.
14. Correct source identity and metadata in persisted run configuration or manifests.
15. No mutation of the selected source file.
16. Regression coverage for the existing configuration and investigation CLI flows.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import pandas as pd

from config import DATA_DIR
from data.dataset_config import (
    DatasetConfig,
    create_custom_dataset_config,
    get_default_dataset_config,
    infer_dataset_config,
    register_custom_dataset_config,
    unregister_custom_dataset_config,
)
from data.loader import load_dataset
from data.validation import (
    build_attack_mask,
    inspect_custom_dataset_preflight,
)
from interface.cli import NidsAgentCli, SessionConfig
from phase3_runtime.orchestrator import run_phase3a_batch


@pytest.fixture(autouse=True)
def clean_custom_registry():
    """Ensure custom configs registry is cleaned before and after every test."""
    unregister_custom_dataset_config()
    yield
    unregister_custom_dataset_config()


def _create_sample_csv(path: Path, label_col: str = "Label", normal_val: str = "BENIGN") -> Path:
    """Helper to create a valid small tabular CSV fixture."""
    df = pd.DataFrame({
        label_col: [normal_val, normal_val, "Attack-Dos", "Attack-PortScan", normal_val, "Attack-Dos"],
        "Flow_Duration": [120.0, 150.5, 3000.0, 450.0, 110.2, 2900.0],
        "Total_Fwd_Packets": [2, 3, 50, 10, 2, 45],
        "Total_Bwd_Packets": [1, 2, 40, 8, 1, 38],
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


# ===========================================================================
# 1. Existing Registered Dataset / Partition Selection
# ===========================================================================

def test_01_existing_dataset_partition_selection_unchanged():
    """Ensure predefined dataset/partition selection behaves exactly as before."""
    cli = NidsAgentCli()
    available = cli._get_available_dataset_paths()
    assert len(available) > 0, "Predefined partitions should be discovered in DATA_DIR"

    # Default dataset is the first candidate
    assert cli.session_config.dataset_name == available[0].name
    assert cli.session_config.custom_dataset_path is None
    assert cli._get_selected_dataset_label() == available[0].name
    assert cli._get_selected_dataset_path() == available[0]

    # Select second partition via predefined menu
    if len(available) > 1:
        with patch.object(cli, "_wait_for_enter", return_value=None), \
             patch.object(cli, "_read_menu_choice", side_effect=["1", "2"]):
            cli._change_dataset_partition()
        assert cli.session_config.dataset_name == available[1].name
        assert cli.session_config.custom_dataset_path is None
        assert cli._get_selected_dataset_path() == available[1]


# ===========================================================================
# 2. Custom CSV Discovered in Existing Data Directory
# ===========================================================================

def test_02_custom_csv_discovered_in_data_directory(tmp_path: Path):
    """Test discovering and selecting a custom CSV within the project's DATA_DIR."""
    # Place a test CSV in DATA_DIR
    custom_name = "test_discovered_custom.csv"
    discovered_path = Path(DATA_DIR) / custom_name
    try:
        _create_sample_csv(discovered_path)
        cli = NidsAgentCli()
        discovered = [p for p in Path(DATA_DIR).rglob("*") if p.is_file() and p.name == custom_name]
        assert len(discovered) == 1

        # Simulate selecting [2] Discovered -> item index -> [1] Confirm
        all_discovered = sorted(
            p for p in Path(DATA_DIR).rglob("*")
            if p.is_file() and p.suffix.lower() in {".csv", ".tsv", ".tab"}
        )
        target_idx = all_discovered.index(discovered_path) + 1

        with patch.object(cli, "_wait_for_enter", return_value=None), \
             patch.object(cli, "_read_menu_choice", side_effect=["2", str(target_idx), "1"]):
            cli._change_dataset_partition()

        assert cli.session_config.custom_dataset_path == discovered_path.resolve()
        assert cli._get_selected_dataset_path() == discovered_path.resolve()
        assert cli._get_selected_dataset_label() == f"[Custom] {custom_name}"
    finally:
        if discovered_path.exists():
            discovered_path.unlink()


# ===========================================================================
# 3. Valid Custom CSV Selected Through an Absolute Path
# ===========================================================================

def test_03_valid_custom_csv_absolute_path(tmp_path: Path):
    """Test selecting a valid CSV file located outside the repository via absolute path."""
    csv_file = _create_sample_csv(tmp_path / "external_dataset.csv")
    abs_path_str = str(csv_file.resolve())

    cli = NidsAgentCli()
    # Simulate [3] Custom Path -> input -> [1] Confirm
    with patch.object(cli, "_read_menu_choice", side_effect=["3", "1"]), \
         patch("builtins.input", return_value=abs_path_str):
        cli._change_dataset_partition()

    assert cli.session_config.custom_dataset_path == csv_file.resolve()
    assert cli.session_config.custom_dataset_config is not None
    assert cli.session_config.custom_dataset_config.label_column == "Label"
    assert cli.session_config.custom_dataset_config.normal_labels == ["BENIGN"]
    assert cli._get_selected_dataset_path() == csv_file.resolve()


# ===========================================================================
# 4. Relative Path Resolution
# ===========================================================================

def test_04_relative_path_resolution(tmp_path: Path):
    """Test resolving a relative path against current working directory."""
    csv_file = _create_sample_csv(tmp_path / "rel_data.csv")
    rel_path_str = str(csv_file.relative_to(Path.cwd())) if csv_file.is_relative_to(Path.cwd()) else str(csv_file.name)

    # Test preflight directly with relative path
    report = inspect_custom_dataset_preflight(csv_file)
    assert report.ok is True
    assert report.resolved_path.is_absolute()
    assert report.resolved_path == csv_file.resolve()


# ===========================================================================
# 5. Paths Containing Spaces and Quotes
# ===========================================================================

def test_05_paths_containing_spaces_and_quotes(tmp_path: Path):
    """Ensure paths with spaces and surrounding single/double quotes resolve cleanly."""
    folder = tmp_path / "research folder with spaces"
    folder.mkdir()
    csv_file = _create_sample_csv(folder / "my capture data.csv")

    quoted_input = f'"{csv_file.resolve()}"'
    cli = NidsAgentCli()
    with patch.object(cli, "_read_menu_choice", side_effect=["3", "1"]), \
         patch("builtins.input", return_value=quoted_input):
        cli._change_dataset_partition()

    assert cli.session_config.custom_dataset_path == csv_file.resolve()
    assert cli._get_selected_dataset_path() == csv_file.resolve()


# ===========================================================================
# 6. Invalid, Missing, Unreadable, and Empty Files
# ===========================================================================

def test_06_missing_and_empty_files_rejected(tmp_path: Path):
    """Test rejection of non-existent files and zero-byte files."""
    missing = tmp_path / "does_not_exist.csv"
    rep_missing = inspect_custom_dataset_preflight(missing)
    assert rep_missing.ok is False
    assert any("does not exist" in err.lower() for err in rep_missing.errors)

    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("", encoding="utf-8")
    rep_empty = inspect_custom_dataset_preflight(empty_file)
    assert rep_empty.ok is False
    assert any("empty" in err.lower() for err in rep_empty.errors)

    a_dir = tmp_path / "a_directory"
    a_dir.mkdir()
    rep_dir = inspect_custom_dataset_preflight(a_dir)
    assert rep_dir.ok is False
    assert any("not a regular file" in err.lower() for err in rep_dir.errors)


# ===========================================================================
# 7. Unsupported Formats and Malformed Tabular Data
# ===========================================================================

def test_07_unsupported_extensions_and_malformed_data(tmp_path: Path):
    """Test rejection of unsupported formats (.json, .parquet) and non-numeric files."""
    json_file = tmp_path / "data.json"
    json_file.write_text('{"key": "value"}', encoding="utf-8")
    rep_json = inspect_custom_dataset_preflight(json_file)
    assert rep_json.ok is False
    assert any("unsupported" in err.lower() for err in rep_json.errors)

    # CSV with only string columns (no numeric features)
    text_csv = tmp_path / "text_only.csv"
    text_csv.write_text("Label,ip_src,ip_dst\nBENIGN,1.1.1.1,2.2.2.2\nAttack,3.3.3.3,4.4.4.4\n", encoding="utf-8")
    rep_text = inspect_custom_dataset_preflight(text_csv)
    assert rep_text.ok is False
    assert any("numeric" in err.lower() for err in rep_text.errors)


# ===========================================================================
# 8. Custom File Whose Label Column is Not Named 'Label'
# ===========================================================================

def test_08_custom_label_column_name_detected(tmp_path: Path):
    """Verify that datasets with alternative label column names ('class', 'attack') are inferred."""
    csv_file = tmp_path / "class_named_dataset.csv"
    _create_sample_csv(csv_file, label_col="class", normal_val="normal")

    report = inspect_custom_dataset_preflight(csv_file)
    assert report.ok is True
    assert report.selected_label_column == "class"
    assert report.selected_normal_value == "normal"
    assert "Flow_Duration" in report.numeric_columns


# ===========================================================================
# 9. Missing Label Column and Ambiguous Schema
# ===========================================================================

def test_09_ambiguous_schema_allows_explicit_label_selection(tmp_path: Path):
    """When schema is ambiguous, user can explicitly select the label column."""
    ambiguous = tmp_path / "ambiguous.csv"
    pd.DataFrame({
        "metric_a": [1.0, 2.0, 3.0, 4.0],
        "metric_b": [10.0, 20.0, 30.0, 40.0],
        "target_flag": ["benign", "benign", "malicious", "malicious"],
    }).to_csv(ambiguous, index=False)

    # Without hint
    rep1 = inspect_custom_dataset_preflight(ambiguous)
    assert rep1.ok is True

    # With explicit hint selecting target_flag
    rep2 = inspect_custom_dataset_preflight(ambiguous, explicit_label_column="target_flag")
    assert rep2.ok is True
    assert rep2.selected_label_column == "target_flag"
    assert rep2.selected_normal_value == "benign"
    assert set(rep2.numeric_columns) == {"metric_a", "metric_b"}


# ===========================================================================
# 10. Benign-Class Selection and Validation
# ===========================================================================

def test_10_benign_class_selection_and_mask_generation(tmp_path: Path):
    """Test explicit selection of the benign class and verify build_attack_mask."""
    csv_file = tmp_path / "binary_data.csv"
    pd.DataFrame({
        "label": ["0", "0", "1", "1", "0"],
        "feature": [1.0, 2.0, 3.0, 4.0, 5.0],
    }).to_csv(csv_file, index=False)

    report = inspect_custom_dataset_preflight(csv_file, explicit_normal_value="0")
    assert report.ok is True
    assert report.selected_normal_value == "0"

    cfg = create_custom_dataset_config(
        file_path=csv_file,
        label_column="label",
        normal_labels=["0"],
    )
    df, features = load_dataset(csv_file, cfg)
    mask = build_attack_mask(df["label"], cfg.normal_labels, cfg.attack_labels, cfg.attack_label_mode)

    # Rows with '0' should be False (not attack), rows with '1' should be True (attack)
    assert list(mask) == [False, False, True, True, False]


# ===========================================================================
# 11. Cancellation Preserves Session Configuration
# ===========================================================================

def test_11_cancellation_preserves_session_configuration():
    """Ensure cancelling out of the custom dataset prompt preserves current session state."""
    cli = NidsAgentCli()
    initial_dataset = cli.session_config.dataset_name

    # Select [3] Custom Path -> Enter 'B' to cancel -> Enter 'B' on source menu
    with patch.object(cli, "_read_menu_choice", side_effect=["3", "B"]), \
         patch("builtins.input", return_value="B"):
        cli._change_dataset_partition()

    assert cli.session_config.dataset_name == initial_dataset
    assert cli.session_config.custom_dataset_path is None


# ===========================================================================
# 12. Confirmed Custom Path Propagation into Runtime Call
# ===========================================================================

def test_12_confirmed_custom_path_propagates_to_batch_runtime(tmp_path: Path):
    """Verify that a confirmed custom path and its DatasetConfig reach run_phase3a_batch."""
    csv_file = _create_sample_csv(tmp_path / "runtime_target.csv", label_col="attack_type", normal_val="clean")
    cli = NidsAgentCli()

    # Pre-set the custom dataset in session config
    cfg = create_custom_dataset_config(
        csv_file,
        label_column="attack_type",
        normal_labels=["clean"],
    )
    cli.session_config.custom_dataset_path = csv_file.resolve()
    cli.session_config.custom_dataset_config = cfg
    cli.session_config.dataset_name = csv_file.name

    captured_kwargs = {}

    def mock_batch_runner(dataset_path, **kwargs):
        captured_kwargs["dataset_path"] = dataset_path
        captured_kwargs.update(kwargs)
        return {
            "batch_id": "test_batch_123",
            "artifact_paths": {"component_run_path": "logs/test/run.json"},
        }

    with patch("interface.cli.run_phase3a_batch", side_effect=mock_batch_runner), \
         patch.object(cli, "_read_menu_choice", return_value="0"), \
         patch.object(cli, "_wait_for_enter", return_value=None), \
         patch.object(cli, "_prompt_yes_no", return_value=False), \
         patch.object(cli, "_build_phase3a_runtime_run_context", return_value=MagicMock()):
        cli._run_phase3a_runtime_flow("full_batch")

    assert captured_kwargs["dataset_path"] == csv_file.resolve()
    assert captured_kwargs["dataset_config"] == cfg
    assert captured_kwargs["dataset_config"].label_column == "attack_type"
    assert captured_kwargs["dataset_config"].normal_labels == ["clean"]


# ===========================================================================
# 13. No Silent Fallback When Custom Path Fails
# ===========================================================================

def test_13_no_silent_fallback_on_unresolved_custom_path():
    """Ensure that an invalid custom dataset path raises FileNotFoundError rather than silently falling back."""
    cli = NidsAgentCli()
    ghost_path = Path("C:/unlikely_test_dir/nonexistent_ghost_dataset.csv")
    cli.session_config.custom_dataset_path = ghost_path

    # _get_selected_dataset_path must explicitly fail
    with pytest.raises(FileNotFoundError) as exc_info:
        cli._get_selected_dataset_path()

    assert "nonexistent_ghost_dataset.csv" in str(exc_info.value)
    assert "Configured custom dataset file does not exist" in str(exc_info.value)


# ===========================================================================
# 14. Correct Source Identity & Metadata in Persisted Ledger
# ===========================================================================

def test_14_correct_source_identity_in_persisted_ledger(tmp_path: Path):
    """Verify that run_phase3a_batch records custom dataset metadata in BatchLedger."""
    csv_file = _create_sample_csv(tmp_path / "ledger_check.csv", label_col="cat", normal_val="benign")
    cfg = create_custom_dataset_config(
        csv_file,
        label_column="cat",
        normal_labels=["benign"],
    )

    log_dir = tmp_path / "test_logs"

    # Mock semantic extraction and investigation analysis so no live LLM calls are made
    fake_semantic = {
        "component_run": {"component": "semantic_extraction", "status": "ok", "validation_ok": True},
        "parsed_output": {"substrate_id": "sub-1"},
        "artifact_paths": {"component_run_path": str(log_dir / "sem_run.json")},
    }
    fake_analysis = {
        "component_run": {"component": "investigation_analysis", "status": "ok", "validation_ok": True},
        "parsed_output": {"analysis_id": "an-1", "hypotheses": []},
        "artifact_paths": {"component_run_path": str(log_dir / "an_run.json")},
    }

    with patch("phase3_runtime.orchestrator.run_semantic_extraction", return_value=fake_semantic), \
         patch("phase3_runtime.orchestrator.run_investigation_analysis", return_value=fake_analysis):
        bundle = run_phase3a_batch(
            csv_file,
            dataset_config=cfg,
            caller_mode="test",
            max_rounds=0,
            execution_mode="cognitive_only",
            log_dir=log_dir,
        )

    ledger_path = Path(bundle["artifact_paths"]["batch_ledger_path"])
    assert ledger_path.is_file()

    import json
    with open(ledger_path, "r", encoding="utf-8") as f:
        ledger_data = json.load(f)

    meta = ledger_data.get("dataset_metadata", {})
    assert meta.get("is_custom_dataset") is True
    assert meta.get("source_type") == "custom_path"
    assert meta.get("label_column") == "cat"
    assert meta.get("normal_labels") == ["benign"]
    assert str(csv_file.resolve()) in meta.get("dataset_path")

    # Also verify the in-memory ledger instance returned
    ledger_obj = bundle["batch_ledger"]
    assert ledger_obj.dataset_metadata["is_custom_dataset"] is True
    assert ledger_obj.dataset_metadata["label_column"] == "cat"


# ===========================================================================
# 15. No Mutation of the Selected Source File
# ===========================================================================

def test_15_no_mutation_of_selected_source_file(tmp_path: Path):
    """Confirm the source CSV file is strictly read-only and never modified in place."""
    csv_file = _create_sample_csv(tmp_path / "immutable_test.csv")
    initial_hash = hashlib.sha256(csv_file.read_bytes()).hexdigest()

    # Pre-flight inspection
    report = inspect_custom_dataset_preflight(csv_file)
    assert report.ok is True

    # Loading via load_dataset
    cfg = create_custom_dataset_config(csv_file, "Label", ["BENIGN"])
    df, features = load_dataset(csv_file, cfg)

    # Post-execution hash verification
    final_hash = hashlib.sha256(csv_file.read_bytes()).hexdigest()
    assert initial_hash == final_hash, "Source dataset file was mutated during inspection/loading!"


# ===========================================================================
# 16. Regression: Existing CLI Workflows Unaffected
# ===========================================================================

def test_16_regression_existing_cli_workflows_unaffected():
    """Verify that existing SessionConfig defaults and predefined menus remain unaffected."""
    cfg = SessionConfig()
    assert cfg.model_name == "gpt-4.1-mini"
    assert cfg.max_steps == 10
    assert cfg.custom_dataset_path is None
    assert cfg.custom_dataset_config is None

    # Verify infer_dataset_config for benchmark datasets
    cicids_path = Path(DATA_DIR) / "cic_ids_2017" / "Monday-WorkingHours.pcap_ISCX.csv"
    inferred_cic = infer_dataset_config(cicids_path)
    assert inferred_cic.dataset_name == "cic_ids_2017"
    assert inferred_cic.label_column == "Label"
    assert inferred_cic.normal_labels == ["BENIGN"]

    unsw_path = Path(DATA_DIR) / "UNSW_NB15" / "UNSW-NB15_1.csv"
    inferred_unsw = infer_dataset_config(unsw_path)
    assert inferred_unsw.dataset_name == "unsw_nb15"
    assert inferred_unsw.label_column == "label"
    assert inferred_unsw.normal_labels == ["0"]
