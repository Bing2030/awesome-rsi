# Component guide — objectives: the task-agnostic seam

*The engine optimizes whatever you hand it. Four real objectives have run
through it with zero engine changes.*

Files: `src/rsif/objectives/base.py` (the protocol),
`code_tasks.py`, `exact_match.py` (built-ins); `examples/custom_objective.py`;
`projects/regex_agent/`, `projects/harness_efficiency/` (real projects —
see their `README.md`). Verified by `tests/integration/test_task_agnostic.py`,
`test_regex_project.py`, `test_harness_efficiency.py`.

## The protocol

```python
class Objective(Protocol):
    def suites(self) -> dict[Split, TaskSuite]: ...          # the tasks
    def evaluate(self, task: Task, attempt) -> TaskScore: ... # the grader
    def fitness(self, scorebook: ScoreBook) -> float: ...     # aggregate
    def behavior_descriptors(self, scorebook) -> tuple: ...   # niche key
    def canaries(self) -> TaskSuite: ...                      # never-regress set
```

- **`Task`** — `id`, `split`, `prompt`, free-form `meta` (targets, expected
  code, anything your grader needs).
- **`TaskSuite`** — split + tasks; `sample(n, rng)` powers the cascade
  screen.
- **`TaskScore`** — `task_id`, `score` (0..1 convention), `detail`, `wall_s`.
- **`ScoreBook`** — list of scores + `mean()`.
- **`Split`** — `train | val | test | canary`. **Train selects, val
  accepts, test is sealed until `rsif report`, canaries never regress.**

`evaluate` receives the runtime's `Attempt` — so an objective can grade on
anything the attempt carries: result text (`exact-match`), executed code
(`code-tasks` runs hidden tests in the sandbox), regex behavior
(`regex_agent` compiles and executes the pattern), or *cost*
(`harness_efficiency` reads `usage` and `input_chars`).

The engine never imports a concrete objective — a structural guard test
asserts the engine source names none. `objectives/objective_from_config`
dispatches the built-ins; any other non-empty `RunConfig.objective` name is
yours (the M14 change that made the config seam as open as the engine one).

## The four objectives

| Objective | Tasks | Grading | Proven by |
|---|---|---|---|
| `code-tasks` (built-in) | 21 generated Python function tasks | extract ```python fence, exec hidden unit tests in the sandbox | flagship golden: val 0.40 → 0.80 |
| `exact-match` (built-in) | Q&A pairs | plain-text equality — no fence, no sandbox | 1/3 → 1.0 through the identical engine |
| `RegexObjective` (`projects/regex_agent/`) | pattern tasks (positives/negatives) | compile & execute `re` in the sandbox against examples | offline: val 0.2 → 0.4 → 1.0; **live gateway run** (see below) |
| `EfficiencyObjective` (`projects/harness_efficiency/`) | echo tasks | correctness **minus token cost** — see [efficiency.md](efficiency.md) | concise-correct accepted over verbose-correct; concise-wrong screened |

Each objective also supplies `behavior_descriptors` — the MAP-Elites niche
key. Keep it low-dimensional and *not* a copy of fitness (a documented
limitation, L3: the default `(round(mean, 2),)` partially encodes fitness).
`code-tasks` uses a pass-band; the projects use simple means.

## Writing your own objective

`examples/custom_objective.py` is a complete arithmetic objective in ~30
lines. The recipe:

1. Define tasks with prompts a model can actually answer, and put the
   grading data in `task.meta`.
2. Implement `evaluate` — return a `TaskScore` in 0..1 (the gates' θ and ε
   assume that scale).
3. Keep the output contract trivial to satisfy: whatever your extractor
   expects (a fence, a marker line, bare text), make sure *correct behavior
   by a real model produces it* (see the live-run lesson below).
4. Splits: enough val tasks for the paired net-gain floor to mean
   something (≥ 5–10), a couple of trivial canaries, a sealed test split.
5. Write a **solvability invariant** test: your reference answers must pass
   your own grader. This has caught two real task-design bugs
   (`colou?r` matching inside "colorr"; a hidden test asserting 3 words).

```python
class MyObjective:
    def suites(self): ...           # build TaskSuites per split once
    def evaluate(self, task, attempt):
        ok = attempt.result.strip() == task.meta["answer"]
        return TaskScore(task.id, 1.0 if ok else 0.0)
    def fitness(self, book): return book.mean()
    def behavior_descriptors(self, book): return (round(book.mean(), 2),)
    def canaries(self): return self.suites()[Split.CANARY]
```

Run it offline first with a `ScriptedProvider` (deterministic), then live
through `projects/*/run.py`-style runners with hard budgets and the
response cache.

## Evidence that the seam is real

- **Structural**: the engine-source guard; the config seam accepts any
  objective name (M14 fix).
- **Behavioral**: three evaluation surfaces (code fences → bare text →
  integer strings → regexes → echo markers) over the same engine, gates,
  archive, safety stack.
- **Live (regex_agent, glm-5.3-flash via gateway, 29 calls, exit 0)**:
  baseline val 0.6 — a genuine held-out gap; both real-improver proposals
  were plausible-sounding prompt refinements that *regressed train* and
  were **correctly rejected at the cascade screen**; the g1 reflection
  visibly shaped the g2 proposal; no ratchet (active stayed at seed);
  sealed test 0.5 on the archive best. Honest headline: the machinery is
  validated; improvement was not found within 2 proposals.
- The live run also surfaced a real **contract hazard**: prompts that tell
  the model to "verify before answering" make it emit prose first, breaking
  a first-line extractor — the gates kept that regression from deploying,
  and the lesson is recorded for extractor design.

## Design notes

- `bootstrap_ci(values)` (base.py) gives a seeded 95% CI of the mean —
  `rsif report` uses it on the sealed test split so a lucky task can't
  carry a claim.
- Objectives are constructed by you (or `objective_from_config`) and passed
  to `EvolutionEngine`; they hold no framework state beyond their task
  packs (memoization of suites is the objective's own concern — build once,
  as all built-ins do).
- Grading runs in your process unless you choose the sandbox — `code-tasks`
  and `regex_agent` execute *model-produced code* in the sandbox; text
  objectives don't need it.
