# Walkthrough — one run, narrated end to end

*The offline demo run, followed file by file and event by event. Everything
quoted below is real output from `rsif evolve` — you can reproduce it with
[quickstart.md](quickstart.md) and diff your run against this page byte for
byte.*

One caveat before we start, stated honestly: the demo runs **offline**,
against a scripted provider (`llm/demo.py`) that plays both the agent and
the improver with pre-written, content-addressed answers. That makes the
run free, instant, and deterministic — ideal for seeing the *machinery*.
Every gate, store write, and event you see below is the real production
code path; only the model's words are canned. [quickstart.md](quickstart.md)
shows the same loop against a live API.

## 1. The task: what is being improved, and against what

The demo objective is `code-tasks`: the agent must implement small Python
functions. Each task is a JSON file like this one — the real `val/01`:

```json
{
  "id": "val/01",
  "prompt": "Implement `sum_list(xs)` summing a list of numbers.",
  "function_name": "sum_list",
  "hidden_tests": "assert sum_list([1, 2, 3]) == 6\nassert sum_list([]) == 0\nassert sum_list([-1, 1]) == 0\n"
}
```

Note what the agent sees and doesn't see: the `prompt` is given to it; the
`hidden_tests` are **not**. Scoring extracts the fenced `python` code
block from the agent's answer and executes the hidden tests against it in
a locked-down sandbox subprocess. A task scores 1.0 or 0.0.

The 26 tasks are split into four **suites** with distinct jobs — a strict
train/validation/test discipline like in ML:

| Suite | Tasks | Purpose |
|---|---|---|
| `train` (8) | seen during search | cheap signal for screening candidates |
| `val` (10) | seen at acceptance | **the** gate: a change must measurably improve held-out val score to deploy |
| `test` (5) | sealed until the end | final honesty check, opened only by `rsif report` |
| `canary` (3) | trivial | must **never** regress — smoke tests |

## 2. `rsif init` — what exists before any improvement

`rsif init ../runs/demo --objective code-tasks --provider scripted` writes
a workspace and six **seed artifacts** — the complete starting agent, all
of it versioned data under `artifacts/`:

```
runs/demo/
├── artifacts/
│   ├── prompt/system/v1/system.md          ← the agent's system prompt
│   ├── memory/playbook/v1/playbook.json    ← its standing "lessons" file
│   ├── module/default/v1/module.py         ← its control loop as code
│   ├── meta/improver-template/v1/template.md   ← the IMPROVER's prompt
│   ├── meta/operator-catalog/v1/operators.json ← its allowed mutation verbs
│   └── policy/context/v1/policy.json       ← {"max_memory_chars": 4000}
├── checkout.json        ← the ACTIVE agent: artifact → version (all v1)
├── config.json, seed.json
└── (events.jsonl, lineage.jsonl, archive.json, evals/, memory/ appear as the run progresses)
```

Three of the seeds are worth actually reading, because they are the whole
agent. The system prompt (`prompt/system` v1):

````markdown
You are a careful Python-solving agent. Read the task, think, and answer
with a single ```python code block implementing the requested function
exactly (signature and name as specified). Prefer simple, correct,
dependency-free code. The block must be self-contained: only stdlib
imports.
````

The control loop (`module/default` v1) — an agent's "architecture" here is
just a Python class the harness calls; this one is ask-once-then-submit:

```python
class Module(AgentModule):
    name = "default"
    def step(self, ctx: ModuleContext) -> Action:
        if not ctx.session.messages:   # nothing asked yet
            return LLMAction()         # → harness calls the model
        return SubmitAction()          # → harness takes the last reply as the answer
