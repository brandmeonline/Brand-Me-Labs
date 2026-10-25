"""Assistant task runtime (ch.03 §7; W07): research / prepare / buy-within-rules tasks.

This package never imports ``model_planner`` or the Anthropic SDK; ``composition`` does, and only
loads the SDK when a model planner is configured.
"""

from .background import BackgroundRunner, TaskRunner
from .runtime import (AssistantRuntime, AssistantTask, DeterministicPlanner, IdempotencyReuse, Planner,
                      PlannerError, ProposedCall, TaskConstraints, TaskEvent, TaskView)

__all__ = ["AssistantRuntime", "AssistantTask", "BackgroundRunner", "DeterministicPlanner", "IdempotencyReuse",
           "Planner", "PlannerError", "ProposedCall", "TaskConstraints", "TaskEvent", "TaskRunner", "TaskView"]
