"""Pluggable objectives: the task-agnostic fitness interface."""

from rsif.config import RunConfig
from rsif.objectives.base import (
    Objective,
    ScoreBook,
    Split,
    Task,
    TaskScore,
    TaskSuite,
)

__all__ = [
    "Objective",
    "ScoreBook",
    "Split",
    "Task",
    "TaskScore",
    "TaskSuite",
    "objective_from_config",
]


def objective_from_config(cfg: RunConfig) -> Objective:
    """Instantiate the configured objective.

    The seam every task-agnostic claim rests on: the engine never imports a
    concrete objective, it receives one built here (or hand-constructed in
    tests / examples/custom_objective.py).
    """
    if cfg.objective == "code-tasks":
        from rsif.objectives.code_tasks import CodeTasksObjective

        return CodeTasksObjective()
    if cfg.objective == "exact-match":
        from rsif.objectives.exact_match import ExactMatchObjective

        return ExactMatchObjective()
    raise ValueError(f"unknown objective: {cfg.objective!r}")
