"""State schema scaffold for MVP run state."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Minimal state container for the MVP loop."""

    run_id: str
    objective: str
    current_step: int = 0
    max_steps: int = 5
    available_features: list[str] = field(default_factory=list)
    analyzed_features: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    promising_features: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return asdict(self)
