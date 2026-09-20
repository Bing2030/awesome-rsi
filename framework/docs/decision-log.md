# rsif Decision Log

The framework's own design-loop correction record: every meaningful design
decision, deviation, or fix made during implementation, with rationale.
(Newest entries at the bottom.)

## Format

- **Date / milestone** — decision — why — grounding

## Entries

- **M0 / 2026-09-20** — Checkout is a manifest (`checkout.json`: artifact_id →
  version), not copied files. Immutable version dirs are read by reference.
  Why: same git-like semantics with less I/O and no copy drift; snapshots are
  trivially serializable for the archive.
- **M0 / 2026-09-20** — `apply_patch` never activates candidates; a separate
  `promote()` runs only after acceptance. Why: makes the empirical validation
  gate a structural property of the store, not a convention. [2505.22954, 2605.23904]
- **M0 / 2026-09-20** — Meta.json `accepted` flag mutates on promote even though
  payload versions are immutable; `content_hash` covers payload files only.
  Why: acceptance is bookkeeping about a version, not the version's content.

## M6 — Evolution engine v1
- **Phase mapping implemented as decided**: propose (Improver over META template) → design (bounds+operator validation, `apply_patch` materializes candidate versions *without* activation) → exploration (screen on train-probe tasks, `child ≥ parent − ε`) → verification (scan → canary → train → val acceptance `child > parent + θ`) → correction (promote+archive / reflect+discard). Every event carries its phase.
- **Rejection = discard, not promote-then-rollback**: candidates are never activated before acceptance, so a rejected proposal's "rollback" is a recorded no-op (`rollback` event, `checkout_unchanged=true`); genuine `Restore` rollbacks remain wired for canary regressions (M8). Keeps the acceptance gate honest — a bad candidate can never leak into the active agent.
- **Archive parent sampling**: harmonic rank-biased roulette (weight 1/(rank+1)) over the frontier + ε-reseeding of lost niches. Replaced top-half truncation — truncation gave zero bias for small archives (caught by a unit test) and excluded half the niches.
- **Determinism**: event payloads contain only ids/scores/decisions — never wall-times or sandbox stderr (temp paths leak into tracebacks). Parent/candidate evaluations are memoized by (mapping, task-ids); with the same seed a full two-proposal run reproduces `events.jsonl`/`archive.json`/`checkout.json`/`lineage.jsonl` byte-for-byte (golden committed at `tests/golden/golden_events.jsonl`, regen: `RSIF_UPDATE_GOLDEN=1`).
- **Agent-side memory in M6**: system prompt + skills + playbook (via `build_spec`); reflections/insights feed the *improver* and are retrieved per-task into agent context via `_agent_memory`. Insight `uses` counters therefore advance during evaluation — deterministic, and exercises ExpeL use-tracking.

