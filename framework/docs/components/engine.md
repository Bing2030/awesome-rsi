# Component guide — the evolution engine

*The trusted loop: propose, screen, gate, accept or reject, remember.*

Files: `src/rsif/evolve/engine.py` (the engine and its five phases),
`proposer.py` + `proposal.py` (the improver), `selection.py` (the gates),
`archive.py` (MAP-Elites), `scheduler.py` (fast/slow cadence). The phase
order and rejection taxonomy are detailed in [lifecycle.md](../lifecycle.md);
this guide covers the mechanisms and their knobs.

## EvolutionEngine

```python
engine = EvolutionEngine(
    store=ArtifactStore(ws),          # versioned artifacts
    provider=...,                     # any LLMProvider
    objective=...,                    # any Objective
    cfg=RunConfig(),                  # every knob
    clock=time.time,                  # injectable → deterministic tests
    approver=None,                    # optional; META is fail-closed without it
)
summary = engine.run()                # RunSummary
```

Construction wires the whole stack: event log, hard budget, wrapped
provider (`_EventfulProvider` — every completion becomes an `llm_call`
event and a budget record), archive, reflection/insight stores, agent
runtime, and the improver. `run()` then executes the loop
(baseline → generations × proposals → per-generation housekeeping) and
always terminates with a `run_end` event — even on budget exhaustion,
provider errors, or engine bugs (distinct stop reasons; see
[observability.md](observability.md)).

Out-of-loop evaluation reuses the identical path:
`engine.evaluate_active(suite)` (what `rsif run` calls) and
`engine.evaluate_snapshot(mapping, suite)` (`rsif report`, on the archive
best) — same assembly, same memory injection, same memoization, so scores
are comparable everywhere.

## The Improver

`evolve/proposer.py`. One LLM call (role `improver`, optionally a different
`improver_model`) whose **user prompt is assembled from the active META
template** — which is an artifact, so the improver's own strategy evolves.
The template receives:

- `max_ops` — the bounded-edit budget,
- `checkout_summary` — active artifacts, versions, 80-char previews,
- `archive_summary` — frontier top-5 + superseded lineages worth revisiting
  + the sampled parent to mutate,
- `lessons` — rendered reflections + insights (what failed/succeeded and
  why),
- `operators` — the catalog, filtered to surfaces open this generation,
- `op_schema` — the JSON op grammar.

The response is parsed by `proposal.py`, which tolerates code fences and
prose around the JSON object but rejects anything that is not exactly one
valid proposal (`surface` ∈ the six types, known operator shape, non-empty
ops). Grounding: STOP [2310.02304], Promptbreeder [2309.16797].

## The gates (`evolve/selection.py`)

Three pure functions — the entire acceptance policy of the framework:

```python
pass_screen(child, parent, epsilon)   # child ≥ parent − ε        (cascade)
pass_canary(child, parent)            # child ≥ parent            (hard)
accept_val(child, parent, θ, c_scores, p_scores)
                                      # child > parent + θ  AND  paired net gain ≥ 1
```

Why the paired floor: on a 10-task val suite the mean can move by θ through
reshuffled noise; requiring at least one *net* task improved is the cheap
honest noise floor at the gate. The bootstrap CI at `rsif report` is the
final statistical check. Grounding: SkillOpt strict held-out acceptance
[2605.23904]; noise guards [2510.16657]; execution-grounded verification
[2310.01798] — an LLM's opinion of a candidate is never an input here.

## The archive (`evolve/archive.py`)

MAP-Elites with backtracking:

- **Niche key** = the objective's `behavior_descriptors` (prefixed with the
  proposal surface). One elite per cell; replacement is strictly
  `(fitness, -cost)` — better fitness, then lower cost.
- **Parent sampling** = harmonic rank-biased roulette over the frontier
  (weight `1/(rank+1)`): every elite selectable, fitter ones likelier.
  DGM's greedy-best-parent ablation (39.7% vs 50.0% SWE-bench) is the
  independent evidence for not going greedy.
