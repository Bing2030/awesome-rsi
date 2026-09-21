# Component guide — cost-aware evolution (SoL-Pi grounding)

*The first objective that prices tokens — and the POLICY artifact that
makes the harness's own context assembly evolvable.*

Files: `projects/harness_efficiency/{objective.py,run.py}`; engine-side
support: `Attempt.input_chars` (`src/rsif/runtime/types.py`,
`runtime.py`), `ArtifactType.POLICY` + the `policy/context` seed
(`src/rsif/constants.py`, `store.seed_defaults`), the memory cap
(`src/rsif/evolve/assembler.py`), the `policy/bound-context` operator
(`src/rsif/operators_seed.py`), and `policy` in `FAST_SURFACES`
(`src/rsif/evolve/scheduler.py`). Verified by
`tests/integration/test_harness_efficiency.py` (5 tests).

Grounding: SoL-Pi [2609.20519] — harness-layer auto-research under a
token-efficiency objective gated by a *predeclared capability floor*.

## The scalar quality-first floor

`EfficiencyObjective.evaluate` folds cost into the per-task score:

```python
answer   = extract_answer(attempt.result)          # text after the last "ANSWER:"
correct  = answer == task.meta["target"]
tokens   = attempt.input_chars // 4 + attempt.usage.out_tokens   # in + out
cost     = min(1.0, tokens / 500)
score    = (1.0 if correct else 0.0) - 0.1 * cost
```

with λ = 0.1 and a 500-token budget per task. This is a **scalar floor,
not a pareto gate** (a deliberate design choice):

- Cost can never promote a wrong answer (wrong ≤ −λ·cost < 0 < any correct
  answer's ≥ 0.9).
- Cost can never push a correct answer below 1 − λ = 0.9.
- Therefore **the existing gates enforce the capability floor unchanged**:
  the val threshold (θ = 0.02) and the M13 paired net-gain floor still run
  exactly as before. No new gate was added anywhere.

The task pack is a deliberately trivial echo task ("output the exact string
`'42'` after the marker `ANSWER:`") so that correctness and token cost are
the only things that vary — the isolated signal an efficiency objective
needs. `extract_answer` takes the text after the **last** `ANSWER:` marker
(learning the M14 lesson: prefer a marked final line over the first line).

## Input cost: `Attempt.input_chars`

Cost-awareness needs both sides of the token bill. The runtime records
`input_chars = len(compose_system()) + len(task_prompt)` — the context
actually injected — on every attempt. The field is **additive** (default 0)
and deliberately does *not* touch `session.usage` or budget accounting, so
no other objective, no golden byte, and no budget behavior changes.

## The POLICY artifact (`policy/context`)

The harness's context assembly becomes evolvable data:

```json
{ "max_memory_chars": 4000 }
```

`build_spec` truncates the **total** injected memory (playbook + retrieved
insights/reflections) to this cap after assembly (cap ≤ 0 = inject
everything). Tightening the cap lowers `input_chars` on every task — which
raises the efficiency score if correctness holds. So:

- the **output axis**: prompt edits that make answers concise;
- the **input axis**: `policy/bound-context` edits that make contexts
  smaller.

Both are ordinary operator proposals through the ordinary gates. `policy`
is a **fast surface** — it rides the every-generation cadence like
prompt/skill/memory/module (only META is slow).

## The proofs (offline, deterministic)

1. **Concise beats verbose** — baseline answers verbosely (~1170 chars of
   reasoning); candidate 1 answers concisely; candidate 2 answers
   concisely but *wrong*. Result: candidate 1 accepted and promoted (val
   0.91 → 0.97, clearing θ with a ~0.06 gap); candidate 2 rejected at the
   cascade screen (train score ≈ −0.01, nowhere near its parent).
2. **Context compaction is accepted** — baseline carries a large,
   non-load-bearing memory artifact; the proposal tightens
   `max_memory_chars` 4000 → 100 via `policy/bound-context`. Correctness
   is unchanged (both agents echo correctly), `input_chars` drops, the val
   gap clears θ, the edit is accepted and `policy/context` advances v1 →
   v2. A unit test separately pins that the cap really truncates the
   assembled spec's memory.

## Live runner

`projects/harness_efficiency/run.py` mirrors the regex_agent runner —
gateway provider, hard budgets (USD/calls/wall), disk-cached responses,
fail-closed META, val trace + spend printed, sealed test split evaluated
after the run:

```bash
cd framework
uv run python -m projects.harness_efficiency.run --run ../runs/eff \
    --model glm-5.3-flash --generations 2 --proposals 1
```

No live run is committed for this project — the seam is proven
deterministically offline; the runner exists for the real thing.

## Design decisions worth remembering

- **Scalar floor over pareto gate** — chosen because the existing gate
  chain then *is* the capability floor; a pareto surface would have needed
  new archive semantics (cost as a second objective dimension) and new
  acceptance logic.
- **Fold cost into the task score, not the fitness only** — so the paired
  net-gain floor sees per-task cost movements, and a candidate that saves
  tokens on *every* task (either axis) clears it on a pure efficiency gain.
- **Calibration** — λ = 0.1, budget = 500 tokens: both proof scenarios
  clear θ = 0.02 with ~3× margin while correct scores stay ≥ 0.9. If you
  retune budgets or answer styles, re-check those margins.
- **What SoL-Pi's floor means here** — "predeclared capability floor" is
  realized *structurally*: the objective's formula is fixed before the run,
  and no candidate can trade correctness for cost past the floor because
  the floor is inside the score, enforced by the unchanged acceptance
  gates.
