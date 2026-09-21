# rsif — Design Document

> **rsif** is a framework for constructing agents that improve themselves
> through a verified loop: *idea proposal → idea exploration → idea design →
> idea verification & validation → correction*, iterating until the best
> agent evolves. Every design mechanism below carries (a) the paper(s) it is
> grounded in, (b) the code path that implements it, and (c) the test that
> verifies it. Citations were cross-checked against this repo's hand-distilled
> entries in `site/curated.json`; §10 records spot-checks against the local
> PDFs in `resources/`.

Implementation process and status: `docs/plan.md`. Key decisions and bugs
caught along the way: `docs/decision-log.md`.

Reader's guide: this document is the *rationale* layer (mechanism ↔ paper ↔
code ↔ test). For the reference layer — system map, glossary, per-subsystem
guides — see `docs/index.md` (start there as a newcomer:
`docs/architecture.md`, `docs/concepts.md`, `docs/lifecycle.md`,
`docs/components/`).

---

## 1. Scope and the trust boundary

rsif targets **harness-level recursive self-improvement**: the LLM weights are
frozen; everything the agent *is* — module code, prompts, skills, memory,
and the improver's own templates — is evolvable data under a trusted, frozen
outer loop.

```
                ┌───────────────────────────────────────────────┐
                │ EvolutionEngine (trusted, frozen process)     │
                │ propose → explore → design → verify → correct │
                └───┬─────────┬──────────┬──────────┬──────────┘
                Improver   Objective   Archive    Safety
              (templates  (fitness,   (MAP-Elites (gates, drift,
               = META      suites:     + backtrack) budget, approve,
               artifacts)  train/val/              rollback)
                           test/canary)
                ┌────┴─────────────────────────────────────────┐
                │ ArtifactStore — immutable version dirs +      │
                │ append-only lineage + active checkout         │
                │ skills | prompts | memory | modules | meta    │
                └────┬─────────────────────────────────────────┘
                  AgentSpec (resolved checkout)
                ┌────┴─────────────────────────────────────────┐
                │ AgentRuntime: LLMProvider ↔ module ABI ↔     │
                │ Sandbox (+ memory retrieval)                  │
                └──────────────────────────────────────────────┘
```

**Why this shape.** DGM [2505.22954] and ADAS [2408.08435] show agents can
rewrite themselves productively when an outer empirical selector enforces
progress; Gödel Agent [2410.04444] shows the risks when self-modification is
unguarded. rsif's split — *engine is trusted code, agent is modifiable
data* — realizes the former while making it structurally impossible for an
evolved artifact to break its own selection loop in v1. The
improver-improves-improver axis [2310.02304, 2607.05297] is not sacrificed:
it runs through **META artifacts** (§4.5) under stricter gates and human
approval.

**Four improvement surfaces** (all first-class artifacts):

