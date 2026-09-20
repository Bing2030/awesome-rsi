"""A ~40-line plug-in objective: grade-school arithmetic with carry digits.

Copy this file, change `suites`/`evaluate`/`fitness`/`behavior_descriptors`,
and pass an instance to EvolutionEngine - the engine, store, archive, safety,
and CLI machinery need zero changes (see tests/integration/test_task_agnostic.py).

This objective is deliberately third in a different domain to prove the seam:
- code_tasks: sandbox-executed hidden tests
- exact_match: plain-text exact equality
- arithmetic (here): parse a numeric answer and compare against a target
"""

from __future__ import annotations

from rsif.objectives.base import (
    Objective,
    ScoreBook,
    Split,
    Task,
    TaskScore,
    TaskSuite,
)


def _mk(split: Split, i: int, a: int, b: int) -> Task:
    return Task(
        id=f"{split.value}/{i:02d}", split=split,
        prompt=f"Compute {a} + {b}. Reply with the integer only.",
        meta={"answer": str(a + b)})


class ArithmeticObjective(Objective):
    def __init__(self) -> None:
        train = [("11", "19"), ("5", "7"), ("20", "30"), ("101", "1")]
        val = [("9", "9"), ("13", "27"), ("99", "2")]
        canary = [("1", "1")]

        def suite(split, pairs):
            return TaskSuite(split, [_mk(split, i + 1, int(a), int(b))
                                     for i, (a, b) in enumerate(pairs)])

        self._suites = {
            Split.TRAIN: suite(Split.TRAIN, train),
            Split.VAL: suite(Split.VAL, val),
            Split.CANARY: suite(Split.CANARY, canary),
        }

    def suites(self):
        return self._suites

    def canaries(self):
        return self._suites[Split.CANARY]

    def evaluate(self, task: Task, attempt) -> TaskScore:
        got = (attempt.result or "").strip()
        if got == task.meta["answer"]:
            return TaskScore(task.id, 1.0)
        return TaskScore(task.id, 0.0, f"expected {task.meta['answer']!r}, got {got!r}")

    def fitness(self, scorebook: ScoreBook) -> float:
        return scorebook.mean()

    def behavior_descriptors(self, scorebook: ScoreBook) -> tuple:
        return (int(scorebook.mean() * 4), 0)
