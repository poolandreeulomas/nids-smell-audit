"""Validation helpers for dataset loading and feature checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import numpy as np
import pandas as pd


class DatasetValidationError(ValueError):
    """Base exception for dataset validation failures."""


class MissingLabelColumnError(DatasetValidationError):
    """Raised when the expected label column is missing."""


class InvalidFeatureNameError(DatasetValidationError):
    """Raised when a requested feature name is not valid."""


class InvalidDatasetConfigError(DatasetValidationError):
    """Raised when dataset configuration is inconsistent or unsupported."""


def validate_label_column(columns: list[str], label_column: str) -> None:
    """Ensure the configured label column exists in the dataset."""
    if label_column not in columns:
        preview = ", ".join(columns[:10])
        raise MissingLabelColumnError(
            f"Missing label column '{label_column}'. "
            f"Available columns (first 10): {preview}"
        )


_FEATURE_NAME_EXPANSIONS = {
    r"\bbwd\b": "backward",
    r"\bfwd\b": "forward",
    r"\bpkts?\b": "packets",
    r"\bpkt\b": "packet",
    r"\blen\b": "length",
    r"\btotal\b": "total",
}


def _normalize_feature_name(value: str) -> str:
    normalized = value.strip().casefold()
    for pattern, replacement in _FEATURE_NAME_EXPANSIONS.items():
        normalized = re.sub(pattern, replacement, normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def resolve_feature_name(feature_name: str, valid_features: list[str]) -> str | None:
    """Resolve a model-produced alias to the canonical dataset feature name."""
    if not isinstance(feature_name, str):
        return None

    candidate = feature_name.strip()
    if not candidate:
        return None

    if candidate in valid_features:
        return candidate

    normalized_candidate = _normalize_feature_name(candidate)
    for valid_feature in valid_features:
        if normalized_candidate == _normalize_feature_name(valid_feature):
            return valid_feature
    return None


def validate_feature_name(feature_name: str, valid_features: list[str]) -> str:
    """Ensure a requested feature is present in the valid feature list."""
    resolved = resolve_feature_name(feature_name, valid_features)
    if resolved is None:
        raise InvalidFeatureNameError(
            f"Invalid feature '{feature_name}'. "
            f"Feature is not present in valid numeric features."
        )
    return resolved


def validate_feature_names(feature_names: list[str], valid_features: list[str]) -> list[str]:
    """Validate a list of requested feature names."""
    canonical_names: list[str] = []
    invalid: list[str] = []
    for name in feature_names:
        resolved = resolve_feature_name(name, valid_features)
        if resolved is None:
            invalid.append(str(name))
        else:
            canonical_names.append(resolved)

    if invalid:
        invalid_preview = ", ".join(invalid)
        raise InvalidFeatureNameError(
            f"Invalid feature names: {invalid_preview}. "
            f"Requested features must exist in valid numeric feature list."
        )
    return canonical_names


def validate_attack_label_config(attack_label_mode: str, attack_labels: list[str]) -> None:
    """Validate attack label policy settings."""
    allowed_modes = {"non_normal", "explicit_attack_labels"}
    if attack_label_mode not in allowed_modes:
        raise InvalidDatasetConfigError(
            f"Invalid attack_label_mode '{attack_label_mode}'. "
            f"Allowed values: {sorted(allowed_modes)}"
        )

    if attack_label_mode == "explicit_attack_labels" and not attack_labels:
        raise InvalidDatasetConfigError(
            "attack_labels cannot be empty when attack_label_mode is "
            "'explicit_attack_labels'."
        )


def build_attack_mask(
    label_series: pd.Series,
    normal_labels: list[str],
    attack_labels: list[str],
    attack_label_mode: str,
) -> np.ndarray:
    """Build attack mask according to dataset label policy."""
    validate_attack_label_config(attack_label_mode, attack_labels)

    labels = label_series.astype(str).str.strip().to_numpy()
    if attack_label_mode == "explicit_attack_labels":
        return np.isin(labels, np.asarray([str(lbl).strip() for lbl in attack_labels]))

    return ~np.isin(labels, np.asarray([str(lbl).strip() for lbl in normal_labels]))


# =========================================================================
# Custom Dataset Pre-Flight Validation
# =========================================================================


@dataclass
class DatasetPreflightReport:
    """Result of bounded pre-flight schema inspection for a custom dataset."""

    ok: bool
    file_path: Path
    resolved_path: Path
    file_size_bytes: int
    delimiter: str
    total_columns: int
    column_names: list[str]
    numeric_columns: list[str]
    candidate_label_columns: list[str]
    selected_label_column: str | None
    unique_label_values: list[str]
    selected_normal_value: str | None
    row_count_sampled: int
    estimated_total_rows: int | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _resolve_delimiter_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".tsv", ".tab"}:
        return "\t"
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline()
        if "\t" in first_line and first_line.count("\t") > first_line.count(","):
            return "\t"
        if ";" in first_line and first_line.count(";") > first_line.count(","):
            return ";"
    except Exception:
        pass
    return ","


def _fast_count_lines(path: Path) -> int | None:
    """Quickly estimate or count rows in a tabular file without loading all data."""
    try:
        size = path.stat().st_size
        if size == 0:
            return 0
        if size <= 25_000_000:  # <= 25 MB: exact count
            with open(path, "rb") as f:
                lines = sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1024 * 1024), b""))
            return max(0, lines - 1)  # subtract header
        # For larger files: estimate from first 100 KB
        with open(path, "rb") as f:
            sample = f.read(100 * 1024)
        sample_lines = sample.count(b"\n")
        if sample_lines > 0:
            avg_line_len = len(sample) / sample_lines
            return int(size / avg_line_len) - 1
    except Exception:
        pass
    return None


def inspect_custom_dataset_preflight(
    file_path: str | Path,
    *,
    explicit_label_column: str | None = None,
    explicit_normal_value: str | None = None,
    sample_rows: int = 100,
) -> DatasetPreflightReport:
    """Perform bounded pre-flight schema inspection on a custom dataset file.

    Validates:
    - Path existence, type, readability, non-empty.
    - Supported extensions (.csv, .tsv, .tab).
    - Tabular structure, column headers, valid delimiter.
    - Presence of at least one valid numeric feature.
    - Ground-truth label column identification and normal/benign class resolution.
    - Bounded sample read (never loads the full file into memory).

    Returns:
        DatasetPreflightReport containing validation status, schema metadata, and any errors/warnings.
    """
    raw_path = Path(file_path)
    warnings: list[str] = []
    errors: list[str] = []

    # 1. Path existence and file check
    try:
        resolved = raw_path.resolve()
    except Exception as exc:
        return DatasetPreflightReport(
            ok=False,
            file_path=raw_path,
            resolved_path=raw_path,
            file_size_bytes=0,
            delimiter=",",
            total_columns=0,
            column_names=[],
            numeric_columns=[],
            candidate_label_columns=[],
            selected_label_column=None,
            unique_label_values=[],
            selected_normal_value=None,
            row_count_sampled=0,
            estimated_total_rows=None,
            errors=[f"Invalid filesystem path: {exc}"],
        )

    if not resolved.exists():
        errors.append(f"File does not exist: '{resolved}'.")
        return DatasetPreflightReport(
            ok=False,
            file_path=raw_path,
            resolved_path=resolved,
            file_size_bytes=0,
            delimiter=",",
            total_columns=0,
            column_names=[],
            numeric_columns=[],
            candidate_label_columns=[],
            selected_label_column=None,
            unique_label_values=[],
            selected_normal_value=None,
            row_count_sampled=0,
            estimated_total_rows=None,
            errors=errors,
        )

    if not resolved.is_file():
        errors.append(f"Path is not a regular file: '{resolved}'.")
        return DatasetPreflightReport(
            ok=False,
            file_path=raw_path,
            resolved_path=resolved,
            file_size_bytes=0,
            delimiter=",",
            total_columns=0,
            column_names=[],
            numeric_columns=[],
            candidate_label_columns=[],
            selected_label_column=None,
            unique_label_values=[],
            selected_normal_value=None,
            row_count_sampled=0,
            estimated_total_rows=None,
            errors=errors,
        )

    # 2. Extension check
    suffix = resolved.suffix.lower()
    if suffix not in {".csv", ".tsv", ".tab"}:
        errors.append(
            f"Unsupported file extension '{suffix}'. ATLAS requires a .csv, .tsv, or .tab tabular file."
        )
        return DatasetPreflightReport(
            ok=False,
            file_path=raw_path,
            resolved_path=resolved,
            file_size_bytes=0,
            delimiter=",",
            total_columns=0,
            column_names=[],
            numeric_columns=[],
            candidate_label_columns=[],
            selected_label_column=None,
            unique_label_values=[],
            selected_normal_value=None,
            row_count_sampled=0,
            estimated_total_rows=None,
            errors=errors,
        )

    # 3. Readability & size
    try:
        file_size = resolved.stat().st_size
    except Exception as exc:
        errors.append(f"Cannot read file metadata: {exc}")
        file_size = 0

    if file_size == 0:
        errors.append(f"File is empty (0 bytes): '{resolved}'.")
        return DatasetPreflightReport(
            ok=False,
            file_path=raw_path,
            resolved_path=resolved,
            file_size_bytes=file_size,
            delimiter=",",
            total_columns=0,
            column_names=[],
            numeric_columns=[],
            candidate_label_columns=[],
            selected_label_column=None,
            unique_label_values=[],
            selected_normal_value=None,
            row_count_sampled=0,
            estimated_total_rows=0,
            errors=errors,
        )

    # 4. Delimiter and sample read
    delimiter = _resolve_delimiter_for_path(resolved)
    try:
        df_sample = pd.read_csv(resolved, sep=delimiter, nrows=sample_rows, encoding="utf-8")
    except UnicodeDecodeError:
        try:
            df_sample = pd.read_csv(resolved, sep=delimiter, nrows=sample_rows, encoding="latin-1")
            warnings.append("File required Latin-1 fallback encoding; non-ASCII characters may be present.")
        except Exception as exc:
            errors.append(f"Failed to decode tabular file: {exc}")
            df_sample = pd.DataFrame()
    except Exception as exc:
        errors.append(f"Failed to parse tabular file: {exc}")
        df_sample = pd.DataFrame()

    if errors or df_sample.empty:
        if not errors:
            errors.append("File contains no data rows or could not be parsed.")
        return DatasetPreflightReport(
            ok=False,
            file_path=raw_path,
            resolved_path=resolved,
            file_size_bytes=file_size,
            delimiter=delimiter,
            total_columns=len(df_sample.columns),
            column_names=[str(c).strip() for c in df_sample.columns],
            numeric_columns=[],
            candidate_label_columns=[],
            selected_label_column=None,
            unique_label_values=[],
            selected_normal_value=None,
            row_count_sampled=0,
            estimated_total_rows=0,
            warnings=warnings,
            errors=errors,
        )

    # Clean column headers
    df_sample.columns = [str(c).strip() for c in df_sample.columns]
    column_names = list(df_sample.columns)
    total_columns = len(column_names)

    if total_columns < 2:
        errors.append(
            f"Dataset has only {total_columns} column(s). ATLAS requires at least 1 feature column and 1 label column."
        )

    # 5. Numeric feature analysis
    numeric_columns = [
        col for col in df_sample.select_dtypes(include="number").columns.tolist()
    ]

    # 6. Label candidate discovery
    candidate_label_columns: list[str] = []
    # Exact matches
    for candidate in ["Label", "label"]:
        if candidate in column_names and candidate not in candidate_label_columns:
            candidate_label_columns.append(candidate)
    # Case-insensitive "label" in name
    for col in column_names:
        if "label" in col.lower() and col not in candidate_label_columns:
            candidate_label_columns.append(col)
    # Common classification target names
    for col in column_names:
        if col.lower() in {"class", "target", "attack", "category", "classification"} and col not in candidate_label_columns:
            candidate_label_columns.append(col)
    # Fallback: all non-numeric columns
    for col in column_names:
        if col not in numeric_columns and col not in candidate_label_columns:
            candidate_label_columns.append(col)

    # Select active label column
    selected_label_column: str | None = None
    if explicit_label_column and explicit_label_column in column_names:
        selected_label_column = explicit_label_column
    elif candidate_label_columns:
        selected_label_column = candidate_label_columns[0]
    elif column_names:
        selected_label_column = column_names[-1]

    # 7. Unique classes and normal class resolution
    unique_label_values: list[str] = []
    selected_normal_value: str | None = None

    if selected_label_column and selected_label_column in column_names:
        series = df_sample[selected_label_column].dropna()
        unique_label_values = [str(v).strip() for v in series.unique() if str(v).strip()]

        if not unique_label_values:
            errors.append(f"Label column '{selected_label_column}' has no valid non-null values in sample.")
        else:
            if len(unique_label_values) < 2:
                warnings.append(
                    f"Sample rows contain only 1 class ({unique_label_values}). "
                    "Ensure the dataset contains both normal and anomalous instances before running shortcut/class-conditioned tools."
                )

            # Resolve normal class value
            if explicit_normal_value and explicit_normal_value in unique_label_values:
                selected_normal_value = explicit_normal_value
            else:
                # Common normal conventions
                for candidate in ["BENIGN", "0", "normal", "Normal", "benign", "legitimate", "0.0"]:
                    if candidate in unique_label_values:
                        selected_normal_value = candidate
                        break
                if selected_normal_value is None:
                    # Case-insensitive match
                    for v in unique_label_values:
                        if v.lower() in {"benign", "normal", "0", "legitimate"}:
                            selected_normal_value = v
                            break
                if selected_normal_value is None:
                    selected_normal_value = unique_label_values[0]

    # 8. Remaining numeric features
    remaining_numeric = [c for c in numeric_columns if c != selected_label_column]
    if len(remaining_numeric) == 0:
        errors.append(
            f"No numeric feature columns remain after reserving '{selected_label_column}' as the label column. "
            "ATLAS statistical tools require at least one numeric feature."
        )

    # 9. Estimated rows
    estimated_rows = _fast_count_lines(resolved)

    return DatasetPreflightReport(
        ok=len(errors) == 0,
        file_path=raw_path,
        resolved_path=resolved,
        file_size_bytes=file_size,
        delimiter=delimiter,
        total_columns=total_columns,
        column_names=column_names,
        numeric_columns=remaining_numeric,
        candidate_label_columns=candidate_label_columns,
        selected_label_column=selected_label_column,
        unique_label_values=unique_label_values,
        selected_normal_value=selected_normal_value,
        row_count_sampled=len(df_sample),
        estimated_total_rows=estimated_rows,
        warnings=warnings,
        errors=errors,
    )
