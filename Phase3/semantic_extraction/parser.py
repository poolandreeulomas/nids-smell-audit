"""Strict parser for Semantic Extraction model output."""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json


TOP_LEVEL_FIELDS = {
    "substrate_id",
    "batch_id",
    "compressed_regions",
    "preserved_weak_signals",
    "contradictions",
    "unresolved_tensions",
}


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def parse_semantic_extraction_response(response_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(response_text))
    except json.JSONDecodeError:
        print("[JSON_RECOVERY] attempting repair")
        text = _strip_code_fences(response_text)
        try:
            repaired_text = repair_json(text)
            payload = json.loads(repaired_text)
            print("[JSON_RECOVERY] repair successful")
        except Exception:
            print("[JSON_RECOVERY] repair failed")

            print("\n" + "=" * 80)
            print("SEMANTIC EXTRACTION JSON PARSE FAILURE")
            print("=" * 80)
            import json as _json
            try:
                _json.loads(text)
            except _json.JSONDecodeError as exc2:
                print(f"Message : {exc2.msg}")
                print(f"Position: {exc2.pos}")
                print(f"Line    : {exc2.lineno}")
                print(f"Column  : {exc2.colno}")
                print()
                print("Context around failure:")
                start2 = max(0, exc2.pos - 200)
                end2 = min(len(text), exc2.pos + 200)
                print(text[start2:end2])
            print("=" * 80 + "\n")

            raise ValueError("semantic extraction response is not valid JSON")

    if not isinstance(payload, dict):
        raise ValueError("semantic extraction response must be a JSON object")

    if set(payload.keys()) == {"semantic_substrate"}:
        payload = payload["semantic_substrate"]

    if not isinstance(payload, dict):
        raise ValueError("semantic_substrate must be a JSON object")

    if set(payload.keys()) != TOP_LEVEL_FIELDS:
        raise ValueError(
            "semantic extraction response must contain exactly substrate_id, batch_id, compressed_regions, preserved_weak_signals, contradictions, unresolved_tensions"
        )

    return payload