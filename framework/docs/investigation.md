# rsif Implementation Investigation — Details & Design Points

A code-level walkthrough of what actually exists in `src/rsif/`, the design
point each mechanism serves, and the evidence that it works. This is the
investigation counterpart to `docs/design.md` (which carries the citation
map): here every claim is anchored to a file and a test, and validated by a
**third real project** (`projects/regex_agent/`) that was built through the
public seams only and run against a live model.

Status: post-M13 (external review fixes). 119 offline tests + live runs.

---

## 1. Trust boundary — the engine is frozen, the agent is data

**Implementation.** `evolve/engine.py` (`EvolutionEngine`) and everything it
imports directly (`artifacts/`, `safety/`, `evolve/selection|archive`) are
trusted process code; the agent's entire configuration — module code,
prompts, skills, memory, improver templates — lives in the `ArtifactStore`
as versioned *data*. The runtime ABI (`runtime/module_api.py`) is the only
surface evolved code touches: `ModuleContext` exposes task, session, tools,
step counters — never the store, engine, or provider.

**Design point.** DGM/ADAS-style self-modification without the runaway risk:
an evolved artifact cannot structurally break its own selection loop in v1
[2505.22954, 2408.08435, 2410.04444]. The improver-improves-itself axis is
not sacrificed — it runs through META artifacts under stricter gates (§5).

**Honest boundary (post-M13).** MODULE code is exec'd in-process behind the
import whitelist (`sandbox/guards.py`, `runtime/loader.py`); SKILL code runs
in the subprocess sandbox. Network egress from the sandbox child is not
blocked; the scrubbed environment removes the exfiltration prize.

**Evidence.** `test_meta_and_module.py` (module edits gated, `import os`
rejected pre-execution), `test_sandbox.py` (whitelist incl. transitive
escapes, env scrubbing).

---

## 2. Artifact store — everything improvable is versioned

**Implementation.** `artifacts/store.py`: immutable `artifacts/<id>/vN/`
dirs (rewriting raises), append-only `lineage.jsonl`
(`create|update|delete|restore`), mutable checkout manifest
(`checkout.json`). `apply_patch()` materializes candidate versions
**without activation**; `promote()` activates only after acceptance;
`restore()` appends — history is never rewritten.

**Design point.** The empirical validation gate is a *structural property
of the store*, not a convention: there is no code path from "candidate
written" to "agent changed" that bypasses acceptance [2505.22954, 2605.23904].

