"""Second shipped objective: short-answer exact-match questions.

Deliberately unlike ``code-tasks``: no code fences, no sandbox, no hidden
tests - the agent's submitted text must equal the canonical answer. Its
existence proves the engine is objective-agnostic (M11): the same
``EvolutionEngine`` improves both objectives with zero changes.

Tasks are declared inline (data-in-code) to show that an objective needs no
on-disk task packs either - only the ``Objective`` protocol.
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

# (key, question, canonical answer) - the key is the stability point that
# scripts and demos gate ability on.
_QA: list[tuple[str, str, str]] = [
    # train
    ("japan", "What is the capital of Japan?", "Tokyo"),
    ("week", "How many days are in a week?", "7"),
    ("purple", "What color do you get by mixing red and blue?", "purple"),
    ("42", "What is 6 times 7?", "42"),
    # val
    ("mars", "Which planet is known as the Red Planet?", "Mars"),
    ("continents", "How many continents are there?", "7"),
    ("gold", "What is the chemical symbol for gold?", "Au"),
    # canary
    ("2+2", "What is 2 + 2?", "4"),
]

_SPLITS: dict[str, tuple[str, ...]] = {
    "train": ("japan", "week", "purple", "42"),
    "val": ("mars", "continents", "gold"),
    "canary": ("2+2",),
}

_BY_KEY = {k: (q, a) for k, q, a in _QA}

_PROMPT = ("Q: {question}\nAnswer with the exact answer text only - no "
           "explanation, no code block.")


class ExactMatchObjective(Objective):
    """Score 1.0 iff the submitted text equals the canonical answer."""

    def __init__(self) -> None:
        self._suites: dict[Split, TaskSuite] | None = None

    def suites(self) -> dict[Split, TaskSuite]:
        if self._suites is None:
            self._suites = {}
            for split in Split:
                keys = _SPLITS.get(split.value, ())
                tasks = []
                for i, key in enumerate(keys):
                    question, answer = _BY_KEY[key]
                    tasks.append(Task(
                        id=f"{split.value}/{i + 1:02d}", split=split,
                        prompt=_PROMPT.format(question=question),
                        meta={"key": key, "answer": answer}))
                self._suites[split] = TaskSuite(split, tasks)
        return self._suites

    def canaries(self) -> TaskSuite:
        return self.suites()[Split.CANARY]

    def evaluate(self, task: Task, attempt) -> TaskScore:
        expected = task.meta["answer"]
        got = (attempt.result or "").strip()
        if got == expected:
            return TaskScore(task.id, 1.0)
        return TaskScore(task.id, 0.0, f"expected {expected!r}, got {got[:40]!r}")

    def fitness(self, scorebook: ScoreBook) -> float:
        return scorebook.mean()

    def behavior_descriptors(self, scorebook: ScoreBook) -> tuple:
        return (int(scorebook.mean() * 4), 0)