| Surface | Artifact | Example evolution |
|---|---|---|
| Skills & tools (code) | `skill/*` | new tool module + manifest, admitted after the static-scan gate |
| Prompts & strategies | `prompt/*` | refine the system prompt (the demo's main axis) |
| Memory & knowledge | `memory/*` | playbook sections, distilled insights |
| Architecture (meta-agent) | `module/*` | rewrite the agent's control loop within the module ABI |

---

## 2. The design loop, phase by phase

One proposal moves through five phases; **every event in the log is
phase-attributed** (observability with edit attribution [2604.25850]).

| Phase | What happens | Code | Reference |
|---|---|---|---|
| **1 Proposal** | Improver (a meta-agent running a META template) proposes one bounded change: surface, operator, hypothesis, ops. Prompt is assembled from checkout summary, archive frontier, recent lessons (reflections+insights) | `evolve/proposer.py` | STOP [2310.02304]; Promptbreeder [2309.16797] |
| **2 Exploration** | Cheap cascade screen: candidate runs `screen_tasks` probe tasks; continues only if `score ≥ parent − ε` | `engine._one_proposal`, `evolve/selection.pass_screen` | AlphaEvolve cascade [2506.13131] |
| **3 Design** | Proposal → concrete patch: ≤ `max_patch_ops` ops (bounded edits), operator validated against the catalog, `apply_patch` materializes candidate versions **without activation**; then static feasibility gates (AST scan for forbidden constructs; module-ABI load check) **before any execution** | `engine._one_proposal`, `artifacts/store.apply_patch` | ACE bounded ops [2510.04618]; SkillOpt [2605.23904]; guard layers [2603.03329] |
| **4 Verification** | Execution-grounded gate chain: canary suite (`child ≥ parent`) → full train eval → **val acceptance** (`val(child) > val(parent) + θ` with a paired net-gain floor; META-only patches defer to an eval window, §4.5). LLM self-critique is advisory, never the accept signal | `evolve/selection.py`, engine gates | DGM [2505.22954]; SkillOpt [2605.23904]; self-correction negative result [2310.01798] |
| **5 Correction** | On reject: Reflexion reflection → episodic memory; periodic ExpeL distillation; on regression alarms: auto-rollback. On accept: **two-level acceptance** (§4.3) | `engine._reject`, `memory/`, `safety/rollback.py` | Reflexion [2303.11366]; ExpeL [2308.10144]; DGM backtracking |

The loop *is* the framework's public contract: `EvolutionEngine.run()` drives
generations × proposals through exactly these phases, and
`tests/golden/test_flagship_evolution.py` asserts per-proposal phase
monotonicity `proposal → design → exploration → verification → correction`
on a byte-identical golden event log.

---

## 3. Artifact store — everything improvable is versioned

`artifacts/` implements git-like semantics without git plumbing:

- **Immutable version dirs** `artifacts/<id>/vN/` — writing an existing
  version raises (`store._write_version`).
- **Append-only `lineage.jsonl`** — ops `create|update|delete|restore` with
  parent refs; rollback *appends* a `restore` entry, history is never
  rewritten (DGM backtracking semantics [2505.22954]).
- **Mutable checkout** `checkout.json` — the active agent: artifact_id →
  version. `apply_patch` materializes candidates but never activates;
  `promote()` activates only after acceptance — the empirical validation gate
  is a *structural property of the store*, not a convention.
- Verified by `tests/unit/test_store.py` (immutability, byte-identical
  rollback, lineage append-only) and `tests/unit/test_safety.py`
  (restore + deactivation semantics).

---

## 4. Evolution mechanisms

### 4.1 Archive — MAP-Elites + open-ended exploration
`evolve/archive.py`. Niches keyed by objective-supplied behavior descriptors
(coding objective: `(surface, pass_band, steps_band)`); one **elite per
cell**, ties broken by lower cost; **harmonic rank-biased** parent sampling
(weight `1/(rank+1)`, all elites selectable) plus **ε-reseeding of superseded
lineages** — individuals displaced inside their own niche by a fitter
sibling stay in history and re-enter parent sampling with probability ε
[1504.04909, 2505.22954]. Every archived individual stays selectable —
older or locally-weaker agents can seed later breakthroughs (stepping stones
[2505.22954, 1901.01753]; DGM's greedy best-parent ablation scores far
worse, §10). `parent_ref` pointers are recorded on every individual as
lineage metadata (for `rsif inspect`); the *selection* pressure toward
backtracking is the ε-reseed, not the pointers. Persisted to `archive.json`.
Verified: `tests/unit/test_evolve.py` (elitism, tie-break, frontier, rank
bias, ε-reseed from superseded, persistence).

### 4.2 Two-cadence scheduler — fast/slow loops
`evolve/scheduler.py`. Task-surface artifacts (prompt/skill/memory/module)
evolve every generation; the **META surface opens only every k-th
generation** and requires approval — the fast/slow two-cadence loop of
MetaSkill-Evolve [2607.05297]. Verified: META outside cadence → `surface`
rejection with no approval requested (`test_meta_and_module.py`).

### 4.3 Two-level acceptance — no ratcheting down
A candidate may beat its *sampled* parent (a weak elite) while still being
worse than the *active* agent. rsif separates:
- **Archive-acceptance**: `val(child) > val(parent) + θ` **with a paired
  net-gain floor** — across the val tasks, the child must beat the parent on
  at least one more task than it loses to it. On small suites a mean can
  move by threshold amounts through reshuffled noise; a sub-task improvement
  is not evidence (`selection.accept_val`). The final `rsif report` adds a
  bootstrap CI over the sealed test split.
- **Promotion**: additionally `val(child) > val(active)` → becomes the
  deployed agent.

The deployed agent can therefore never regress through weak sampled
parents. `accept` events carry `promoted`. Verified:
`test_safety_loop.py::test_two_level_acceptance_prevents_ratchet` and the
CLI demo (`g3` accepted, `promoted: false`, checkout unchanged).

### 4.4 Architecture surface — the module ABI
`runtime/module_api.py`. An agent's control loop is a module implementing
`AgentModule.step(ctx) → LLMAction|ToolAction|SubmitAction|ReflectAction`.
Modules see only `ModuleContext` — never the store or engine (ADAS search
space discipline [2408.08435]; Gödel Agent inspect/rewrite [2410.04444]).
Evolved module code passes the static scan + a real `importlib` load/ABI
check *before it is ever executed* (design-phase gates). Verified:
`test_meta_and_module.py` — a reflect-then-retry module passes
`scan → load → canary → val`, visibly changes execution (self-critique
present in retry requests), and lands in its own niche; `import os` module
rejected pre-execution.

### 4.5 META recursion — the improver improves itself, on a deferred gate
The improver's prompt template and operator catalog are themselves META
artifacts [2310.02304, 2309.16797]. A **META-only** patch leaves the agent
spec byte-identical, so gating it on the immediate agent-val comparison
would measure only noise (the M7-era test that "proved" recursion was in
fact accepting on unrelated scripted answers — corrected in the M13 review).
rsif instead runs each META edit as a controlled experiment:

1. **Provisional acceptance** on agent *non-regression* (val + canary
   unchanged), after the normal scan/surface/approval gates. One META edit
   at a time — a second while a window is open is rejected (`meta_pending`).
2. **Deferred evaluation** over `meta_eval_window` generations: the evolved
   template really formats the next generations' improver calls (asserted
   on captured requests). The window's proposal success rate is compared to
   the pre-edit baseline.
