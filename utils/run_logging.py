"""Run artifact persistence helpers for MVP sessions.

This module persists human-readable JSON logs for full run traces and
associated metrics.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from state.schema import AgentState
from state.store import state_to_dict


DEFAULT_RUNS_DIR = Path(__file__).resolve().parent.parent / "logs" / "runs"
_RUN_INDEX_PATTERN = re.compile(r"^run_(?P<index>\d{3})_")
_PROMPT_SECTION_PATTERN = re.compile(r"^[A-Z][A-Z_ ()]+:$")


def _format_partition_tag(partition_name: str | Path | None) -> str:
    raw_name = Path(str(partition_name or "").strip()).name
    stem = Path(raw_name).stem.lower()
    if not stem:
        return "UNK"

    if any(token in stem for token in ("ddos", "dos")):
        return "DS"
    if "portscan" in stem:
        return "PS"
    if any(token in stem for token in ("webattacks", "webattack", "xss", "sqli")):
        return "WEB"
    if any(token in stem for token in ("infiltration", "infilteration")):
        return "INF"
    if any(token in stem for token in ("bruteforce", "ftp", "ssh")):
        return "BF"
    if any(token in stem for token in ("monday", "benign")):
        return "BN"
    if "tuesday" in stem:
        return "TUE"
    if "wednesday" in stem:
        return "WED"
    if "thursday" in stem:
        return "THU"
    if "friday" in stem:
        return "FRI"

    compact = re.sub(r"[^a-z0-9]+", "", stem).upper()
    return compact[:4] or "UNK"


def _format_model_tag(model_name: str | None) -> str:
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return "unknown"
    if normalized.startswith("gpt-"):
        normalized = normalized[4:]
    normalized = normalized.replace("-mini", "_mini")
    normalized = normalized.replace("-nano", "_nano")
    normalized = normalized.replace("-", "_")
    return normalized or "unknown"


def get_next_run_index(log_dir: str | Path | None = None) -> int:
    """Return the next visible run index from persisted CLI-style artifacts."""
    runs_dir = ensure_runs_dir(log_dir)
    max_index = 0
    for path in runs_dir.glob("run_*.json"):
        if path.name.endswith("_metrics.json"):
            continue
        match = _RUN_INDEX_PATTERN.match(path.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group("index")))
    return max_index + 1


def _extract_reproducibility_naming_parts(state: AgentState) -> tuple[str | None, str | None]:
    reproducibility = state.metadata.get("reproducibility") or {}
    if not isinstance(reproducibility, dict):
        return None, None

    dataset_snapshot = reproducibility.get("dataset_snapshot") or {}
    if not isinstance(dataset_snapshot, dict):
        dataset_snapshot = {}

    partition_name = dataset_snapshot.get("path")
    model_name = reproducibility.get("model_name")
    return partition_name, model_name


def ensure_runs_dir(log_dir: str | Path | None = None) -> Path:
    """Ensure the runs directory exists and return it."""
    target = Path(log_dir) if log_dir else DEFAULT_RUNS_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def build_run_basename(
    timestamp: datetime | None = None,
    *,
    run_index: int | None = None,
    partition_name: str | Path | None = None,
    model_name: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    """Build a human-readable basename with index, date, partition, and model."""
    ts = timestamp or datetime.now(UTC)
    visible_index = run_index if run_index is not None else get_next_run_index(
        log_dir)
    return "run_{index:03d}_{day_month}_{partition}_{model}".format(
        index=visible_index,
        day_month=ts.strftime("%d-%m"),
        partition=_format_partition_tag(partition_name),
        model=_format_model_tag(model_name),
    )


def build_session_run_basename(
    run_index: int,
    timestamp: datetime | None = None,
    *,
    partition_name: str | Path | None = None,
    model_name: str | None = None,
) -> str:
    """Build a visible run basename for CLI sessions."""
    return build_run_basename(
        timestamp,
        run_index=run_index,
        partition_name=partition_name,
        model_name=model_name,
    )


def build_run_log_payload(
    state: AgentState,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build full JSON payload for one run log."""
    payload = state_to_dict(state)
    payload["summary"] = {
        "history_len": len(state.history),
        "errors_len": len(state.errors),
        "analyzed_feature_count": len(state.analyzed_features),
        "promising_feature_count": len(state.promising_features),
    }
    if metrics is not None:
        payload["metrics"] = metrics
    return payload


