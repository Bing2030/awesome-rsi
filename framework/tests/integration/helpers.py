"""Shared fixtures for integration tests: a minimal plug-in objective.

TinyObjective doubles as living proof of the Objective seam: the engine runs
it unchanged (the same class powers the M11 task-agnosticism demo).
"""

from rsif.llm.base import extract_code_fence
from rsif.objectives.base import (
    Objective,
    Split,
    Task,
    TaskScore,
    TaskSuite,
)

CORRECT = "```python\ndef double(x):\n    return 2 * x\n```"
WRONG = "```python\ndef double(x):\n    return x\n```"


class TinyObjective(Objective):
    """2 train / 2 val / 1 canary, scored in-process."""

    def __init__(self):
        def mk(split, i):
            return Task(f"{split.value}/{i:02d}", split,
                        "Implement `double(x)` returning 2 * x.",
                        {"tests": "assert double(3) == 6\nassert double(0) == 0\n"})

        self._suites = {
            Split.TRAIN: TaskSuite(Split.TRAIN, [mk(Split.TRAIN, i) for i in (1, 2)]),
            Split.VAL: TaskSuite(Split.VAL, [mk(Split.VAL, i) for i in (1, 2)]),
            Split.CANARY: TaskSuite(Split.CANARY, [mk(Split.CANARY, 1)]),
        }

    def suites(self):
        return self._suites

    def canaries(self):
        return self._suites[Split.CANARY]

    def evaluate(self, task, attempt):
        code = extract_code_fence(attempt.result)
        ns: dict = {}
        try:
            exec(compile(code, "<candidate>", "exec"), ns)  # noqa: S102
            exec(compile(task.meta["tests"], "<tests>", "exec"), ns)  # noqa: S102
        except Exception:  # noqa: BLE001 - any failure scores 0
            return TaskScore(task.id, 0.0, "failed tests")
        return TaskScore(task.id, 1.0)

    def fitness(self, scorebook):
        return scorebook.mean()

    def behavior_descriptors(self, scorebook):
        return (int(scorebook.mean() * 4), 0)