3. **Confirm or revert**: worse than baseline (or zero wins with no
   baseline) → the pre-edit META versions are restored (append-only
   `restore` lineage, `meta_revert` event); otherwise `meta_confirm`.

Mixed patches (META + an agent surface) take the normal strict val gate —
the agent-visible part must pay for the whole patch. Approval is
**fail-closed**: no approver wired or denied → rejection. Verified:
`test_meta_and_module.py` (provisional accept → revert-on-bad-window with
the original template provably re-used afterwards; confirm-on-winning-window;
`meta_pending`).

### 4.6 Memory — three layers
`memory/`:
- **Episodic reflections** (Reflexion [2303.11366]): every rejection
  produces a reflection; retrieved per-task by lexical TF-IDF.
- **Distilled insights** (ExpeL [2308.10144]): distilled from **verified
  successes only**, with provenance and usage-based retirement — the
  hallucination guard of model-collapse findings [2510.16657].
- **Curated playbook** (ACE [2510.04618]): the assembled context evolves
  only via bounded, acceptance-gated section ops.
Verified: `tests/unit/test_memory*.py` (retrieval ranks similar over
dissimilar; distill/retire; playbook rejects unbounded rewrites).

---

## 5. Safety

| Mechanism | Code | Reference | Test |
|---|---|---|---|
| Hard budget (calls / USD / wall) checked before every proposal **and after every recorded call** — overshoot is bounded to one call, not one proposal; clean abort, no partial proposals | `safety/budget.py`, engine | cost blowout risk [2506.13131] | `test_safety_loop.py` |
| Drift monitor: canary/active regression → **auto-rollback** to archive best (`restore` lineage, extras deactivated); stagnation → approval-or-stop | `safety/drift.py`, `safety/rollback.py` | misevolution [2509.26354, 2603.06333] | `test_safety.py`, `test_safety_loop.py` |
| Human approval for META edits and drift continuation (`CLIApprover`, fail-closed on EOF/non-tty) | `safety/approvers.py` | AutoHarness guard layers [2603.03329] | `test_meta_and_module.py` |
| Static scan: **import whitelist** for evolved code (curated pure stdlib + `rsif.runtime.module_api` only), before execution. Honest boundary: MODULE code is exec'd in-process behind this scan; a blacklist would be bypassable via transitive imports (`from rsif.commands import os`) | `sandbox/guards.py`, engine design gates | [2603.03329] | `test_sandbox.py`, loader tests |
| Sandbox: subprocess `python -I`, temp cwd, wall/CPU timeouts, rlimits, **minimal environment (PATH only — no secrets)** — one code path for agent code, skill execution, and unit-test scoring. Residual limitation: network egress from the child is not blocked (no seccomp on macOS); the scrubbed env removes the exfiltration prize, not the socket | `sandbox/exec.py` | — | `tests/unit/test_sandbox*.py` |

