"""RegexObjective — the third real objective, built as a standalone project.

A deliberately different evaluation surface from the two shipped built-ins:
the agent must PRODUCE a regular expression that matches every positive
example and no negative example. Grading is execution-grounded (the pattern
is compiled and tested inside the sandbox) and fully deterministic.

Why this project exists (see docs/investigation.md): it exercises the whole
framework through the public seams only — a custom `Objective`, the
`EvolutionEngine` API, and a real provider through the gateway — with zero
changes to the engine. The only core edit it required was relaxing
`RunConfig`'s closed objective-name set, which contradicted the
task-agnosticism the engine itself guarantees (recorded in the decision log).
"""

from __future__ import annotations

import json

from rsif.llm.base import extract_code_fence
from rsif.objectives.base import (
    Objective,
    ScoreBook,
    Split,
    Task,
    TaskScore,
    TaskSuite,
)

# (key, positives, negatives, reference pattern). The reference is NOT used
# for scoring - grading is purely match/no-match on the examples - it exists
# so offline scripts and reviewers can sanity-check solvability.
_TASKS: list[tuple[str, list[str], list[str], str]] = [
    # -- train (6) ------------------------------------------------------------
    ("train/01", ["123-4567", "555-0000"], ["12-4567", "1234567"],
     r"\d{3}-\d{4}"),
    ("train/02", ["2024-01-15", "1999-12-31"], ["15-01-2024", "2024/01/15"],
     r"\d{4}-\d{2}-\d{2}"),
    ("train/03", ["color", "colour"], ["colr", "colouur"], r"colou?r"),
    ("train/04", ["user@example.com", "a@b.co"],
     ["userexample.com", "@nope.com"], r"[\w.]+@[\w.]+"),
    ("train/05", ["#FF00AA", "#abc"], ["FF00AA", "#GGH"],
     r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?"),
    ("train/06", ["cat", "cot", "cut"], ["cit", "caat"], r"c[aou]t"),
    # -- val (5): held-out acceptance gate ------------------------------------
    ("val/01", ["1,234", "12,345,678"], ["1234", "1,23"], r"\d{1,3}(,\d{3})+"),
    ("val/02", ["Mr. Smith", "Ms. Jones"], ["Mr Smith", "Smith"],
     r"M(r|s)\. \w+"),
    ("val/03", ["file.py", "data.json"], ["filepy", ".py"], r"\w+\.(py|json)"),
    ("val/04", ["It's", "don't"], ["Its", "dont"], r"\w+'\w"),
    ("val/05", ["12:30", "23:59"], ["25:00", "12:5"],
     r"([01]\d|2[0-3]):[0-5]\d"),
    # -- canary (2): trivial, must never regress ------------------------------
    ("canary/01", ["aaa", "aa"], ["b"], r"a+"),
    ("canary/02", ["2024", "1999"], ["24", "20a4"], r"\d{4}"),
    # -- test (4): sealed until rsif report / end-of-run summary --------------
    ("test/01", ["abc123", "xyz789"], ["abc", "123"], r"[a-z]{3}\d{3}"),
    ("test/02", ["foo_bar", "a_b"], ["foo-bar", "_ab"], r"\w+_\w+"),
    ("test/03", ["3.14", "0.5"], ["3,14", "3."], r"\d+\.\d+"),
    ("test/04", ["#FFF", "#123456"], ["FFF", "#12"],
     r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?"),
]

_BY_SPLIT: dict[str, list[tuple[str, list[str], list[str], str]]] = {
    "train": [t for t in _TASKS if t[0].startswith("train/")],
    "val": [t for t in _TASKS if t[0].startswith("val/")],
    "canary": [t for t in _TASKS if t[0].startswith("canary/")],
    "test": [t for t in _TASKS if t[0].startswith("test/")],
}


def _prompt(key: str, positives: list[str], negatives: list[str]) -> str:
    pos = json.dumps(positives)
    neg = json.dumps(negatives)
    return (
        f"Task {key}: produce ONE Python regular expression (a bare pattern\n"
        f"string, no flags, no delimiters) that matches ALL of {pos} and\n"
        f"NONE of {neg}. Answer with the pattern alone."
    )


def extract_pattern(text: str) -> str:
    """Pull the pattern out of the agent's answer: prefer a fenced block,
    else the first non-empty line; strip wrapping quotes."""
    candidate = extract_code_fence(text)
    if candidate == text.strip():
        # no fence: first non-empty line
        for line in text.splitlines():
            if line.strip():
                candidate = line.strip()
                break
    candidate = candidate.strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "'\"":
        candidate = candidate[1:-1]
    return candidate


class RegexObjective(Objective):
    """Score 1.0 iff the submitted pattern matches all positives and no
    negatives, verified by executing `re` in the sandbox."""

    def __init__(self, sandbox=None):
        self._suites: dict[Split, TaskSuite] | None = None
        self._sandbox = sandbox

    def suites(self) -> dict[Split, TaskSuite]:
        if self._suites is None:
            self._suites = {}
            for split in Split:
                tasks = [
                    Task(id=key, split=split,
                         prompt=_prompt(key, pos, neg),
                         meta={"positives": pos, "negatives": neg})
                    for key, pos, neg, _ref in _BY_SPLIT.get(split.value, [])
                ]
                self._suites[split] = TaskSuite(split, tasks)
        return self._suites

    def canaries(self) -> TaskSuite:
        return self.suites()[Split.CANARY]

    def evaluate(self, task: Task, attempt) -> TaskScore:
        pattern = extract_pattern(attempt.result or "")
        if not pattern:
            return TaskScore(task.id, 0.0, "no pattern found in answer")
        program = (
            "import re\n"
            f"rx = re.compile({pattern!r})\n"
            f"pos = {task.meta['positives']!r}\n"
            f"neg = {task.meta['negatives']!r}\n"
            "for s in pos:\n"
            "    assert rx.search(s), ('missed', s)\n"
            "for s in neg:\n"
            "    assert not rx.search(s), ('hit', s)\n"
        )
        sandbox = self._sandbox
        if sandbox is None:
            from rsif.sandbox.exec import run_python

            sandbox = run_python
        outcome = sandbox(program)
        if outcome.ok:
            return TaskScore(task.id, 1.0, "", outcome.wall_s)
        return TaskScore(task.id, 0.0, outcome.error_text[:300], outcome.wall_s)

    def fitness(self, scorebook: ScoreBook) -> float:
        return scorebook.mean()

    def behavior_descriptors(self, scorebook: ScoreBook) -> tuple:
        return (int(scorebook.mean() * 4), 0)
