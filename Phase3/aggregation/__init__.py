"""Phase 3A Aggregation package exports."""

from aggregation.contracts import MAX_UPDATE_FOCUS_CHARS
from aggregation.input_resolver import build_normalized_inputs, build_worker_result_set, load_worker_result_set
from aggregation.runner import run_aggregation

__all__ = [
    "MAX_UPDATE_FOCUS_CHARS",
    "build_normalized_inputs",
    "build_worker_result_set",
    "load_worker_result_set",
    "run_aggregation",
]