Misevolution is treated as *expected*, not exceptional [2509.26354].

---

## 6. Determinism & reproducibility

- Explicit `random.Random(seed)` threading; no global RNG.
- Event payloads carry only ids/scores/decisions — never wall-times or
  sandbox stderr (temp paths would leak into goldens).
- Evaluation memoization by `(mapping, split, task-ids)`; a candidate suite
  is evaluated exactly once per run.
- Golden test: a full 2-proposal run reproduces `events.jsonl` /
  `archive.json` / `checkout.json` / `lineage.jsonl` **byte-identically**
  across processes (`tests/golden/`; regen deliberately with
  `RSIF_UPDATE_GOLDEN=1 pytest`).
- Offline guard: the test suite blocks `socket.socket` — accidental network
  calls fail loudly.
- With `seed.json` + the LLM disk cache (`llm/cache.py`), a real-provider
  run is replayable.

---

## 7. Objectives — the task-agnostic seam

`Objective` protocol (`objectives/base.py`): `suites()`, `evaluate(task,
attempt)`, `fitness(scorebook)`, `behavior_descriptors(scorebook)`,
`canaries()`; splits `train|val|test|canary` — **train selects, val
accepts** [2605.23904], test stays sealed until `rsif report` (bootstrap CI
guards lucky-task claims [2510.16657]). The engine never imports a concrete
objective (`objectives/objective_from_config` is the only instantiation
site). Ships with `CodeTasksObjective` (hidden-test-scored function tasks in
a sandbox); `examples/custom_objective.py` + the second built-in objective
prove the seam (M11).

Providers are equally pluggable: a 3-method `LLMProvider` protocol with
capped Anthropic/OpenAI/LiteLLM adapters (`llm/`), a `ScriptedProvider`
test seam, and a content-addressed offline `DemoProvider` (`llm/demo.py`)
that runs the whole CLI lifecycle deterministically with no network.

---

## 8. Observability

`events.jsonl` is the backbone: kinds
`proposal|patch|screen|eval|gate|accept|reject|reflect|archive_update|rollback|budget|llm_call|approval|run_start|run_end|error|meta_confirm|meta_revert`,
each phase-attributed. It is (a) what `rsif status/inspect` render,
(b) what reflections/insights read, (c) the replay source. CLI:
`init/run/evolve/status/inspect/rollback/report` (`rsif --help`); rendering
is timestamp-free so outputs are diff-stable.

---

## 9. Non-goals (v1)

No weight training; no distributed eval pool; no Docker/VM sandbox (macOS
process sandbox instead); no web UI; no embeddings/external retrieval
services; the evolution engine itself is not an editable artifact (only
improver templates/operators are, via the META surface).

---

## 10. Citation spot-checks against local PDFs

Six load-bearing mechanism claims were spot-checked against the PDFs in
`resources/` on 2026-09-20 (each read from the local PDF; quotes shortened,
page numbers as read). Verdicts: **5 confirmed, 1 partial** — and the
partial one surfaced a real design distinction, recorded below.

### 10.1 DGM — Darwin Gödel Machine [2505.22954] — archive, empirical selection, fixed outer loop
- **Archive + ancestor re-selection: CONFIRMED.** "the DGM maintains an
  archive of discovered solutions during the search, facilitating
  open-ended exploration rather than relying on evolving a single solution"
  (p.4); archived solutions "serve as stepping stones … much later than
  their original discovery" (p.5). *Nuance:* the paper never frames this as
  "backtracking when stuck" — every agent gets non-zero selection
  probability as an always-on property of open-ended exploration. rsif's
  design doc was reworded accordingly (§4.1).
