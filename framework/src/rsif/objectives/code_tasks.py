"""Shipped executable benchmark objective: self-contained Python functions
scored by hidden unit tests run in the sandbox.

The agent's submitted code is combined with a task's hidden test source and
executed; pass fraction is the score. Task packs are pure data under
`objectives/tasks/{train,val,test,canary}/`.
"""

from __future__ import annotations

import json
from pathlib import Path

from rsif.objectives.base import Objective, ScoreBook, Split, Task, TaskScore, TaskSuite
from rsif.llm.base import extract_code_fence


class CodeTasksObjective(Objective):
    def __init__(self, root: Path | None = None, sandbox=None):
        self.root = Path(root) if root else Path(__file__).parent / "tasks"
        self._suites: dict[Split, TaskSuite] | None = None
        self._sandbox = sandbox

    # -- loading ------------------------------------------------------------

    def _load(self) -> dict[Split, TaskSuite]:
        suites: dict[Split, TaskSuite] = {}
        for split in Split:
            d = self.root / split.value
            tasks = []
            if d.is_dir():
                for f in sorted(d.glob("*.json")):
                    data = json.loads(f.read_text(encoding="utf-8"))
                    tasks.append(Task(
                        id=data["id"], split=split, prompt=data["prompt"],
                        meta={k: v for k, v in data.items()
                              if k not in ("id", "prompt")}))
            suites[split] = TaskSuite(split, tasks)
        return suites

    def suites(self) -> dict[Split, TaskSuite]:
        if self._suites is None:
            self._suites = self._load()
        return self._suites

    def canaries(self) -> TaskSuite:
        return self.suites()[Split.CANARY]

    # -- scoring ------------------------------------------------------------

    def evaluate(self, task: Task, attempt) -> TaskScore:
        code = extract_code_fence(attempt.result)
        test_source = task.meta.get("hidden_tests", "")
        if not code or not test_source:
            return TaskScore(task.id, 0.0, "missing code or hidden tests")

        program = f"{code}\n\n# --- hidden tests ---\n{test_source}\n"
        sandbox = self._sandbox
        if sandbox is None:
            from rsif.sandbox.exec import run_python

            sandbox = run_python
        try:
            outcome = sandbox(program)
        except OSError as e:  # sandbox could not even spawn: no verdict exists
            return TaskScore(task.id, 0.0, f"sandbox spawn failure: {e}",
                             infra=True)
        if outcome.ok:
            return TaskScore(task.id, 1.0, "", outcome.wall_s)
        if outcome.timed_out:
            # wall/CPU budget hit: the environment failed to deliver a
            # verdict. Unscored, not an official zero [2609.15364 §4.1].
            return TaskScore(task.id, 0.0, "sandbox timeout", outcome.wall_s,
                             infra=True)
        if outcome.exit_code < 0:
            # death by signal: in this sandbox that is a resource-limit kill
            # (RLIMIT_CPU/AS enforcement), i.e. infrastructure — a Python
            # error exits 1 with a traceback, a signal does not
            return TaskScore(task.id, 0.0,
                             f"killed by signal {-outcome.exit_code} "
                             f"(resource limit)", outcome.wall_s, infra=True)
        return TaskScore(task.id, 0.0, outcome.error_text[:300], outcome.wall_s)

    def behavior_descriptors(self, scorebook: ScoreBook) -> tuple:
        # (pass_band, mean_steps_band) - mean_steps not tracked in v1, so 0
        band = int(scorebook.mean() * 4)  # 0..4
        return (band, 0)
