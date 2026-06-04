"""State schema scaffold for MVP run state with Phase 2 extensions.

This module adds a lightweight `EvidenceBlock` dataclass and extends
`AgentState` additively to store evidence and contradiction memory.
Only the schema is changed here; runtime behavior remains unchanged.
"""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any, Dict, List


def _ensure_json_primitive(obj: Any) -> Any:
    """Recursively coerce common non-JSON primitives to JSON-friendly types.

    - Convert numpy scalar types to native Python scalars when numpy is available.
    - Convert bytes to UTF-8 strings.
    - Recurse into lists/tuples/dicts.
    - Fallback to str() for unknown objects.
    """
    # Local import to avoid hard dependency at module import time.
    try:
        import numpy as _np
    except Exception:
        _np = None

    # Primitives
    if obj is None:
        return None
    if isinstance(obj, (str, bool)):
        return obj

    if _np is not None:
        # numpy scalar types
        if isinstance(obj, _np.generic):
            try:
                return obj.item()
            except Exception:
                # Fallback to Python conversion
                if isinstance(obj, _np.integer):
                    return int(obj)
                if isinstance(obj, _np.floating):
                    return float(obj)
                if isinstance(obj, _np.bool_):
                    return bool(obj)

    if isinstance(obj, (int, float)):
        return obj

    if isinstance(obj, (list, tuple)):
        return [_ensure_json_primitive(v) for v in obj]

    if isinstance(obj, dict):
        return {str(k): _ensure_json_primitive(v) for k, v in obj.items()}

    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except Exception:
            return str(obj)

    # Last resort: try to coerce via __iter__ or str()
    try:
        return str(obj)
    except Exception:
        return obj


