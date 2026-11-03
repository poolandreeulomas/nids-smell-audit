"""Dataset configuration layer for MVP data loading.

This module centralizes dataset-specific assumptions so tools and agent
code remain dataset-agnostic.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration contract for tabular dataset loading and cleaning."""

    dataset_name: str = "cic_ids_2017"
    label_column: str = "Label"
    normal_labels: list[str] = field(default_factory=lambda: ["BENIGN"])
    attack_labels: list[str] = field(default_factory=list)
    # Allowed values: "non_normal", "explicit_attack_labels"
    attack_label_mode: str = "non_normal"
    ignored_columns: list[str] = field(default_factory=list)
    non_numeric_policy: str = "drop"
    # When enabled, strips leading/trailing whitespace from all column names.
    strip_column_names: bool = True
    delimiter: str | None = None
    # Dataset metadata for prompt/context generation.
    dataset_display_name: str = "CICIDS2017"
    dataset_description: str = (
        "CICIDS2017 benchmark dataset containing benign and up-to-date common "
        "network attacks, with labeled network flows across multiple attack scenarios "
        "including DDoS, PortScan, Web Attacks, Infiltration, and Brute Force."
    )
    traffic_domain: str = "enterprise network traffic"
    label_description: str = (
        "Multi-class labels: 'BENIGN' for normal traffic and specific attack names "
        "for malicious traffic."
    )


DEFAULT_DATASET_CONFIG = DatasetConfig()

DATASET_CONFIGS: dict[str, DatasetConfig] = {
    "cic_ids_2017": DEFAULT_DATASET_CONFIG,
    "unsw_nb15": DatasetConfig(
        dataset_name="unsw_nb15",
        label_column="label",
        normal_labels=["0"],
        attack_labels=["1"],
        attack_label_mode="explicit_attack_labels",
        ignored_columns=["id"],
        non_numeric_policy="drop",
        strip_column_names=True,
        delimiter=",",
        dataset_display_name="UNSW-NB15",
        dataset_description=(
            "UNSW-NB15 benchmark dataset containing a hybrid of real modern normal "
            "and synthetic attack activities in network traffic, with nine attack "
            "families including Fuzzers, Analysis, Backdoors, DoS, Exploits, Generic, "
            "Reconnaissance, Shellcode, and Worms."
        ),
        traffic_domain="enterprise network traffic",
        label_description=(
            "Binary labels: 0 (normal) and 1 (attack) with an additional 'attack_cat' "
            "column providing the specific attack category."
        ),
    ),
}

CUSTOM_DATASET_CONFIGS: dict[str, DatasetConfig] = {}


def register_custom_dataset_config(
    dataset_path: str | Path,
    config: DatasetConfig,
) -> None:
    """Register a custom dataset configuration bound to a file path or name."""
    resolved_key = str(Path(dataset_path).resolve())
    CUSTOM_DATASET_CONFIGS[resolved_key] = config
    CUSTOM_DATASET_CONFIGS[Path(dataset_path).name] = config
    CUSTOM_DATASET_CONFIGS[config.dataset_name] = config


def unregister_custom_dataset_config(
    dataset_path: str | Path | None = None,
) -> None:
    """Unregister custom dataset configurations."""
    if dataset_path is None:
        CUSTOM_DATASET_CONFIGS.clear()
        return
    resolved_key = str(Path(dataset_path).resolve())
    CUSTOM_DATASET_CONFIGS.pop(resolved_key, None)
    CUSTOM_DATASET_CONFIGS.pop(Path(dataset_path).name, None)


def create_custom_dataset_config(
    file_path: str | Path,
    label_column: str,
    normal_labels: list[str],
    *,
    attack_labels: list[str] | None = None,
    attack_label_mode: str = "non_normal",
    ignored_columns: list[str] | None = None,
    non_numeric_policy: str = "drop",
    strip_column_names: bool = True,
    delimiter: str | None = None,
    dataset_name: str | None = None,
    dataset_display_name: str | None = None,
    dataset_description: str | None = None,
    traffic_domain: str = "network traffic",
    label_description: str | None = None,
) -> DatasetConfig:
    """Factory to build a valid DatasetConfig for a custom dataset."""
    path = Path(file_path)
    stem = path.stem
    name = dataset_name or f"custom_{stem}"
    display_name = dataset_display_name or stem
    desc = dataset_description or f"Custom dataset partition loaded from '{path.name}'."
    normal = [str(lbl).strip() for lbl in normal_labels if str(lbl).strip()]
    if not normal:
        normal = ["BENIGN"]
    attacks = [str(lbl).strip() for lbl in attack_labels if str(lbl).strip()] if attack_labels else []
    label_desc = (
        label_description
        or f"Label column '{label_column}' with normal/benign class {normal}."
    )

    return DatasetConfig(
        dataset_name=name,
        label_column=label_column.strip(),
        normal_labels=normal,
        attack_labels=attacks,
        attack_label_mode=attack_label_mode,
        ignored_columns=list(ignored_columns or []),
        non_numeric_policy=non_numeric_policy,
        strip_column_names=strip_column_names,
        delimiter=delimiter,
        dataset_display_name=display_name,
        dataset_description=desc,
        traffic_domain=traffic_domain,
        label_description=label_desc,
    )


def get_default_dataset_config() -> DatasetConfig:
    """Return the default dataset config used by the MVP loader."""
    return DEFAULT_DATASET_CONFIG


def get_dataset_config(dataset_name: str) -> DatasetConfig:
    """Return dataset config by name.

    Raises KeyError if dataset name is unknown.
    """
    if dataset_name in CUSTOM_DATASET_CONFIGS:
        return CUSTOM_DATASET_CONFIGS[dataset_name]
    return DATASET_CONFIGS[dataset_name]


def infer_dataset_config(dataset_path: str | Path) -> DatasetConfig:
    """Resolve the appropriate DatasetConfig from a dataset file path.

    Uses registered custom configs, then parent directory/filename keywords,
    falling back to the default CICIDS config.
    """
    path = Path(dataset_path)
    resolved_key = str(path.resolve())

    # Check for registered custom dataset configs
    if resolved_key in CUSTOM_DATASET_CONFIGS:
        return CUSTOM_DATASET_CONFIGS[resolved_key]
    if path.name in CUSTOM_DATASET_CONFIGS:
        return CUSTOM_DATASET_CONFIGS[path.name]
    if str(dataset_path) in CUSTOM_DATASET_CONFIGS:
        return CUSTOM_DATASET_CONFIGS[str(dataset_path)]

    path_str = str(path).lower()

    # Check for UNSW_NB15 in parent directory or path
    if "unsw_nb15" in path_str:
        return DATASET_CONFIGS["unsw_nb15"]

    # Check for cic_ids_2017 in parent directory or path
    if "cic_ids_2017" in path_str:
        return DATASET_CONFIGS["cic_ids_2017"]

    # Fallback to default
    return DEFAULT_DATASET_CONFIG
