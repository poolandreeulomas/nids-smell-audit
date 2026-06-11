"""Strict JSON parsing for Worker step outputs."""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json


def _looks_like_worker_result(payload: dict[str, Any]) -> bool:
    required_keys = {
        "task_id",
        "hypothesis_id",
        "status",
        "findings",
        "evidence_refs",
        "contradictions",
        "limitations",
    }
    return required_keys.issubset(payload.keys())


def parse_worker_step_response(raw_response_text: str) -> dict[str, Any]:
    text = str(raw_response_text or "").strip()
    if not text:
        raise ValueError("Worker response is empty.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        print("[JSON_RECOVERY] attempting repair")
        try:
            repaired_text = repair_json(text)
            payload = json.loads(repaired_text)
            print("[JSON_RECOVERY] repair successful")
        except Exception:
            print("[JSON_RECOVERY] repair failed")
            raise ValueError(f"Worker response is not valid JSON")

    if not isinstance(payload, dict):
        raise ValueError("Worker response must decode to a JSON object.")

    if isinstance(payload.get("worker_step"), dict):
        payload = payload["worker_step"]
    elif isinstance(payload.get("worker_output"), dict):
        payload = payload["worker_output"]

    if _looks_like_worker_result(payload):
        return {
            "decision": "finish",
            "worker_result": payload,
        }

    if isinstance(payload.get("worker_result"), dict) and "decision" not in payload:
        return {
            "decision": "finish",
            "worker_result": payload["worker_result"],
        }

    decision = payload.get("decision")
    if decision not in {"continue", "action", "finish"}:
        raise ValueError("Worker response must include decision='continue', decision='action', or decision='finish'.")

    if decision == "continue":
        if not isinstance(payload.get("reasoning"), str) or not str(payload.get("reasoning") or "").strip():
            raise ValueError("Worker continue responses must include a non-empty 'reasoning' string.")
        return {
            "decision": "continue",
            "reasoning": str(payload.get("reasoning") or "").strip(),
        }

    if decision == "action":
        actions_payload = payload.get("actions")
        if isinstance(actions_payload, list):
            actions = [dict(item) for item in actions_payload if isinstance(item, dict)]
        elif isinstance(payload.get("action"), dict):
            actions = [dict(payload.get("action") or {})]
        else:
            actions = []
        if not actions:
            raise ValueError("Worker action responses must include 'action' or a non-empty 'actions' list.")
        normalized_payload = {
            "decision": "action",
            "actions": actions,
        }
        if isinstance(payload.get("reasoning"), str) and str(payload.get("reasoning") or "").strip():
            normalized_payload["reasoning"] = str(payload.get("reasoning") or "").strip()
        return normalized_payload

    if decision == "finish" and not isinstance(payload.get("worker_result"), dict):
        raise ValueError("Worker finish responses must include a 'worker_result' object.")
    normalized_payload = {
        "decision": "finish",
        "worker_result": payload.get("worker_result"),
    }
    if isinstance(payload.get("reasoning"), str) and str(payload.get("reasoning") or "").strip():
        normalized_payload["reasoning"] = str(payload.get("reasoning") or "").strip()
    return normalized_payload