## M7 — Architecture surface, META recursion, scheduler
- **Two real bugs caught by M7's tests**: (1) `runtime._llm` never sent `session.system` — the evolved PROMPT artifact would silently not reach a real provider (scripted tests masked it because they match on task text). Fixed: system prompt is always prepended. (2) Static gates ran *after* the screen, so a broken module was executed during screening before rejection. Fixed: scan+load are design-feasibility gates that precede ANY evaluation.
- **Module-load gate**: patches touching MODULE artifacts must `load_module_source` cleanly (ABI + static scan) before evaluation; emitted as `gate: load` in phase `design`.
- **Two-level acceptance (designed in M7, landing in M8)**: sampled-parent acceptance alone permits a ratchet — a candidate can beat a weak sampled parent while being worse than the active agent. Fix: archive-acceptance (beats its parent, enters its MAP-Elites niche as a stepping stone) is separated from promotion (must also beat the active agent's val).
- **META gate order**: scheduler closes the surface *before* approval is requested (out-of-cadence META → `surface` rejection, no approval event); in-cadence META without a wired approver is fail-closed denied.
- **Recursion evidence**: after an approved template mutation, the next generation's improver request provably contains the evolved template text (asserted on captured provider calls).

## M8 — Safety hardening
- **Two-level acceptance landed**: (a) archive-acceptance — beats its sampled parent, enters its MAP-Elites niche (stepping stones stay available [1901.01753]); (b) promotion — must also beat the *active* agent. This closes the ratchet hole where a candidate beating a weak sampled parent could deploy a worse agent. `accept` events carry `promoted`; non-promoted accepts keep the active checkout.
- **Budget**: `_EventfulProvider` records every completion (calls/tokens/USD estimate via configurable per-Mtok prices); the run checks before each proposal and aborts cleanly with a `budget` event + `run_end.stop_reason` — no partial proposals.
- **Drift monitor** (per generation end, execution-grounded): `canary_regression` / `active_regression` → auto-rollback to archive best; `stagnation` (N consecutive rejections) → explicit approval required to continue, else clean stop. With the promotion gate, active regression is structurally impossible — the monitor is defense-in-depth (and testable by direct invocation, like a manual fire-pull).
- **Auto-rollback semantics**: restore appends `restore` lineage entries (never rewrites); artifacts absent from the target snapshot are deactivated (v0, files kept) via delete-lineage + checkout removal.

## M9 — CLI + observability
- **DemoProvider is content-addressed** (role + request text), unlike the strict-FIFO `ScriptedProvider` used by the golden tests. The demo agent's ability is a function of (task function, `STRATEGY-LEVEL: n` marker in the active system prompt), so prompt evolution demonstrably changes agent behavior and the script survives any change in evaluation order. Demo story: baseline val 0.6 → level-2 0.8 (promoted) → level-3 1.0 (promoted) → level-4 0.8 accepted as stepping stone, NOT promoted.
- **`rsif run`/`report` reuse the evolve-time evaluation path** via new public `engine.evaluate_active/evaluate_snapshot` (spec assembly, memory injection, memoization, persisted scorebooks, `eval` events) instead of a parallel scorer — CLI scores are directly comparable to evolve-time scores, and out-of-loop evaluations land in the same event log.
- **`rsif report` unseals the sealed test split** on the archive-best snapshot with a seeded bootstrap CI [2510.16657 guard against lucky-task claims]. The unseal event is visible as `eval label=report-test`.
- **Approver wiring**: `CLIApprover` is attached only when stdin is a TTY; non-interactive runs are fail-closed for META edits (consistent with M7's fail-closed default). The scripted demo proposes no META edits.
- **`objective_from_config` factory** added as the single place objectives are instantiated; `exact-match` branch lands in M11.
- **Rendering is timestamp-free** (seq/kind/phase/generation/payload only) so `status` output is snapshot-testable and diff-stable.

## M10 — Design doc, live smoke, PDF citation spot-checks
- **PDF spot-checks (6 claims vs local PDFs)**: 5 CONFIRMED, 1 PARTIAL. The partial is load-bearing: DGM [2505.22954] empirically gates **selection**, but *archive admission* only requires a valid, evaluated child — rsif is deliberately stricter (admission requires beating the sampled parent on held-out val, per SkillOpt [2605.23904] strict held-out acceptance). DGM's greedy-best-parent ablation (39.7% vs 50.0% SWE-bench) is independent evidence for the harmonic rank-biased roulette that keeps every elite selectable. Reflexion nuance recorded honestly: paper retrieval is whole-buffer per task; rsif generalizes with cross-task TF-IDF.
- **Two live-path bugs caught only by running a real provider**: (1) the current Anthropic SDK rejects `temperature` on `messages.create` — adapter now probes the client signature once and sends it only when accepted (also covers Anthropic-protocol proxies); (2) the autouse offline socket-guard blocked live tests — `live`-marked nodes are now exempt (opt-in network stays a deliberate choice).
- **Live smoke verified** (glm-5.3-flash via Anthropic-protocol gateway, ~$1/60-call caps): the loop drove a real model through baseline + one full proposal in 7m10s; budget held; any accepted proposal provably passed canary→val gates in order; accepted-or-correctly-rejected are both treated as success (machinery is the claim, not guaranteed improvement).
- **Environment incident**: mid-M10, macOS TCC revoked the session's `~/Documents` access (EPERM for shell and file tools). Files were intact; work resumed after the user restarted the terminal. Recorded here because the framework directory was then untracked in git — a single-process permission glitch could have cost the whole afternoon's work.

## M11 — Task-agnosticism proof
- **Two more objectives, zero engine changes.** `exact-match` (plain-text equality, no code fence/sandbox) and `examples/custom_objective.py` (arithmetic, integer answers) both improve 1/3 → 1.0 held-out val through the *identical* `EvolutionEngine.run()` path. The proof is behavioral: three distinct evaluation surfaces (code fences → bare text → integer strings) over the same store/archive/safety/runtime. A structural guard (`test_engine_has_no_concrete_objective_dependency`) asserts `rsif/evolve/engine.py` source never names a concrete objective — the seam is enforced, not convention.
- **DemoProvider is objective-aware**: `DemoProvider(objective=...)` selects the agent character (code-tasks solutions vs exact-match Q&A) while sharing the improver/reflector roles and the `STRATEGY-LEVEL` ability-gating mechanism. `_provider` passes `cfg.objective` through, so `rsif init --objective exact-match && rsif evolve` works offline end-to-end.
- **The `Objective` protocol is the whole contract**: `suites()` (train/val/test/canary), `evaluate(task, attempt)`, `fitness(scorebook)`, `behavior_descriptors(scorebook)`, `canaries()`. Nothing else is objective-specific — the engine calls `build_spec` (surface-agnostic spec assembly) and the runtime's generic `run(task_prompt, spec)`.

## M12 — Overall review & optimization
- **Provider-error clean abort (queued M11 finding, fixed).** A real gateway `RateLimitError` mid-baseline previously crashed `cmd_evolve` with a traceback, because the runtime's broad `except Exception` swallowed the provider error into a failed Attempt (score 0) and then the improver/reflector calls raised. Fix: `ProviderError` (in `llm/base.py`) carries an `origin` type name; `_EventfulProvider` normalizes any non-`ProviderError` inner exception into one; the runtime re-raises `ProviderError` (never scores 0 on a provider failure); the engine catches it in `run()` and aborts cleanly — `error` event + `run_end.stop_reason="error:<Origin>"`. `cmd_run`/`cmd_report` surface it as a CLI error (exit 2). Verified by `test_safety_loop.py::test_provider_error_aborts_cleanly` (`error:ConnectionError`).
- **Design↔implementation audit — 4 over-promises reconciled (docs corrected, code left as-is — the implementation is the intended simplification).** (1) No `skills/` package: skills are first-class `SKILL` artifacts assembled by `evolve/assembler.py`, exposed as tools by `runtime._tool_specs`, executed via `runtime._run_skill` through the sandbox — admitted by the static-scan gate, with no self-test admission gate and no lexical tool selection in v1. (2) No `safety/gates.py`: the ordered gate chain lives in `evolve/selection.py` (`pass_screen`/`accept_val`/`pass_canary`) + `sandbox/guards.py` (static scan) + engine inline. (3) No `observe/cost.py`: cost tracking is `safety/budget.py` (Budget + per-call usage) + `observe/render.py` (token sums in `status`). (4) "skill/memory retrieval" in the architecture diagram → memory retrieval only. README layout, `design.md` (self-test admission, skill-retrieval, sandbox one-code-path lines), and a Part-B reconciliation note in `plan.md` now state the real structure.
- **Code-review pass**: no dead code (every helper — `EchoProvider`, `extract_code_fence`, `canonical_request_key`, `bootstrap_ci` — is referenced), no TODO/FIXME/debug prints, `compileall` clean. No functional changes required beyond the provider-error fix.
- **Demo event-log walkthrough** (scripted, seed 0, deterministic): `run_start → eval(baseline) → archive_update(seed)`; per proposal the phases are attributed `proposal → design(patch+gate) → exploration(eval+screen) → verification(eval+gate) → correction(accept/reflect)`. 3 accepted / 3 rejected; best fitness 1.0; `report` unseals test split 5/5 CI [1.0, 1.0]. Reproduces the M9 story (0.6 → 0.8 → 1.0, third accept non-promoted).
