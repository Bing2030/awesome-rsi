"""Objective protocol: task-agnostic fitness.

The single seam that makes the framework task-agnostic. A user supplies any
`Objective` and the engine improves against it with zero engine changes.

Split discipline is the overfitting guard: train selects candidates, val
accepts [SkillOpt 2605.23904], test is sealed until `rsif report` [model
collapse 2510.16657], canaries must never regress [misevolution 2509.26354].
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class Split(str, Enum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"
    CANARY = "canary"


@dataclass(frozen=True)
class Task:
    id: str
    split: Split
    prompt: str
    meta: dict = field(default_factory=dict)


@dataclass
class TaskScore:
    task_id: str
    score: float  # 0..1
    detail: str = ""
    wall_s: float = 0.0
    # Infrastructure failure (sandbox timeout / spawn failure / resource-kill):
    # the environment never delivered a verdict, so the task is *unscored*,
    # not failed. Gates and means must skip it rather than read it as 0.0
    # [RSIAgent 2609.15364: "an infrastructure failure is unscored; it is not
    # an official zero"].
    infra: bool = False


@dataclass
class TaskSuite:
    split: Split
    tasks: list[Task] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.tasks)

    def sample(self, n: int, rng) -> "TaskSuite":
        tasks = self.tasks if len(self.tasks) <= n else rng.sample(self.tasks, n)
        return TaskSuite(self.split, list(tasks))


@dataclass
class ScoreBook:
    scores: list[TaskScore] = field(default_factory=list)

    @property
    def scored(self) -> list[TaskScore]:
        """Tasks with a real verdict — infra failures are unscored, not 0.0."""
        return [s for s in self.scores if not s.infra]

    @property
    def n_infra(self) -> int:
        return sum(1 for s in self.scores if s.infra)

    @property
    def n_scored(self) -> int:
        return len(self.scores) - self.n_infra

    def mean(self) -> float:
        # infra entries carry no verdict: they leave the mean instead of
        # dragging it toward zero (n_scored == 0 means "no evidence", which
        # callers must treat as unscored, never as a behavioral 0.0)
        s = self.scored
        if not s:
            return 0.0
        return sum(x.score for x in s) / len(s)

    def add(self, score: TaskScore) -> None:
        self.scores.append(score)

    def to_dict(self) -> dict:
        return {"mean": self.mean(), "n_infra": self.n_infra, "scores": [
            {"task_id": s.task_id, "score": s.score, "detail": s.detail,
             "infra": s.infra}
            for s in self.scores]}


def bootstrap_ci(values: list[float], n_resample: int = 1000, rng=None) -> tuple[float, float]:
    """95% bootstrap CI of the mean. Guards improvement claims built on a
    couple of lucky tasks."""
    import random

    rng = rng or random.Random(0)
    if not values:
        return (0.0, 0.0)
    means = []
    m = len(values)
    for _ in range(n_resample):
        sample = [values[rng.randrange(m)] for _ in range(m)]
        means.append(sum(sample) / m)
    means.sort()
    lo = means[int(0.025 * n_resample)]
    hi = means[int(0.975 * n_resample)]
    return (lo, hi)


class Objective(Protocol):
    """The fitness function the engine optimizes."""

    def suites(self) -> dict[Split, TaskSuite]: ...

    def evaluate(self, task: Task, attempt) -> TaskScore: ...

    def fitness(self, scorebook: ScoreBook) -> float:
        return scorebook.mean()

    def behavior_descriptors(self, scorebook: ScoreBook) -> tuple:
        """Low-dim niche key for the MAP-Elites archive [1504.04909]."""
        return (round(scorebook.mean(), 2),)

    def canaries(self) -> TaskSuite:
        return TaskSuite(Split.CANARY)