**Evidence.** `test_store.py` (immutability raises; rollback restores
byte-identical; lineage append-only with parent refs); the flagship golden
run (a rejected candidate's v3 exists on disk but never reaches checkout).

---

## 3. The five-phase loop

**Implementation.** `engine._one_proposal` — every event is
phase-attributed (`observe/events.py`):

| Phase | Code path | Guard |
|---|---|---|
| 1 proposal | `evolve/proposer.py` — Improver over the ACTIVE META template; prompt = checkout summary + archive frontier + superseded lineages + lessons | scheduler (`evolve/scheduler.py`) closes surfaces; META needs approval |
| 2 design | bounds (`max_patch_ops`) + operator-catalog validation + `apply_patch` + **static scan / module-load gates before any execution** | `sandbox/guards.py`, `runtime/loader.py` |
| 3 exploration | cascade screen on sampled train tasks (`selection.pass_screen`, `child ≥ parent − ε`) | cheap: a far-below-parent candidate never reaches expensive gates [2506.13131] |
| 4 verification | canary (`child ≥ parent`) → train → **val acceptance** (§4) | execution-grounded only [2310.01798] |
| 5 correction | accept → promote/archive/insight; reject → reflection + discard (`rollback` event, checkout unchanged) | Reflexion [2303.11366], ExpeL [2308.10144] |

**Evidence.** `tests/golden/test_flagship_evolution.py` asserts per-proposal
phase monotonicity on a byte-identical golden log; the regex project's
offline test asserts the same phases on a third objective.

---

## 4. Acceptance machinery — four layers

**Implementation.** `evolve/selection.py` + engine:

1. **Paired net-gain floor** (M13): `accept_val` requires the child to beat
   the parent on ≥1 net val *task*, not just a mean threshold — on small
   suites a mean can move by threshold amounts through noise.
2. **Canary gate**: canaries never regress (hard reject).
3. **Two-level acceptance** (M8): *archive-acceptance* (beats its sampled
   parent → enters its MAP-Elites niche as a stepping stone) is separate
   from *promotion* (must also beat the ACTIVE agent). The deployed agent
   cannot ratchet down through weak sampled parents.
4. **META eval window** (M13): a META-only patch leaves the agent
   byte-identical, so it is accepted provisionally on non-regression and
   judged by its proposals' success rate over `meta_eval_window` (default 3)
   generations → `meta_confirm` / `meta_revert` (append-only restore).
   One META experiment at a time (`meta_pending`).

**Design point.** Every accept/reject decision is execution-grounded and
noise-aware; the one signal that *cannot* be measured immediately (improver
quality) is measured on the timescale where it exists [2605.23904, 2310.01798,
1504.04909, 2310.02304].

**Evidence.** `test_safety_loop.py` (ratchet test, budget, provider
errors), `test_meta_and_module.py` (provisional→revert with the original
template provably re-used; confirm-on-win; pending guard), `test_cli.py`
(demo story 0.4 → 0.6 → 1.0 + non-promoted 0.9 stepping stone).

---

## 5. Archive — quality-diversity that actually pressures exploration

**Implementation.** `evolve/archive.py`: niches keyed by
objective-supplied behavior descriptors; one elite per cell (ties → lower
cost); **harmonic rank-biased** parent sampling (`1/(rank+1)`, every elite
selectable); **ε-reseeding from superseded lineages** — individuals
displaced in their own niche re-enter parent sampling with probability 0.2.

**Design point.** Keep rare/older/weaker agents in play: stepping stones
[1901.01753], DGM's greedy-best-parent ablation losing ~10 points on
SWE-bench is the independent evidence for non-greedy parent choice
[2505.22954].

**Correction on the record (M13).** The originally documented
"ε-underfilled-niche reseeding" was provably inert (cells never shrink ⇒
the underfilled set is always empty); `parent_ref`-based re-seeding was
never wired. The current superseded-reseeding is real and tested; `parent_ref`
remains lineage metadata only.

**Evidence.** `test_evolve.py` (elitism, tie-break, frontier order, rank
bias, ε-reseed firing, persistence).

---

## 6. Memory — three layers, honestly thin

**Implementation.** `memory/episodic.py` (Reflexion-style reflections on
every rejection, retrieved by lexical TF-IDF), `memory/insights.py` (ExpeL
distillation from verified successes only, provenance + usage-based
retirement), `memory/playbook.py` (ACE-style bounded section ops on the
assembled context), `memory/retrieve.py` (hand-rolled TF-IDF + stemmer
behind a Retriever protocol).

**Design point.** Verified-trajectory-only distillation guards against
insight collapse [2510.16657]; bounded playbook ops guard context bloat
[2510.04618].

**Known limitation (open, L2).** Rejection reflections are built from ids +
scores + gate reasons — not full task trajectories — so the *informational
content* of memory is low even though the machinery is correct. Feeding
real failing traces is the highest-value next improvement.

**Evidence.** `test_memory*.py` (retrieval ranks similar over dissimilar;
distill/retire; playbook rejects unbounded rewrites).

---

## 7. Runtime & the module ABI — architecture as evolvable code

**Implementation.** `runtime/runtime.py` interprets an `AgentSpec`
(assembled by `evolve/assembler.py` from a version mapping): system prompt,
skills-as-tools, memory text, module code. `module_api.py` defines
`AgentModule.step(ctx) → LLMAction | ToolAction | SubmitAction |
ReflectAction`. Skills execute via `runtime._run_skill` in the sandbox with
execution feedback appended to the session [2305.16291].

**Design point.** Architecture search happens inside a fixed envelope
[2408.08435]; `ReflectAction` is advisory context only — self-critique is
never the accept signal [2310.01798].

**Known limitation (open, L3).** The behavior descriptor's pass-band
component partially encodes fitness (a QD anti-pattern); diversity pressure
is weaker than the MAP-Elites framing suggests.

**Evidence.** `test_runtime.py`, `test_meta_and_module.py` (evolved
retry-reflect module visibly changes the request stream: self-critique in
retry calls).

---

## 8. Safety stack — misevolution as the expected case

**Implementation.**
- **Budget** (`safety/budget.py`): hard caps on calls/USD/wall-clock,
  checked before each proposal *and after every recorded call* (M13:
  overshoot bounded to one call). `BudgetExhausted` propagates through the
  runtime (never scored as a 0-valued attempt).
- **Drift monitor** (`safety/drift.py`): generation-end canary/active
  regression → auto-rollback to archive best (`safety/rollback.py`,
  restore-lineage, extras deactivated); stagnation → approval-or-stop.
- **Approvals** (`safety/approvers.py`): `CLIApprover` for META edits and
  drift continuation; fail-closed without a TTY.
- **Provider errors** (`llm/base.py:ProviderError` with `origin`): clean
  abort with `run_end.stop_reason="error:<Origin>"`; engine bugs are
  distinguished as `engine:<Type>` (M13).
- **Static scan** (`sandbox/guards.py`): import **whitelist** (pure stdlib
  + `rsif.runtime.module_api`).
- **Sandbox** (`sandbox/exec.py`): `python -I`, temp cwd, CPU/wall
  timeouts, rlimits, PATH-only environment.

**Design point.** Guard layers before execution, rollback that never
rewrites history, and budgets that cannot be argued with [2603.03329,
2509.26354, 2603.06333, 2506.13131].

**Evidence.** `test_safety.py`, `test_safety_loop.py` (all seven,
including the one-call-overshoot abort), `test_sandbox.py`.

---

## 9. Determinism engineering

**Implementation.** Explicit `random.Random` threading; scripted/demo
providers (`llm/mock.py`, `llm/demo.py` — content-addressed by role +
request text); eval memoization keyed on `(mapping, split, task-ids)`;
disk-cached real providers (`llm/cache.py`); event payloads carry only
ids/scores/decisions; timestamp-free rendering.

**Design point.** A self-improvement loop whose *acceptance decisions*
cannot be replayed is unfalsifiable. Byte-identical goldens make every
accept/reject auditable after the fact.

**Evidence.** The golden test reproduces `events.jsonl` /
`archive.json` / `checkout.json` / `lineage.jsonl` byte-identically across
processes; `test_cli.py` asserts cross-process event-stream equality on the
demo.

---

## 10. The task-agnostic seam — three objectives, zero engine changes

**Implementation.** `objectives/base.py: Objective` protocol — `suites()`,
`evaluate(task, attempt)`, `fitness(scorebook)`,
`behavior_descriptors(scorebook)`, `canaries()`. The engine imports no
concrete objective (a structural guard test asserts this on the engine's
source). Built-ins: `code-tasks` (sandboxed hidden tests), `exact-match`
(plain-text equality).

**Third real proof — `projects/regex_agent/`** (this investigation's
validation project): a custom `RegexObjective` (produce a pattern matching
given positives/negatives; graded by compiling and executing `re` in the
sandbox), driven through the `EvolutionEngine` API against a live gateway
model, plus a deterministic offline test (`tests/integration/
test_regex_project.py`) showing val 0.2 → 0.4 → 1.0 through two accepted
prompt edits. Building it required **one** core change: `RunConfig`'s
closed objective-name set (a config-level contradiction of the
task-agnostic claim) was relaxed to any non-empty name — recorded in the
decision log. The project's solvability invariant caught one badly
designed task before it could poison scoring (`colou?r` vs "colorr"),
the same class of bug the M13 suite-growth caught.

**Live gateway run (2026-09-21, glm-5.3-flash, 29 calls, exit 0):**
baseline train 1.0 / canary 1.0 / **val 0.6** (a real generalization gap);
both real-improver proposals were **correctly rejected at the cascade
screen** (train 0.5 and 0.0 vs parent 1.0), the g1 reflection visibly
shaped the g2 proposal, no ratchet (active stayed at seed), sealed test
0.5 on the archive best. The run also surfaced a genuine emergent
interaction: prompt strategies that add "verify before answering"
discipline make the model emit prose first, breaking the objective's
first-line extraction contract — the gates kept that regression from ever
deploying (details in `projects/README.md`).

**Evidence.** `test_task_agnostic.py` (exact-match + arithmetic custom
objective + structural guard), `test_regex_project.py` (this project).

---

## 11. Known limitations (open, accepted)

| # | Limitation | Where |
|---|---|---|
| M2 | Eval memo ignores memory-store content: children are scored with current memory, memo-hit parents with old memory (comparability vs staleness trade-off, undocumented at the gate) | `engine._evaluate` |
| M3 | The improver sees the ACTIVE checkout summary but patches overlay the sampled PARENT snapshot — content-aware edits on non-active parents are composed blind | `proposer.py`, `engine._one_proposal` |
| M4 | "Bounded edits" bounds op count, not diff size — one replace can swap an entire prompt | `store.apply_patch` |
| L2 | Reflections carry ids/scores, not trajectories — memory content is thin | `engine._reject` |
| L3 | Behavior descriptor partially encodes fitness (pass band) | `objectives/base.py` |
| — | Sandbox network egress unblocked; module code in-process behind the whitelist | `sandbox/` |

---

## 12. Evidence index

- Offline suite: `uv run pytest -q` — 119 passed (deterministic, no network).
- Golden: `tests/golden/` — byte-identical reproduction across processes.
- Live smoke (M10): glm-5.3-flash via the gateway; loop + budget + gate
  order verified on real completions.
- Real project (M14): `projects/regex_agent/` — offline deterministic
  improvement test (val 0.2 → 0.4 → 1.0) **and** a live gateway run
  (baseline val 0.6; two plausible regressions correctly rejected at the
  screen; 29 calls; no ratchet) — full record in `projects/README.md`.
