"""EfficiencyObjective — the fourth objective, and the first cost-aware one.

A standalone project proving the harness-efficiency seam: correctness is the
primary signal, but every token the harness spends on a task — the injected
context (system prompt + memory) *and* the output — folds into the task's
score,

    score = correctness - LAMBDA * min(1, tokens / TOKEN_BUDGET)
    tokens = input_chars / CHARS_PER_TOKEN + output_tokens

so `fitness = mean(score)` is a *quality-first scalar floor*. This is rsif's
grounding of SoL-Pi [2609.20519] (auto-research under a token-efficiency
objective gated by a predeclared capability floor): the floor is structural,
not a separate check. Because cost is folded into the per-task score, the
existing acceptance gates enforce it unchanged — the val threshold (0.02) and
the M13 paired net-gain floor. A candidate that answers correctly in fewer
tokens raises *every* task's score (clearing the paired floor on a pure
efficiency gain); a candidate that spends fewer tokens but answers *wrong*
still scores <= -LAMBDA*cost, below any correct answer, and is rejected.

The same objective drives the context policy (3b): a POLICY artifact bounds
the injected memory, so a smaller bound lowers `input_chars` and raises the
score — the same scalar floor rewards context compaction as readily as output
concision.

The task pack is an echo task (output the target after an ``ANSWER:``
marker). It is deliberately trivial so that correctness and token cost are
the only things that vary — the exact isolated signal an efficiency objective
needs.
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

_LAMBDA = 0.1
_TOKEN_BUDGET = 500  # tokens; a correct answer costing >= this scores 1 - LAMBDA
_CHARS_PER_TOKEN = 4
_MARKER = "ANSWER:"

# (key, target). Each target is a short echo string the agent must reproduce.
_TASKS: list[tuple[str, str]] = [
    # -- train (4): candidate selection ---------------------------------------
    ("train/01", "42"),
    ("train/02", "3.14"),
    ("train/03", "red"),
    ("train/04", "true"),
    # -- val (3): held-out acceptance gate ------------------------------------
    ("val/01", "hello"),
    ("val/02", "0"),
    ("val/03", "blue"),
    # -- canary (2): trivial, must never regress ------------------------------
    ("canary/01", "yes"),
    ("canary/02", "no"),
    # -- test (2): sealed until rsif report -----------------------------------
    ("test/01", "left"),
    ("test/02", "up"),
]

_BY_SPLIT: dict[str, list[tuple[str, str]]] = {
    "train": [t for t in _TASKS if t[0].startswith("train/")],
    "val": [t for t in _TASKS if t[0].startswith("val/")],
    "canary": [t for t in _TASKS if t[0].startswith("canary/")],
    "test": [t for t in _TASKS if t[0].startswith("test/")],
}


def _prompt(key: str, target: str) -> str:
    return (
        f"Task {key}: output the exact string {target!r} after the marker "
        f"`{_MARKER}` on its own line. Reply with nothing else."
    )


def extract_answer(text: str) -> str:
    """Pull the echo out of an answer: the text after the LAST ``ANSWER:``
    marker; fall back to the last non-empty line; strip wrapping quotes."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    answer = ""
    for ln in reversed(lines):
        if _MARKER in ln:
            answer = ln.split(_MARKER, 1)[1].strip()
            break
    else:
        answer = lines[-1].strip() if lines else ""
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in "'\"":
        answer = answer[1:-1]
    return answer


class EfficiencyObjective(Objective):
    """Per-task score = correctness - LAMBDA * min(1, tokens / budget)."""

    def __init__(self):
        self._suites: dict[Split, TaskSuite] | None = None

    def suites(self) -> dict[Split, TaskSuite]:
        if self._suites is None:
            self._suites = {}
            for split in Split:
                tasks = [
                    Task(id=key, split=split,
                         prompt=_prompt(key, target),
                         meta={"target": target})
                    for key, target in _BY_SPLIT.get(split.value, [])
                ]
                self._suites[split] = TaskSuite(split, tasks)
        return self._suites

    def canaries(self) -> TaskSuite:
        return self.suites()[Split.CANARY]

    def evaluate(self, task: Task, attempt) -> TaskScore:
        answer = extract_answer(attempt.result or "")
        correct = answer == task.meta["target"]
        input_tokens = getattr(attempt, "input_chars", 0) // _CHARS_PER_TOKEN
        total = input_tokens + attempt.usage.out_tokens
        cost = min(1.0, total / _TOKEN_BUDGET)
        score = (1.0 if correct else 0.0) - _LAMBDA * cost
        detail = "" if correct else f"expected {task.meta['target']!r}, got {answer!r}"
        return TaskScore(task.id, score, detail, attempt.wall_s)

    def fitness(self, scorebook: ScoreBook) -> float:
        return scorebook.mean()

    def behavior_descriptors(self, scorebook: ScoreBook) -> tuple:
        return (round(scorebook.mean(), 2),)
