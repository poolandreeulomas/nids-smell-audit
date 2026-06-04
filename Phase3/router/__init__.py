"""Phase 3A Router package exports."""

from router.context_reducer import (
    build_router_context_min,
    build_task_bundle_index,
    collect_known_action_classes,
    project_planner_strategy,
    project_router_context_min,
)
from router.contracts import (
    DEFAULT_MAX_ROUTER_TASKS,
    DEFAULT_MAX_WORKER_RETRIES,
    DEFAULT_MAX_WORKER_STEPS,
    SCHEMA_VERSION,
)
from router.runner import run_router

__all__ = [
    "DEFAULT_MAX_ROUTER_TASKS",
    "DEFAULT_MAX_WORKER_RETRIES",
    "DEFAULT_MAX_WORKER_STEPS",
    "SCHEMA_VERSION",
    "build_router_context_min",
    "build_task_bundle_index",
    "collect_known_action_classes",
    "project_planner_strategy",
    "project_router_context_min",
    "run_router",
]