# The lifecycle of a proposal

The dynamic view: what actually happens when the improver speaks, in what
order, which events land in the log, and every way a proposal can die.
Static structure lives in [architecture.md](architecture.md); vocabulary in
[concepts.md](concepts.md). The authoritative implementation is
`EvolutionEngine._one_proposal` in `src/rsif/evolve/engine.py`.

## The run loop

```
EvolutionEngine.run()
 │
 ├─ run_start event
 ├─ baseline: evaluate seed agent on train + canary + val
 │    └─ archive_update(action="baseline")   # the root individual
 │
 ├─ for gen in 1..generations:
 │    ├─ for slot in 1..proposals_per_generation:
 │    │    ├─ budget.exhausted()? → budget event, stop_reason="budget:<dim>"
 │    │    └─ _one_proposal(gen, slot)       # five phases, below
 │    ├─ every insights_distill_every gens: retire correlated insights
 │    ├─ _settle_meta(gen)                   # close a META eval window
 │    ├─ _drift_check(gen)                   # canary/active regression, stagnation
 │    │    └─ rollback alarm → auto_rollback, run CONTINUES on the restored agent
 │    └─ archive.save(gen)
 │
 ├─ (or an early stop: budget / drift / provider error / engine bug)
 └─ run_end event  (accepted, rejected, best_fitness, stop_reason?)
```

`RunSummary` returns generations, accepted, rejected, best fitness and
descriptor, the best spec snapshot, and the stop reason (`budget:<dim>`,
`drift`, `error:<Origin>` for provider failures, `engine:<Type>` for engine
bugs — kept distinct on purpose).

## The five phases of one proposal

Every event below is stamped with its phase; the flagship golden test
asserts per-proposal phase monotonicity
`proposal → design → exploration → verification → correction`.

### Phase 1 — proposal

The scheduler (`evolve/scheduler.py`) decides which surfaces are open this
generation: the **fast surfaces** (`prompt`, `skill`, `memory`, `module`,
`policy`) every generation; the **META surface** only every `meta_every_k`-th
generation (default 3). The improver's prompt is assembled from the active
META template (itself evolvable), a checkout summary, the archive frontier +
superseded lineages, recent lessons (reflections + insights), and the
operator catalog filtered to open surfaces.

```
improver LLM call (role="improver")
  → parse_proposal: {surface, operator, hypothesis, rationale, ops}
```

| Check | Failure → rejection `reason` | Event |
|---|---|---|
| JSON/schema parse | `parse` | `reject` |
| Surface open this generation? | `surface` | `reject` |
| META + `require_approval_for_meta` | `approval` (fail-closed: no approver = deny) | `approval`, `reject` |
| A META edit while another's window is open | `meta_pending` | `reject` |

On success: **`proposal`** event (surface, operator, hypothesis).

### Phase 2 — design (validate + materialize, never activate)

| Check | Failure → `reason` | Event |
|---|---|---|
| `len(ops) ≤ max_patch_ops` | `bounded` | `reject` |
| Operator exists in catalog **and** matches the surface | `operator` | `reject` |
| `store.apply_patch` succeeds (ids exist, versions writable) | `apply` | `reject` |
| Static scan of skill/module payloads (AST import whitelist) | `scan` | `gate(gate="scan", passed=false)`, `reject` |
| Module patch loads and honors the ABI | `load` | `gate(gate="load", …)`, `reject` |

On success: **`patch`** event (candidate versions), then the feasibility
gates above. Note the ordering: static gates run **before any execution** —
a candidate that would escape the sandbox or cannot load is never evaluated,
not even on the cheap screen. The candidate mapping is
`{**parent.spec_snapshot, **result.versions}` — the active checkout is
untouched.

### Phase 3 — exploration (cheap cascade screen)

`screen_tasks` (default 2) train tasks are sampled with the run RNG; child
and parent both run them (parents are usually memo hits).

```
pass_screen: child_mean ≥ parent_mean − screen_epsilon   (ε = 0.30)
```

Pass → **`screen`** event (`passed: true`). Fail → `screen` rejection —
this is the cheapest exit and the workhorse of cost control: in the live
regex_agent run, both real-improver regressions died here, before canary or
val spent anything.

### Phase 4 — verification (the gate chain proper)

In order:

1. **Canary** — `child_canary ≥ parent_canary`; any drop is a hard reject.
   Event: `gate(gate="canary")`.
2. **Full train eval** — memoized; the screen usually covered a subset.
3. **Val acceptance** — both child and parent run the full val split:
   - Agent patches: `accept_val` requires
     `val(child) > val(parent) + θ` **and** paired net gain
     (`#tasks-better − #tasks-worse ≥ 1`). Event: `gate(gate="val", …)`
     with both scores, the threshold, and the net-gain note.
   - **META-only patches** (agent spec byte-identical by construction):
     accept on *non-regression* (`child ≥ parent`); the real test is
     deferred to the eval window (below).

