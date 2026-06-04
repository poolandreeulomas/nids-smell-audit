"""Phase 3A State Manager package exports."""

from state_manager.contracts import MAX_UPDATE_FOCUS_CHARS
from state_manager.runner import run_state_manager

__all__ = [
    "MAX_UPDATE_FOCUS_CHARS",
    "run_state_manager",
]