```

And the improver template (`meta/improver-template` v1) — the prompt of the
meta-agent whose whole job is proposing changes. Its blanks are filled at
runtime with the *current* checkout summary, archive frontier, and recent
lessons, which is how the improver "sees" what it is improving:

```
You are the Improver: … propose ONE bounded, testable change …
## Current agent      {checkout_summary}
## Archive frontier   {archive_summary}
## Recent lessons     {lessons}
## Available operators {operators}
… Answer with a single JSON object:
{"surface": …, "operator": …, "hypothesis": …, "rationale": …, "ops": […]}
```

The `operator catalog` lists the nine mutation verbs the improver may use
(`prompt/refine`, `skill/add`, `memory/add-rule`, `module/edit`, …) — it
cannot invent others, and every verb is typed to the surface it may touch.

## 3. The baseline — measuring the seed agent

The run starts by scoring the seed agent on all three suites. Each
**attempt** works like this: the harness assembles the full context
(system prompt + task prompt + injected memory), the module drives the
loop (here: one model call, then submit), and the objective grades the
result against hidden tests. One line per attempt lands in the log:

```
eval{suite=train, label=baseline, n=8,  score=0.375}   ← 3 of 8 passed
eval{suite=canary, label=baseline, n=3, score=1.0}
eval{suite=val,    label=baseline, n=10, score=0.4}    ← 4 of 10 passed
archive_update{action=baseline, descriptor=[seed,1,0], fitness=0.4}
```

The last line registers the seed agent as the root of the **archive** —
the zoo of agents the search keeps. `0.4` on held-out tasks is our
starting line: the seed prompt is decent but loses boundary cases
(empty lists, zeros, off-by-ones).

## 4. Generation 1 — an accepted change, gate by gate

### The proposal

One LLM call in the `improver` role returns a JSON proposal (abridged to
the fields that matter):

```json
{"surface": "prompt", "operator": "prompt/refine",
 "hypothesis": "edge-case enumeration discipline reduces boundary failures",
 "rationale": "the baseline loses iteration and aggregation tasks to
               off-by-one and edge-case mistakes",
 "ops": [ … one UpdateOp against prompt/system … ]}
```

Event: `proposal{g1p1, surface=prompt, operator=prompt/refine, hypothesis=…}`.

### The patch materializes — but does NOT deploy

The engine applies the op, which writes a **new immutable version** on
disk. The live agent (checkout.json) is untouched — this is the equivalent
of a pull request that checks out into a scratch worktree:

```
artifacts/prompt/system/
├── v1/system.md   ← unchanged, still what the deployed agent uses
└── v2/system.md   ← the candidate (its edit is quoted below)
```

v2 appends a worked-example strategy to the prompt:

```markdown
Worked example: restate the signature, enumerate edge cases (empty
input, zero, one element), then implement the simplest loop-based
solution.
```

Before any evaluation, two cheap static gates run **before execution**:
`gate{scan, passed}` — the import whitelist (a no-op for prompts, load-
bearing for code artifacts) — and, for module patches only, a load test.
Only then does anything run.

### The gates, in order, with the real numbers

1. **Screen** (cheap probe, 2 of the 8 train tasks):
   `child 0.5 ≥ parent 0.5 − 0.30` → pass. A catastrophically bad idea
   dies here for the price of two tasks.
2. **Canary** (the 3 trivial tasks): `child 1.0 ≥ parent 1.0` → pass.
   Any drop here is an instant reject, however good val looks.
3. **Full train**: child 0.75.
4. **Val acceptance** — the merge gate. Child and parent both run all 10
   held-out tasks:
   `0.60 > 0.40 + 0.02` ✓ and the child wins on at least one more task
   than it loses (a floor against lucky reshuffles) ✓
   `gate{val, passed=true, child=0.6, parent=0.4, threshold=0.02}`

### Acceptance

```
accept{g1p1, promoted=true, val_child=0.6, val_parent=0.4}
archive_update{descriptor=[prompt,2,0], fitness=0.6, stored=true}
reflect{action=distill_insight}
```

`promoted=true` means **checkout.json is rewritten**: `prompt/system` now
points at v2. The deployed agent changed. The archive entry
`[prompt, 2, 0]` decodes as: *prompt-surface agent, val in band 2 of 4
(band = ⌊mean·4⌋), 0 = a steps-band placeholder* — bands are the
"behavior niches" that keep the search diverse. Finally, a one-line
**insight** is distilled into long-term memory (only from verified wins):
*"edge-case enumeration discipline reduces boundary failures (val 0.40 →
0.60)"* — future improver calls and agent contexts will retrieve it.

## 5. Generation 2 — same drill, compounding

The improver (now seeing the v2 prompt, the archive, and the distilled
insight) doubles down — hypothesis: *"verifying each enumerated edge case
before answering generalizes further"* → v3 adds one sentence ("Verify
your logic against every enumerated edge case before answering"). Gates:
screen 1.0 vs 0.5, canary 1.0, train 1.0, **val 1.0** — every held-out
task passes.

```
accept{g2p1, promoted=true, val_child=1.0, val_parent=0.6}
archive_update{descriptor=[prompt,4,0], fitness=1.0}   ← a second niche
```

Held-out accuracy went **0.40 → 0.60 → 1.00** through two one-line prompt
edits, each deployed only after measured, held-out improvement. That is
the entire thesis of the framework in one sentence.

## 6. Generation 3 — the most instructive moment: accepted, NOT deployed

The improver now proposes the *opposite* hypothesis — *"dropping
edge-case enumeration produces faster, simpler answers"* → v4 strips the
enumeration discipline. This is exactly the kind of plausible-sounding
regression the gates exist for. Watch what happens:

- The **parent it must beat is sampled from the archive**, and the sample
  landed on the *seed* lineage (superseded, val 0.4), not the current
  best. Deliberate: the search keeps old lineages selectable so dead ends
  can be revisited.
- Gates: screen `child 1.0 ≥ parent 0.0 − 0.3` ✓ (the seed parent flunks
  its own probes), canary 1.0 ✓, **val 0.9** — worse than the active
  agent's 1.0, but *better than its sampled parent's 0.4*.
- So val acceptance passes (0.9 > 0.4 + 0.02)… and then:

```
accept{g3p1, promoted=FALSE, val_child=0.9, val_parent=0.4}
archive_update{descriptor=[prompt,3,0], fitness=0.9, stored=true}
```

Two different verdicts in one event: **archive-accept** (it beat its
sampled parent → kept as a stepping stone in the `[prompt,3,0]` niche)
but **no promotion** (it did not beat the *active* agent, 0.9 < 1.0 → the
deployed agent does not change). The final checkout proves it:

```json
{"prompt/system": 3,   ← still v3; v4 exists on disk but was never deployed
 "memory/playbook": 1, "module/default": 1, "policy/context": 1,
 "meta/improver-template": 1, "meta/operator-catalog": 1}