- **ε-reseeding (ε = 0.2)**: with probability ε the parent comes from
  *superseded lineages* — individuals displaced inside their own niche by a
  fitter sibling. This is the realized backtracking pressure; `parent_ref`
  pointers are lineage metadata for inspection.
- Persisted to `archive.json` as `{cells, history}` — history keeps every
  stored individual, so superseded genetic material survives.

## The scheduler (`evolve/scheduler.py`)

```python
schedule_for(gen, meta_every_k) → Schedule(open_surfaces, meta_open)
```

Fast surfaces (`prompt`, `skill`, `memory`, `module`, `policy`) are open
every generation; `meta` opens only when `gen % meta_every_k == 0`. A
proposal against a closed surface is rejected (`reason="surface"`) *before
any approval or patch work*. Two-cadence design per MetaSkill-Evolve
[2607.05297].

## Two-level acceptance (no ratcheting down)

A candidate may beat its *sampled* parent (a weak elite) while still being
worse than the *active* agent. The engine separates:

- **Archive-acceptance**: beat the sampled parent → enter the niche
  (stepping stone; the demo's third accept).
- **Promotion**: also `val(child) > val(active)` → write the checkout.

Because promotion compares against the active agent — not whatever parent
happened to be sampled — the deployed agent cannot regress through weak
parents. `accept` events carry `promoted` so the distinction is visible
(`rsif inspect --filter kind=accept`).

## META recursion: provisional accept + eval window

A META-only patch leaves `AgentSpec` byte-identical (META artifacts are not
part of the spec), so the strict val gate would measure only noise. Instead
(`engine._settle_meta`):

1. Accept provisionally on agent **non-regression**; deploy the template.
   One META experiment at a time (`meta_pending`).
2. Run `meta_eval_window` (default 3) generations of normal proposals —
   now formatted by the evolved template.
3. Compare the window's proposal success rate to the pre-edit baseline:
   ≥ baseline (or any win, if no baseline) → `meta_confirm`; else restore
   the pre-edit META versions (append-only) → `meta_revert`.

Mixed META+agent patches take the normal strict gate — the agent-visible
part must pay for the whole patch.

## Evaluation mechanics (`engine._evaluate`)

- **Memo key**: `(sorted mapping items, split, task ids)` — a suite is
  evaluated once per run per agent-state; parents' books are reused across
  proposals, screens memo-hit full train evals.
- **Injection**: for each task, `_agent_memory(task.prompt)` renders
  retrieved insights + reflections (TF-IDF, top-3 each) and passes them as
  `extra_memory` to `build_spec` — the agent's context adapts per task.
- **Persistence**: every fresh book lands in `evals/gen_NNNN/<split>_<label>.json`
  and as an `eval` event (suite, label, n, mean).
- Known trade-off (documented limitation M2): memo hits return the book
  computed with the memory store *as of then* — comparability vs staleness.

## Tuning the loop

| Knob | Effect of raising it |
|---|---|
| `generations`, `proposals_per_generation` | More search (cost scales roughly linearly; budget still bounds it). |
| `screen_tasks` | Screen is more reliable, less cheap. |
| `screen_epsilon` | Looser screen — more candidates reach the expensive gates. |
| `acceptance_threshold` | Harder acceptance — fewer, better-verified promotions. |
| `meta_every_k` | META opens more often (more recursion, more approvals). |
| `meta_eval_window` | More statistical power per META experiment, slower verdicts. |
| `max_patch_ops` | Bigger edits allowed (risk of context collapse rises). |

## Where it's pinned

- Flagship golden: full 2-proposal run byte-reproducible; A accepted (val
  0.40 → 0.80, promoted, archived), B rejected on val with rollback +
  reflection; phase monotonicity asserted per proposal
  (`tests/golden/test_flagship_evolution.py`).
- Two-level acceptance blocks the ratchet
  (`test_safety_loop.py::test_two_level_acceptance_prevents_ratchet`).
- META: provisional → revert (original template provably re-used),
  confirm-on-win, pending guard (`test_meta_and_module.py`).
- Archive: elitism, tie-break, frontier order, rank bias, ε-reseed,
  persistence (`test_evolve.py`).