### Phase 5 — correction

**On reject** (`engine._reject`): a `reject` event (reason + detail), a
`rollback` event (`action="discard_candidate"` — the checkout never moved),
and a Reflexion reflection written to episodic memory with a deterministic
trace ("proposal g1p2 [prompt/prompt/refine] rejected at val: … Try a
different, smaller change."). Reflections are retrieved for later improver
and agent contexts — rejection feeds forward.

**On accept** — two levels:

- **Archive-acceptance**: the candidate beat its *sampled parent* → stored
  in its MAP-Elites niche (elitist replacement, ties by lower cost) as a
  stepping stone.
- **Promotion**: additionally `val(child) > val(active)` (always true for
  META-only) → `store.promote` writes the checkout; the deployed agent
  changes. A candidate can be accepted *without* promotion (the demo's
  third accept) — the archive grows, the agent doesn't regress.

Events: **`accept`** (`promoted`, `meta_provisional`, val/train numbers),
**`archive_update`** (descriptor, fitness, stored, active), and
**`reflect(action="distill_insight")`** — ExpeL-style insight distilled
from the verified success.

## The META recursion state machine

A META-only edit changes the *improver*, not the agent, so it runs as a
controlled experiment (`engine._settle_meta`):

```
proposal (META-only, approved, non-regressing agent)
   │  provisional accept + deploy template          accept{meta_provisional}
   ▼
meta_eval_window generations (default 3) of normal proposals
   │  the evolved template demonstrably formats the next improver calls
   ▼
window closes at generation-end:
   success_rate vs pre-edit baseline ── better/equal ──► meta_confirm
                    └── worse (or 0 wins, no baseline) ──► meta_revert
                                                            (pre-edit versions
                                                             restored append-only)
```

One META experiment at a time (`meta_pending` guard). Mixed META+agent
patches skip this path entirely — the agent-visible part must pay for the
whole patch through the strict val gate.

## Interruptions and run-level correction

- **Budget**: checked before each proposal (`exhausted()` — fires at the
  limit) and after every recorded LLM call (`overshot()` — a call that
  pushes strictly past a limit raises `BudgetExhausted` immediately, so
  overshoot is bounded to one call). Both emit a `budget` event with the
  full snapshot and set `stop_reason="budget:<dim>"`; there are never
  partial proposals.
- **Drift** (every generation end, on the *active* agent): canary or active
  regression → **auto-rollback** to the archive best (`restore` lineage,
  extras deactivated) and the run *continues* on the restored agent;
  stagnation (≥ `stagnation_threshold` consecutive rejections) → an
  `approval` event; approved → continue, denied/unwired → stop with
  `stop_reason="drift"`.
- **Provider errors** propagate as `ProviderError` (with `origin`) and abort
  cleanly — `error` event + `stop_reason="error:<Origin>"`; never a fake
  0-score, never a "parse" rejection.

## Every event kind (18)

`run_start · run_end · proposal · patch · screen · eval · gate · accept ·
reject · reflect · archive_update · rollback · budget · llm_call ·
approval · error · meta_confirm · meta_revert`

`eval` events carry `suite`, `label` (baseline/child/parent/run/report-test),
`n`, and the mean score — the same event stream serves `rsif status`,
`rsif inspect`, and post-hoc analysis. Payloads carry only ids/scores/
decisions (never wall-times or sandbox stderr), which is what makes the
golden log byte-stable.

## A concrete trace (from the golden test)

`tests/golden/test_flagship_evolution.py` scripts a full 2-proposal run;
this is the shape of what lands in `events.jsonl`:

```
run_start
eval{baseline, train}  eval{baseline, canary}  eval{baseline, val}
archive_update{action=baseline}
  g1p1: proposal{prompt/refine}  patch{prompt/system v2}
        gate{scan}  eval{child/parent × screen}
        screen{passed}  gate{canary}  eval{train}  eval{val × 2}
        gate{val, passed}  accept{promoted}  archive_update  reflect{distill}
  g1p2: proposal{prompt/refine}  patch{prompt/system v3}
        gate{scan}  eval{screen × 2}  screen{failed}
        reject{reason=screen}  rollback{discard_candidate}  reflect
run_end{best_fitness=0.8}
```

Determinism: rerunning the same seed into a fresh workspace reproduces
`events.jsonl`, `archive.json`, `checkout.json`, and `lineage.jsonl`
**byte-identically** — that assertion (against a committed golden log) runs
in the offline suite on every test run.