def write_json(file_path: str | Path, payload: dict[str, Any]) -> Path:
    """Write JSON with indentation for easy inspection."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2,
                    ensure_ascii=True), encoding="utf-8")
    return path


def _format_debug_observation(observation: object) -> str:
    if not isinstance(observation, dict):
        return json.dumps(observation, ensure_ascii=True)

    compact = {
        "ok": observation.get("ok"),
        "tool": observation.get("tool"),
        "feature_name": observation.get("feature_name"),
        "value": observation.get("value"),
        "error_code": observation.get("error_code"),
        "error_message": observation.get("error_message"),
    }
    return json.dumps(compact, ensure_ascii=True, sort_keys=True)


def _extract_prompt_sections(prompt_text: object) -> list[tuple[str, str]]:
    text = str(prompt_text or "")
    if not text.strip():
        return []

    sections: list[tuple[str, str]] = []
    current_header: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_header, current_lines
        if current_header is None:
            return
        sections.append((current_header, "\n".join(current_lines).strip()))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _PROMPT_SECTION_PATTERN.fullmatch(line):
            flush()
            current_header = line[:-1]
            current_lines = []
            continue
        if current_header is not None:
            current_lines.append(raw_line)

    flush()
    return sections


def _format_prompt_section_names(prompt_text: object) -> str:
    sections = _extract_prompt_sections(prompt_text)
    if not sections:
        return "NONE"
    return ", ".join(name for name, _ in sections)


def _format_prompt_section_lengths(prompt_text: object) -> str:
    sections = _extract_prompt_sections(prompt_text)
    if not sections:
        return "NONE"
    return ", ".join(
        f"{name}={len(content)} chars" for name, content in sections
    )


def build_debug_log_text(state: AgentState) -> str:
    """Build a compact markdown debug log for prompt/response inspection."""
    partition_name, model_name = _extract_reproducibility_naming_parts(state)
    lines = [
        f"Partition: {partition_name or 'unknown'}",
        f"Model: {model_name or 'unknown'}",
        f"Run ID: {state.run_id}",
    ]

    for step in state.history or []:
        step_id = step.get("step_id", "NA")
        status = step.get("execution_status", "UNKNOWN")
        action = step.get("action") or "NONE"
        action_input = step.get("action_input") or {}
        prompt_snapshot = str(step.get("prompt_snapshot") or "")
        lines.extend(
            [
                "",
                f"## Step {step_id} | {status}",
                f"Partition: {partition_name or 'unknown'}",
                f"Model: {model_name or 'unknown'}",
                f"Prompt Sections: {_format_prompt_section_names(prompt_snapshot)}",
                f"Section Lengths: {_format_prompt_section_lengths(prompt_snapshot)}",
                f"Action: {action}",
                "Action Input:",
                "```json",
                json.dumps(action_input, ensure_ascii=True, sort_keys=True),
                "```",
                "Prompt:",
                "```text",
                prompt_snapshot,
                "```",
                "Model Response:",
                "```text",
                str(step.get("raw_model_output") or ""),
                "```",
                "Tool Result:",
                "```json",
                _format_debug_observation(step.get("observation")),
                "```",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def write_text(file_path: str | Path, text: str) -> Path:
    """Write plain text using UTF-8."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def save_run_artifacts(
    state: AgentState,
    metrics: dict[str, Any],
    log_dir: str | Path | None = None,
    basename: str | None = None,
) -> dict[str, str]:
    """Persist run log and metrics JSON files and return their paths."""
    runs_dir = ensure_runs_dir(log_dir)
    partition_name, model_name = _extract_reproducibility_naming_parts(state)
    run_basename = basename or build_run_basename(
        partition_name=partition_name,
        model_name=model_name,
        log_dir=runs_dir,
    )

    run_log_path = runs_dir / f"{run_basename}.json"
    metrics_log_path = runs_dir / f"{run_basename}_metrics.json"
    debug_log_path = runs_dir / f"{run_basename}_debug.md"

    run_payload = build_run_log_payload(state, metrics=metrics)
    metrics_payload = {
        "run_id": state.run_id,
        "objective": state.objective,
        "metadata": state.metadata,
        "metrics": metrics,
    }

    write_json(run_log_path, run_payload)
    write_json(metrics_log_path, metrics_payload)
    write_text(debug_log_path, build_debug_log_text(state))

    return {
        "run_log_path": str(run_log_path),
        "metrics_log_path": str(metrics_log_path),
        "debug_log_path": str(debug_log_path),
    }


def load_json(file_path: str | Path) -> dict[str, Any]:
    """Load JSON file into memory."""
    return json.loads(Path(file_path).read_text(encoding="utf-8"))