```

This two-level rule is the anti-ratchet: you can never talk the system
into deploying a worse agent by beating up on a weak sparring partner.

## 7. The end state — everything auditable

```
run_end{accepted=3, rejected=0, best_fitness=1.0}
```

Final accounting of a 3-generation run:

| Question | Where the answer lives |
|---|---|
| What is deployed? | `checkout.json` (v3 of the prompt) |
| What was ever tried? | `lineage.jsonl` — 9 append-only entries (6 seeds, 3 updates), including v4 |
| What existed and was rejected? | `archive.json` — 4 individuals across 4 niches; v4's lineage stays selectable |
| Why was each decision made? | `events.jsonl` — 147 events; every gate carries its numbers |
| What did it actually learn? | `memory/insights.jsonl` — 3 distilled insights with provenance |
| Does it hold up on unseen data? | `rsif report` unseals the 5 sealed test tasks on the archive best, with a bootstrap confidence interval |

And the determinism claim, concretely: delete the workspace, re-run with
the same seed, and `events.jsonl`, `archive.json`, `checkout.json`, and
`lineage.jsonl` regenerate **byte-identically** — that assertion runs in
the offline test suite on every commit (the golden test).

## 8. The loop, restated in one diagram

```
        ┌──────────────── IMPROVER (LLM) ────────────────┐
        │  reads: active agent + archive + lessons       │
        │  emits: ONE bounded patch + hypothesis         │
        └───────────────────────┬────────────────────────┘
                                ▼
        materialize as candidate versions (checkout untouched)
                                ▼
   static gates (scan / load) — before any execution
                                ▼
   cheap screen (2 tasks) ── fail ──► reject + reflect
                                ▼ pass
   canary (never regress) ── fail ──► reject + reflect
                                ▼ pass
   full train + VAL (held-out) ─────► reject + reflect
                                ▼ pass: val(child) > val(parent)+θ
        beat sampled parent? → keep in archive (stepping stone)
        also beat ACTIVE agent? → promote → the deployed agent changes
                                ▼
        lessons distilled; budget & drift checks; next generation
```

Everything else in these docs — the component guides, the design
rationale, the safety stack — is one box of this diagram in detail.

## Where to go next

- Do it yourself: [quickstart.md](quickstart.md) (one minute, offline).
- Why each gate is shaped that way: [lifecycle.md](lifecycle.md), then
  [design.md](design.md) for the papers behind each mechanism.
- The static map of components: [architecture.md](architecture.md).