def _string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []

    normalized: List[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class EvidenceBlock:
    """Structured evidence unit for Phase 2.

    Fields are intentionally permissive and defaulted so that older run
    payloads can be loaded without breaking.
    """

    feature: str = ""
    signals: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    support: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain JSON-serializable dict representation.

        Use `dataclasses.asdict` to preserve simple nesting. Defensive
        numeric coercion is applied to ensure JSON serializability.
        """
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "EvidenceBlock":
        """Reconstruct an EvidenceBlock from a dict, tolerating missing keys.

        This is intentionally lenient to preserve backward compatibility
        with older run JSON that will not contain these fields.
        """
        if not payload:
            return cls()

        return cls(
            feature=payload.get("feature", ""),
            signals=list(payload.get("signals", []) or []),
            metrics=dict(payload.get("metrics", {}) or {}),
            support=dict(payload.get("support", {}) or {}),
            provenance=dict(payload.get("provenance", {}) or {}),
            status=payload.get("status", "active") or "active",
        )


@dataclass
class InterpretiveHypothesis:
    """Canonical planner-facing hypothesis state for one batch."""

    hypothesis_id: str
    summary: str = ""
    status: str = "unresolved"
    evidence_refs: List[str] = field(default_factory=list)
    open_gaps: List[str] = field(default_factory=list)
    preserved_contradictions: List[str] = field(default_factory=list)
    merged_findings: List[str] = field(default_factory=list)
    update_focus: str = ""
    last_updated_round: str = ""
    revision_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(
        cls,
        payload: Dict[str, Any] | None,
    ) -> "InterpretiveHypothesis":
        if not payload:
            return cls(hypothesis_id="")

        return cls(
            hypothesis_id=str(payload.get("hypothesis_id", "") or ""),
            summary=str(payload.get("summary", "") or ""),
            status=str(payload.get("status", "unresolved") or "unresolved"),
            evidence_refs=_string_list(payload.get("evidence_refs")),
            open_gaps=_string_list(payload.get("open_gaps")),
            preserved_contradictions=_string_list(
                payload.get("preserved_contradictions")
            ),
            merged_findings=_string_list(payload.get("merged_findings")),
            update_focus=str(payload.get("update_focus", "") or ""),
            last_updated_round=str(payload.get("last_updated_round", "") or ""),
            revision_count=_int_value(payload.get("revision_count"), default=0),
        )


@dataclass
class StateRevisionRecord:
    """Append-only revision metadata for canonical batch-state commits."""

    revision_type: str = "state_update"
    state_version: int = 0
    round_id: str = ""
    hypothesis_id: str = ""
    applied_updates: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(
        cls,
        payload: Dict[str, Any] | None,
    ) -> "StateRevisionRecord":
        raw = payload or {}
        updates = raw.get("applied_updates")
        normalized_updates: List[Dict[str, Any]] = []
        if isinstance(updates, list):
            for item in updates:
                if isinstance(item, dict):
                    normalized_updates.append(dict(item))

        return cls(
            revision_type=str(raw.get("revision_type", "state_update") or "state_update"),
            state_version=_int_value(raw.get("state_version"), default=0),
            round_id=str(raw.get("round_id", "") or ""),
            hypothesis_id=str(raw.get("hypothesis_id", "") or ""),
            applied_updates=normalized_updates,
            timestamp=str(raw.get("timestamp", "") or ""),
        )


@dataclass
class CanonicalBatchState:
    """Two-layer canonical batch state for Phase 3A."""

    batch_id: str
    state_version: int = 1
    structural_substrate: Dict[str, Any] = field(default_factory=dict)
    interpretive_hypotheses: List[InterpretiveHypothesis] = field(default_factory=list)
    revision_log: List[StateRevisionRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "CanonicalBatchState":
        if not payload:
            raise ValueError(
                "payload must be a non-empty dict to build CanonicalBatchState"
            )

        raw_hypotheses = payload.get("interpretive_hypotheses") or []
        if isinstance(raw_hypotheses, dict):
            raw_hypotheses = list(raw_hypotheses.values())

        hypotheses: List[InterpretiveHypothesis] = []
        if isinstance(raw_hypotheses, list):
            for item in raw_hypotheses:
                if isinstance(item, InterpretiveHypothesis):
                    hypotheses.append(item)
                elif isinstance(item, dict):
                    hypotheses.append(InterpretiveHypothesis.from_dict(item))

        raw_revision_log = payload.get("revision_log") or []
        revisions: List[StateRevisionRecord] = []
        if isinstance(raw_revision_log, list):
            for item in raw_revision_log:
                if isinstance(item, StateRevisionRecord):
                    revisions.append(item)
                elif isinstance(item, dict):
                    revisions.append(StateRevisionRecord.from_dict(item))

        return cls(
            batch_id=str(payload.get("batch_id", "") or ""),
            state_version=_int_value(payload.get("state_version"), default=1),
            structural_substrate=dict(payload.get("structural_substrate", {}) or {}),
            interpretive_hypotheses=hypotheses,
            revision_log=revisions,
        )


@dataclass
class AgentState:
    """Minimal state container for the MVP loop, extended for Phase 2.

    New fields are additive and defaulted to preserve compatibility with
    existing persisted run payloads. Other modules should not require
    any changes to continue functioning.
    """

    run_id: str
    objective: str
    current_step: int = 0
    max_steps: int = 5
    available_features: List[str] = field(default_factory=list)
    analyzed_features: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    promising_features: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Phase 2 additions (additive; do not remove existing fields)
    evidence_by_feature: Dict[str, List[EvidenceBlock]] = field(
        default_factory=dict)
    contradiction_memory: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""

        # `dataclasses.asdict` will recursively convert dataclass instances
        # (including `EvidenceBlock`) into plain dicts. This keeps the
        # serialized structure compatible with existing saved runs while
        # adding the new fields as plain JSON objects.
        return _ensure_json_primitive(asdict(self))

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "AgentState":
        """Reconstruct an AgentState from a persisted run payload.

        This factory is tolerant of older payloads that do not include the
        Phase 2 fields and will default them sensibly.
        """
        if not payload:
            raise ValueError(
                "payload must be a non-empty dict to build AgentState")

        run_id = payload.get("run_id", "run_from_payload")
        objective = payload.get("objective", "")
        current_step = int(payload.get("current_step", 0) or 0)
        max_steps = int(payload.get("max_steps", 5) or 5)
        available_features = list(payload.get("available_features", []) or [])
        analyzed_features = dict(payload.get("analyzed_features", {}) or {})
        history = list(payload.get("history", []) or [])
        promising_features = list(payload.get("promising_features", []) or [])
        errors = list(payload.get("errors", []) or [])
        metadata = dict(payload.get("metadata", {}) or {})

        # Reconstruct evidence_by_feature if present; tolerate older payloads
        evidence_map = payload.get("evidence_by_feature", {}) or {}
        reconstructed: Dict[str, List[EvidenceBlock]] = {}
        for feat, blocks in evidence_map.items():
            if not blocks:
                reconstructed[str(feat)] = []
                continue
            lst: List[EvidenceBlock] = []
            for b in blocks:
                if isinstance(b, EvidenceBlock):
                    lst.append(b)
                elif isinstance(b, dict):
                    lst.append(EvidenceBlock.from_dict(b))
                else:
                    # Unknown block representation; attempt to coerce to dict
                    try:
                        lst.append(EvidenceBlock.from_dict(dict(b)))
                    except Exception:
                        continue
            reconstructed[str(feat)] = lst

        contradiction_memory = list(
            payload.get("contradiction_memory", []) or [])

        return cls(
            run_id=run_id,
            objective=objective,
            current_step=current_step,
            max_steps=max_steps,
            available_features=available_features,
            analyzed_features=analyzed_features,
            history=history,
            promising_features=promising_features,
            errors=errors,
            metadata=metadata,
            evidence_by_feature=reconstructed,
            contradiction_memory=contradiction_memory,
        )
