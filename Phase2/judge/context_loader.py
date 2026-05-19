"""Load compact Judge context for CICIDS2017 partition names."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re


_CONTEXT_DIR = Path(__file__).resolve().parent / "context" / "cicids2017"
_SECTION_SPLIT_RE = re.compile(r"\n\s*\n+")
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_PRIORITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ddos", ("ddos", "dos")),
    ("portscan", ("portscan",)),
    ("web", ("webattacks", "webattack", "xss", "sqli")),
    ("infiltration", ("infiltration",)),
    ("bruteforce", ("ftp", "ssh", "bruteforce")),
    ("benign", ("monday", "benign")),
)


@lru_cache(maxsize=None)
def _read_context_file(name: str) -> str:
    path = _CONTEXT_DIR / f"{name}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _normalize_partition_tokens(partition_name: str) -> tuple[str, ...]:
    raw_name = Path(str(partition_name or "").strip()).name
    normalized_name = Path(raw_name).stem.lower()
    base_tokens = [
        token for token in _TOKEN_SPLIT_RE.split(normalized_name) if token
    ]
    combined_tokens = list(base_tokens)
    for index in range(len(base_tokens) - 1):
        combined_tokens.append(base_tokens[index] + base_tokens[index + 1])
    return tuple(dict.fromkeys(combined_tokens))


def resolve_judge_partition_phenomenon(partition_name: str) -> str | None:
    tokens = set(_normalize_partition_tokens(partition_name))
    for phenomenon_name, candidate_tokens in _TOKEN_PRIORITY:
        if any(token in tokens for token in candidate_tokens):
            return phenomenon_name
    return None


def _select_context_name(partition_name: str) -> str | None:
    phenomenon_name = resolve_judge_partition_phenomenon(partition_name)
    if phenomenon_name and _read_context_file(phenomenon_name):
        return phenomenon_name
    if _read_context_file("generic_network_traffic"):
        return "generic_network_traffic"
    return None


def _split_context_sections(text: str) -> tuple[str, str, str]:
    paragraphs = [
        paragraph.strip()
        for paragraph in _SECTION_SPLIT_RE.split(text.strip())
        if paragraph.strip()
    ]
    if not paragraphs:
        return "", "", ""
    if len(paragraphs) == 1:
        return paragraphs[0], "", ""
    if len(paragraphs) == 2:
        return paragraphs[0], paragraphs[1], ""
    if len(paragraphs) == 3:
        return paragraphs[0], paragraphs[1], paragraphs[2]
    return paragraphs[0], paragraphs[1], "\n\n".join(paragraphs[2:])


def get_judge_context_sections(partition_name: str) -> tuple[str, str, str]:
    global_sections = _split_context_sections(_read_context_file("global"))
    selected_name = _select_context_name(partition_name)
    selected_sections = _split_context_sections(
        _read_context_file(selected_name) if selected_name else ""
    )

    merged_sections: list[str] = []
    for global_section, selected_section in zip(global_sections, selected_sections):
        merged_sections.append(
            "\n\n".join(
                part for part in (global_section, selected_section) if part
            )
        )
    return tuple(merged_sections)


def get_judge_partition_context(partition_name: str) -> str:
    global_text = _read_context_file("global")
    selected_name = _select_context_name(partition_name)
    selected_text = _read_context_file(selected_name) if selected_name else ""
    return "\n\n".join(part for part in (global_text, selected_text) if part)
