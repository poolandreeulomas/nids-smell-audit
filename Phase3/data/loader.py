"""Dataset loading and cleaning helpers for MVP.

Loads CSV/TSV files, validates label column, removes ignored columns,
and returns a cleaned dataframe with valid numeric features.
"""

from pathlib import Path

import pandas as pd

from data.dataset_config import DatasetConfig
from data.validation import DatasetValidationError, validate_label_column


def _resolve_delimiter(file_path: str | Path, configured_delimiter: str | None) -> str:
    """Resolve delimiter from config or file extension."""
    if configured_delimiter:
        return configured_delimiter

    suffix = Path(file_path).suffix.lower()
    if suffix in {".tsv", ".tab"}:
        return "\t"
    return ","


def _build_clean_columns(df: pd.DataFrame, config: DatasetConfig) -> list[str]:
    """Build the list of columns to keep in the cleaned dataframe."""
    if config.label_column in config.ignored_columns:
        raise DatasetValidationError(
            "Configuration error: label column cannot be in ignored_columns."
        )

    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    valid_numeric_features = [
        col
        for col in numeric_columns
        if col != config.label_column and col not in config.ignored_columns
    ]

    if config.non_numeric_policy == "drop":
        keep_columns = [config.label_column] + valid_numeric_features
    elif config.non_numeric_policy == "keep":
        keep_columns = [
            col for col in df.columns if col not in set(config.ignored_columns)
        ]
    else:
        raise DatasetValidationError(
            "Configuration error: non_numeric_policy must be 'drop' or 'keep'."
        )

    return keep_columns


def _normalize_columns(df: pd.DataFrame, config: DatasetConfig) -> pd.DataFrame:
    """Normalize dataframe column names according to config policy."""
    if not config.strip_column_names:
        return df

    normalized_df = df.copy()
    normalized_df.columns = [
        col.strip() if isinstance(col, str) else col for col in normalized_df.columns
    ]
    return normalized_df


def load_dataset(file_path: str | Path, config: DatasetConfig) -> tuple[pd.DataFrame, list[str]]:
    """Load dataset and return (cleaned_dataframe, valid_numeric_features).

    Steps:
    1. Read CSV/TSV according to delimiter rules.
    2. Validate label column.
    3. Remove ignored columns.
    4. Return cleaned dataframe and numeric feature names.
    """
    delimiter = _resolve_delimiter(file_path, config.delimiter)
    df = pd.read_csv(file_path, sep=delimiter)

    df = _normalize_columns(df, config)

    effective_label_column = (
        config.label_column.strip() if config.strip_column_names else config.label_column
    )
    effective_ignored_columns = [
        col.strip() if config.strip_column_names else col
        for col in config.ignored_columns
    ]

    effective_config = DatasetConfig(
        dataset_name=config.dataset_name,
        label_column=effective_label_column,
        normal_labels=config.normal_labels,
        attack_labels=config.attack_labels,
        attack_label_mode=config.attack_label_mode,
        ignored_columns=effective_ignored_columns,
        non_numeric_policy=config.non_numeric_policy,
        strip_column_names=config.strip_column_names,
        delimiter=config.delimiter,
    )

    validate_label_column(df.columns.tolist(), effective_config.label_column)

    keep_columns = _build_clean_columns(df, effective_config)
    cleaned_df = df[keep_columns].copy()

    if effective_config.label_column != config.label_column:
        cleaned_df = cleaned_df.rename(
            columns={effective_config.label_column: config.label_column}
        )

    valid_numeric_features = [
        col
        for col in cleaned_df.select_dtypes(include="number").columns.tolist()
        if col != config.label_column
    ]

    return cleaned_df, valid_numeric_features