- **Empirical validation gate: PARTIAL — an important distinction.** DGM
  empirically validates self-modification against benchmarks ("Instead of
  requiring formal proofs, we empirically validate self-modifications
  against a benchmark", p.2), but *archive admission* only requires a valid,
  evaluated child ("Only agents that compile successfully … are added",
  p.4) — the improvement gate lives at **selection**. rsif is deliberately
  stricter, following SkillOpt (§10.2): admission to a niche requires
  beating the sampled parent on held-out val, and *deployment* additionally
  requires beating the active agent (two-level acceptance, §4.3).
  Evaluation in DGM is staged (10 → 50 → 200 tasks, p.6) — rsif's screen →
  full train → val cascade is the same shape.
- **Agent rewrites its own code; outer loop fixed: CONFIRMED.** "modifying
  the design of an agent's own components (i.e., its own code, which does
  *not* include the open-ended exploration process…)" and "the open-ended
  exploration process (i.e., archive maintenance, parent selection) is
  fixed and not modifiable by the DGM" (pp.4–5) — precisely rsif's trust
  boundary (§1). Bonus: DGM's greedy "always pick best parent" ablation
  scores 39.7% vs 50.0% SWE-bench (App.) — independent evidence for rsif's
  rank-biased roulette that keeps every elite selectable.

### 10.2 SkillOpt [2605.23904] — held-out acceptance: CONFIRMED
"an edit is accepted only when it strictly improves a held-out validation
score" (abstract); "The training split supplies experience, the selection
split gates updates, and the test split is used only for final reporting"
(p.5); Figure 2 labels the test split "locked until final report". This is
exactly rsif's train-selects / val-accepts / test-sealed-until-report
discipline (§7), including strict (`>`, not `≥`) acceptance.

### 10.3 Reflexion [2303.11366] — reflect → episodic memory → better retries: CONFIRMED
"Reflexion agents verbally reflect on task feedback signals, then maintain
their own reflective text in an episodic memory buffer to induce better
decision-making in subsequent trials" (abstract); "not by updating weights,
but instead through linguistic feedback" (p.1). *Adaptation, noted
honestly:* Reflexion's retrieval is whole-buffer (capped at 1–3, most
recent first) within one task's trial loop; rsif generalizes to multi-task
evolution with TF-IDF retrieval across reflections, and its reflection
input is the rejection verdict (external, execution-grounded feedback) —
not pure self-reflection.

### 10.4 MAP-Elites [1504.04909] — descriptor cells, one elite each, elite-sampled parents: CONFIRMED
"MAP-Elites will search for the highest performing solution for each cell
in the N-dimensional feature space" (p.3); "we keep the best one found per
cell" (p.6); "A cell in the map is randomly chosen and the genome at that
cell produces an offspring" (p.3); stepping stones "provide … high-performing
solutions … that may not have been discovered had search been trying to
increase performance by searching only in that region" (p.6).
*Deliberate deviation:* MAP-Elites samples parents uniformly; rsif uses
harmonic rank-biased sampling (weight 1/(rank+1)) — between uniform and
greedy, informed by DGM's greedy-parent ablation (§10.1). Cell replacement
is strictly-greater, matching rsif's elitist `add()`.

### 10.5 Promptbreeder [2309.16797] — two-level self-referential mutation: CONFIRMED
"the mutation of these task-prompts is governed by mutation-prompts that
the LLM generates and improves through evolution in a self-referential way
… not just improving task-prompts, but it is also improving the
mutation-prompts that improve these task-prompts" (abstract); formalized as
`P' = LLM(M + P)` and `M' = LLM(H + M)` (p.5). rsif's META surface
(evolvable improver templates + operator catalogs) is exactly this second
level, under approval gates (§4.5).

### 10.6 Self-correction negative result [2310.01798] — execution-grounded verification: CONFIRMED
"LLMs struggle to self-correct responses without external feedback, and at
times, their performance even degrades after self-correction" (abstract;
per-model tables show e.g. Llama-2 GSM8K 62.0 → 36.5); "when valid external
feedback is available, it is beneficial to leverage it properly" (p.8), with
unit tests / code executors named as verifiers. This is why rsif's
acceptance signal is **only** sandbox-executed evaluation (hidden tests,
canaries, val split); LLM self-critique (ReflectAction, reflections) is
advisory context — never an acceptance gate (§2, phase 4).

### 10.7 Verification method note
Spot-checks were performed by reading the local PDFs (`resources/*.pdf`)
with page-level reads; each verdict above carries its quote and page. The
distinction surfaced in §10.1 (admission vs selection gating) is the only
place a claim needed correction rather than confirmation — and rsif's
behavior was already on the strict side of it.
