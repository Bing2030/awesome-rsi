# rsif Implementation Plan — Status Tracking

> The full approved plan lives in this file below the status table.
> Status legend: ⬜ todo · 🔄 in-progress · ✅ done (with verification evidence) · ⏸ deferred

| # | Milestone | Status | Verification result | Notes |
|---|-----------|--------|---------------------|-------|
| M0 | Scaffold + tracked plan doc | ✅ | `pytest` 24 passed; `rsif --help`/`--version` exit 0; `rsif init` creates full layout + 5 seed artifacts | — |
| M1 | Artifacts & lineage | ✅ | unit: version immutability raises; rollback restores byte-identical; lineage append-only w/ parent refs; patch JSON roundtrip | — |
| M2 | LLM layer (Protocol, mocks, cache, adapters) | ✅ | 33 passed: scripted role queues pop/match; cache hit identical + no inner call; anthropic/openai adapter serialization via stubbed clients (offline) | — |
| M3 | Sandbox + code-tasks objective | ✅ | 47 passed: infinite loop killed at timeout; mem hog killed; `os.system`/`subprocess`/framework-import flagged; known-good→1.0 / known-bad→0.0 deterministically | task packs generated via `scripts/gen_seed_tasks.py` (21 tasks) |
| M4 | Runtime + module ABI | ✅ | 52 passed: scripted agent solves 3 tasks via objective; trace+usage recorded; loader rejects non-ABI & forbidden-import sources; custom module drives the loop with zero LLM calls | — |
| M5 | Memory (episodic / insights / playbook) | ✅ | 65 passed: TF-IDF ranking (+minimal stemmer); reflection retrieved for similar task not dissimilar; insight distill/retire/use-counting; playbook rejects unbounded & overflow patches | added minimal stemmer to lexical retrieval (decision-log) |
| M6 | Evolution engine v1 + flagship deterministic test | ✅ | 83 passed: flagship — A accepted (val 0.40→0.80, promoted+archived), B rejected on val (rollback event + reflection, checkout keeps A); golden `events.jsonl` byte-identical across processes & reruns; unit: proposal parsing, MAP-Elites elitism/tie-break/persistence, gate edges, assembler overlay | parent sampling = harmonic rank-biased roulette (all niches selectable; decision-log) |
| M7 | Architecture surface + META recursion + scheduler | ✅ | 89 passed: retry-reflect module edit passes scan→load→canary→val gates, self-critique visible in retry requests, archived in its own niche; broken module (`import os`) rejected pre-execution; META edit denied by approver fails closed, approved edit is used by the *next* generation's improver (recursion proven); META closed outside slow-loop cadence | runtime fix: evolved system prompt now actually sent to provider; static gates moved before screening (decision-log) |
| M8 | Safety hardening (gates, drift, budget, approvers, rollback) | ✅ | 99 passed: budget exhaustion aborts cleanly w/ `budget`+`run_end.stop_reason`, zero partial proposals; two-level acceptance (archive-accept vs promote) blocks the weak-parent ratchet — stepping stone archived, active agent kept; auto-rollback restores best snapshot w/ `restore` lineage + deactivates extras, history append-only; stagnation alarm stops without approval, continues with it; Budget/DriftMonitor unit edges | static scan+load gates precede ALL evaluation (incl. screening); canary/active-regression auto-rollback is defense-in-depth (promotion gate makes regression structurally impossible) |
| M9 | CLI + observability rendering | ✅ | 102 passed: full CLI lifecycle on the scripted demo (init→evolve→status→inspect→run→rollback→report); status renders archive table + checkout + alarms; `inspect --filter kind=accept` shows the two-level acceptance story; rollback v1 → val 0.6, restore v3 → 1.0; report unseals the test split on archive best (5/5, CI [1.0, 1.0]); two same-seed workspaces → identical event streams (ts stripped) + byte-identical archive/checkout | demo provider is content-addressed (role+request text), not FIFO — robust to evaluation-order changes; demo story: val 0.6 → 0.8 → 1.0, third accept is a non-promoted stepping stone |
| M10 | Design doc + live smoke + PDF citation spot-checks | ✅ | `docs/design.md` complete with §10 spot-check notes: **5/6 claims CONFIRMED, 1 PARTIAL** (DGM gates improvement at *selection*, not archive admission — rsif stricter by design, per SkillOpt); `docs/quickstart.md` + README link; `pytest -m live` **1 passed in 430s** (glm-5.3-flash via Anthropic-protocol gateway; 1 gen × 1 proposal; budget ≤ 60 calls held; canary→val gate order verified on any accept) | 2 live-path bugs found & fixed: current Anthropic SDK rejects `temperature` on `messages.create` (adapter probes signature, sends conditionally); autouse offline socket-guard now exempts `live`-marked tests |
| M11 | Second objective (task-agnosticism proof) | ✅ | 105 passed: `exact-match` objective (plain-text equality) improves 1/3 → 1.0 through the identical engine (DemoProvider full loop, 5 phases asserted); `examples/custom_objective.py` (arithmetic, loaded via importlib) improves 1/3 → 1.0 via a FIFO ScriptedProvider — no code fence, no sandbox; structural guard asserts `rsif/evolve/engine.py` never imports a concrete objective; CLI `init --objective exact-match && evolve` runs end-to-end | DemoProvider is objective-aware (code-tasks vs exact-match character); `objective_from_config` dispatches both built-ins |
| M12 | Overall review & optimization | ✅ | **106 passed + 1 live smoke.** (a) code-review: no dead code (all helpers — `EchoProvider`, `extract_code_fence`, `canonical_request_key`, `bootstrap_ci` — referenced), no TODO/FIXME/debug prints, `compileall` clean; (b) scripted demo re-run & event log walked — phase monotonicity `proposal→design→exploration→verification→correction`, `accept{promoted}`, `reflect` on correction, 3 accepted / 3 rejected, best fitness 1.0, report unseals test 5/5 CI [1.0,1.0]; (c) design↔implementation audit reconciled 4 over-promises (see Notes); (d) **provider-error clean-abort bug found & fixed** — real gateway `RateLimitError` previously crashed `cmd_evolve` as an unhandled traceback; now `ProviderError` (with `origin`) propagates from runtime → engine → `run_end.stop_reason="error:<Origin>"` (test `test_provider_error_aborts_cleanly`) | audit: no `skills/` package (skills are `SKILL` artifacts via `assembler`+`runtime`, static-scan-gated, no self-test admission or lexical tool selection in v1); no `safety/gates.py` (gate chain in `selection`+`guards`+engine); no `observe/cost.py` (cost = `safety/budget.py`+`observe/render.py`) — corrected README, `design.md`, and a Part-B reconciliation note in this file. **Two M12 audit claims were later found wrong and corrected in M13** (META recursion proof; archive ε-reseed) |
| M13 | External review fixes (H1–H3, H4, M1/M5/L1) | ✅ | **116 passed.** H1: META-only edits now accepted **provisionally on non-regression** and judged by a `meta_eval_window`-generation success-rate window → `meta_confirm`/`meta_revert` (+ `meta_pending` guard); revert provably restores the original template mid-run (3 new tests). M1: improver-phase `ProviderError` re-raised, never a "parse" reject (test). M5: per-call budget check (`Budget.overshot` + `BudgetExhausted`) bounds overshoot to one call (test: abort at call 7 with limit 6, generation-attributed). L1: engine bugs now `engine:<Type>` vs provider `error:<Type>`. H4: `underfilled_descriptors` (provably always empty) replaced by real ε-reseeding from **superseded lineages** (tests). H2: scan is now an import **whitelist** (`rsif.commands`-style transitive escapes rejected; module ABI import allowed); sandbox child env scrubbed to PATH (secrets invisible; egress limitation documented). H3: `accept_val` gains a **paired net-gain floor** (≥1 net task); code-tasks val 5→10 tasks, exact-match val 3→6; golden regenerated deliberately (same verdicts, richer gate payload); demo story now 0.4 → 0.6 → 1.0 + 0.9 stepping stone | M7's "recursion proven" claim was masked: the test's scripted answers made the META edit's val *comparison* pass — as-implemented, META-only acceptance rode on unrelated agent answers (or noise); the M13 semantics measure the improver itself. Docs corrected (design §4.1/§4.3/§4.5/§5, plan B.5) |
| M14 | Real-project validation + implementation investigation | ✅ | **119 passed** (+ config-objective seam test). Third objective built through public seams only (`projects/regex_agent/`: RegexObjective, sandbox-graded pattern tasks; live runner with cached gateway provider); offline deterministic proof val 0.2→0.4→1.0 (2 accepted edits); **live gateway run** (glm-5.3-flash, 29/120 calls, exit 0): baseline val 0.6 with real held-out gap; two plausible regressions **correctly rejected at the cascade screen**; reflection visibly shaped the next proposal; no ratchet; sealed test 0.5 on archive best. `docs/investigation.md`: 12-section code-level walkthrough (implementation ↔ design point ↔ evidence per mechanism, incl. honest open-limitation table M2/M3/M4/L2/L3) | One core seam fix forced by the project: `RunConfig`'s closed objective-name set contradicted the task-agnostic claim — relaxed to any non-empty name (built-in dispatch unchanged in `objective_from_config`). Project solvability invariant caught a bad task (`colou?r` matches inside "colorr") before scoring; live run surfaced a real harness lesson: "verify-first" prompt strategies break the objective's first-line extraction contract — gates kept it from deploying |

Ordering: M0 → (M1 ∥ M2) → M3 → (M4 ∥ M5) → M6 → M7 → M8 → M9 → M10 → M11 → M12.

---

# RSI Framework (`rsif`): Design & Implementation Plan

## Context

Build a **framework for constructing agents with a recursive self-improvement (RSI) loop**, grounded in the resources of this repo (`awesome-rsi`: ~200 curated resources, 98 hand-distilled mechanism entries in `site/curated.json`, 69 paper PDFs in `resources/`). The repo has no existing framework code — greenfield build in a new `framework/` subdirectory with its own `pyproject.toml`; the awesome-list content is never modified.

**Confirmed requirements (user):**
1. All four improvement surfaces as evolvable artifacts: **skills & tools (code), prompts & strategies, memory & knowledge, agent architecture (meta-agent)**
2. **Pluggable, task-agnostic objective** — ships with an executable coding benchmark + a clean `Objective` protocol
3. **Provider-agnostic LLM layer** (Anthropic / OpenAI / local via optional extras)
4. **Full framework** deliverable: referenced design doc + working implementation + tests
5. The framework's loop must be: **idea proposal → exploration → design → verification/validation → correction**, iterating until the best agent evolves — then implementation proceeds through task-split-with-verification, implementation-with-testing, overall review, and optimization

**Design verification status:** every mechanism below was cross-checked against `site/curated.json` (the hand-distilled, per-paper method/results/limitations written from the papers themselves). M10 additionally spot-checks key citations against the local PDFs in `resources/`.

---

## Part A — Research-Grounded Design Principles (each referenced)

1. **Empirical validation gate** — only evaluated improvements are kept. [DGM 2505.22954; Self-Improving Coding Agent 2504.15228; FunSearch nature-funsearch-2024; AlphaEvolve 2506.13131; SkillOpt 2605.23904 — "accepted only on held-out validation gain"]
2. **Verification must be execution-grounded, never intrinsic self-judgment.** [Negative result 2310.01798 "Cannot Self-Correct Reasoning Yet"; CRITIC 2305.11738; model collapse 2510.16657; AutoResearch 2608.17906 "insight in, hallucination out"; Divergent-Thought/DoT 2305.19118]
3. **Archive, not single lineage** — MAP-Elites quality-diversity + backtracking. [1504.04909; QD frontiers-quality-diversity-2016; DGM archive; POET 1901.01753 stepping stones]
4. **Everything improvable is a versioned artifact with lineage.** [Gödel Agent 2410.04444 "behavior is code it can inspect and rewrite"; ACE 2510.04618 bounded incremental edits vs. context collapse; Voyager 2305.16291; AgentFactory 2603.18000; Strategy Genes 2604.15097 — keep representations compact]
5. **Recursion: the improver is itself improvable.** [STOP 2310.02304; Promptbreeder 2309.16797 mutates mutation prompts; MetaSkill-Evolve 2607.05297 fast/slow two-cadence loop; Hyperagents 2603.19461; ADAS 2408.08435 re-architect step]
6. **Memory = three layers** (episodic reflections / distilled insights / curated playbook). [Reflexion 2303.11366; ExpeL 2308.10144; EvolveR 2510.16079; A-MEM 2502.12110; ACE 2510.04618]
7. **Misevolution is expected, not exceptional.** [Your Agent May Misevolve 2509.26354; SAHOO 2603.06333; PACEvolve 2601.10657 — context pollution/mode collapse; AutoHarness 2603.03329 guard layers]
8. **Observability with edit attribution is a prerequisite.** [Agentic Harness Engineering 2604.25850 — component/trajectory observability + edit attribution]
9. **Theoretical anchor:** self-improvement = amortizing verifier-guided search into the policy. [Sharpening 2412.01951; rooted in L2L-by-GD 1606.04474; Gödel Machine cs/0309048 as the proof-based ideal DGM replaces empirically]

**Key architectural scoping — trust boundary:** the *evolution engine is trusted, frozen process code*; the *agent itself* (module code, prompts, skills, memory) is fully self-modifiable artifact data. This realizes DGM/ADAS-style self-modification while guaranteeing the loop cannot break itself in v1. The improver-improves-improver axis [2310.02304, 2607.05297] is realized via `META` artifacts (improver templates + operator catalogs are themselves evolvable, under stricter gates + approval).

---

## Part B — Architecture

```
                ┌───────────────────────────────────────────────┐
                │ EvolutionEngine (trusted, frozen process)     │
                │ propose → explore → design → verify → correct │
                └───┬─────────┬──────────┬──────────┬──────────┘
                Improver   Objective   Archive    Safety
              (meta-agent, (fitness,  (MAP-Elites (gates, drift,
               templates   suites:    + backtrack) budget, approve,
               = META      train/val/              rollback)
               artifacts)  test/canary)
                ┌────┴─────────────────────────────────────────┐
                │ ArtifactStore — versioned, immutable blobs +  │
                │ lineage.jsonl + active checkout               │
                │ skills | prompts | memory | modules | meta    │
                └────┬──────────────────────────────────────────┘
                  AgentSpec (resolved checkout)
                ┌────┴──────────────────────────────────────────┐
                │ AgentRuntime: LLMProvider ↔ session/tools ↔   │
                │ Sandbox (+ skill retrieval, memory retrieval)  │
                └───────────────────────────────────────────────┘
```

> **Implementation note (post-M12 audit).** `docs/design.md` is the
> authoritative post-implementation description; three B-spec details below
> were simplified in code and are documented there accurately:
> (1) **skills** are first-class `SKILL` artifacts assembled by
> `evolve/assembler.py` and exposed as tools — there is no `skills/` package,
> no self-test admission gate (only the static-scan gate), and no lexical tool
> selection in v1; (2) the **gate chain** lives in `evolve/selection.py` +
> `sandbox/guards.py` + engine inline — there is no `safety/gates.py`;
> (3) **cost tracking** is `safety/budget.py` + `observe/render.py` — there is
> no `observe/cost.py`.

### B.1 LLM layer — thin internal Protocol (no hard LiteLLM dep)
- `llm/base.py`: `Message`, `ToolSpec`, `CompletionRequest`, `CompletionResult`, `Usage`; `LLMProvider(Protocol): complete(req)`.
- Adapters (optional extras): `anthropic_provider.py`, `openai_provider.py`, `litellm_provider.py`. Each capped ~100 LOC.
- `llm/mock.py`: `ScriptedProvider` (deterministic queues) — the test seam.
- `llm/cache.py`: disk cache keyed `(provider, model, canonical-json(messages,tools), seed, temperature)` → deterministic replay + no repeat cost.
- `llm/factory.py`: `provider_from_config(RunConfig)`; `RSIF_PROVIDER=scripted` for offline mode.

### B.2 Artifact store — immutable version dirs + append-only `lineage.jsonl` + mutable checkout (git semantics, no git plumbing)
- `artifacts/model.py`: `ArtifactType = SKILL | PROMPT | MEMORY | MODULE | META`; immutable content-hashed `ArtifactVersion`s; `PatchOp = Create | Update | Delete | Restore`; `Patch(ops, rationale, hypothesis)`.
- `artifacts/store.py`: `apply_patch()` (writes candidate versions, no activation), `promote()` (activate after acceptance), `rollback/restore()` (appends `Restore` lineage entry — history never rewritten), `lineage()`, `snapshot()`.
- `artifacts/workspace.py`: run layout `<run>/{config.json, seed.json, events.jsonl, lineage.jsonl, artifacts/<id>/vN/, checkout.json, evals/<gen>/, cache/llm/}`.
- Payload conventions: PROMPT=markdown sections; SKILL=python file + manifest [2305.16291]; MEMORY=playbook sections with item ids [2510.04618]; MODULE=python class implementing the module ABI; META=improver templates + operator catalog [2310.02304, 2309.16797].

### B.3 Agent runtime + module ABI (architecture surface)
- `runtime/runtime.py`: `AgentRuntime.run(task, spec, budget) -> Attempt(trace, result, usage)`. Context = prompt artifact + retrieved skills + retrieved insights/reflections; loop: LLM → tool calls (skills) via sandbox → observations; budget-bounded. Runtime interprets the spec; the spec evolves.
- `runtime/module_api.py`: stable ABI `AgentModule.setup(ctx) / step(ctx) -> LLMCall|ToolCall|Submit|Reflect`. Modules see only `ModuleContext` — never the store/engine [2408.08435, 2410.04444].
- `runtime/loader.py`: `importlib` load from immutable version dir; ABI validation + static scan before use.

### B.4 Evolution engine — the design loop, phase-named in every event
| Phase | Implementation | Reference |
|---|---|---|
| **1. Idea proposal** | `Improver.propose(ctx) -> [Proposal]`; prompt assembled from checkout summary, archive frontier + underfilled niches, recent rejection reflections, insights. Improver templates are META artifacts → the improver's strategy itself evolves | STOP 2310.02304; Promptbreeder 2309.16797; DGM |
| **2. Idea exploration** | Cheap screening: candidate runs 1–2 probe tasks (train split); cascade continues only if ≥ parent − ε | AlphaEvolve 2506.13131 cascade |
| **3. Idea design** | Proposal → concrete `Patch` (bounded ops: add/update/delete ≤ k; no whole-context rewrites) | ACE 2510.04618; SkillOpt 2605.23904 |
| **4. Verification & validation** | Gate chain: static AST scan → canary suite → train-split eval (sandbox) → **val-split acceptance** (`val(child) > val(parent) + threshold`). LLM self-critique (Self-Refine style) is advisory only | DGM; SkillOpt; Self-Refine 2303.17651; 2310.01798 |
| **5. Correction** | On reject: Reflexion reflection → episodic memory; periodic ExpeL distillation; on regression alarm: auto-rollback to archive ancestor; population-level correction via archive parent sampling (frontier-biased + ε to rare niches) | Reflexion 2303.11366; ExpeL 2308.10144; DGM backtracking |

### B.5 Archive — MAP-Elites + backtracking (`evolve/archive.py`)
Niches keyed by objective-supplied behavior descriptors (coding objective: `(surface_edited, pass_band, mean_steps_band)`); elitist replacement, ties → lower cost; frontier-biased parent sampling [1504.04909] + ε-reseeding from superseded lineages (as-implemented correction, M13; the planned "underfilled niche" reseed was provably inert and `parent_ref` re-seeding was never wired); persisted `archive.json`.

### B.6 Objectives (`objectives/`)
- `base.py`: `Task`, `TaskSuite`, splits `train|val|test`; `Objective(Protocol)`: `suites()`, `evaluate(task, attempt)`, `fitness(scorebook)`, `behavior_descriptors(...)`, `canaries()`; bootstrap CIs on fitness.
- `code_tasks.py`: function-implementation tasks scored by hidden unit tests in the sandbox. Task packs as data: `tasks/{train,val,test,canary}/` (30/10/10 + 5 canaries). Train selects, **val accepts** [2605.23904], test sealed until `rsif report` [2510.16657]. `examples/custom_objective.py` shows a ~30-line plug-in objective.

### B.7 Memory — three layers (`memory/`)
`episodic.py` (Reflexion), `insights.py` (ExpeL distillation over **verified** trajectories only, provenance + usage-based retirement [2510.16657 guard]), `playbook.py` (ACE bounded ops), `retrieve.py` (hand-rolled lexical TF-IDF behind a `Retriever` Protocol).

### B.8 Skill library (`skills/`)
SKILL artifacts admitted only after self-tests pass in the sandbox (verification evidence in artifact meta) [2305.16291]; lexical retrieval for tool selection; successful solutions frozen as executable skills, refined by later feedback [2603.18000].

### B.9 Safety (`safety/`)
`gates.py` (AST scan → canaries → train-gain → val-acceptance, short-circuit); `drift.py` (charter-alignment + canary-regression + spend/step trends [2509.26354, 2603.06333]); `budget.py`; `approvers.py` (`CLIApprover` mandatory for META edits and drift alarms); `rollback.py` (auto-rollback with `Restore` lineage entry).

### B.10 Observability (`observe/`)
`events.py` (kinds: proposal|patch|screen|eval|gate|accept|reject|reflect|archive_update|rollback|budget|llm_call|approval|run_start|run_end). Event log = what `status/inspect` render + what reflections read + the replay source (with `seed.json` + LLM cache a run is bit-reproducible). `cost.py`, `render.py`.

---

## Part C — Implementation: task split with verification methods

Package: `framework/` — `src/rsif/`, import `rsif`, CLI `rsif`, Python 3.11+, **zero required runtime deps**; extras `[anthropic] [openai] [litellm]`; dev group brings pytest. Default `pytest -m "not live"` = offline, free, deterministic.

| # | Milestone | Deliverable | Verification |
|---|---|---|---|
| M0 | Scaffold + tracked plan doc | pyproject, package skeleton, `config.py`, `workspace.py`, `events.py`, `cli.py --help`, `docs/plan.md` + `docs/decision-log.md` | smoke test imports; `rsif --help` exits 0; status table present |
| M1 | Artifacts & lineage | `artifacts/model.py`, `store.py` | unit: version immutability raises; apply→rollback restores byte-identical; lineage append-only w/ parent refs |
| M2 | LLM layer | Protocol, `ScriptedProvider`, disk cache, 3 adapters | unit (socket blocked): scripted responses; cache hit identical + `cached:true`; adapter serialization |
| M3 | Sandbox + code objective | `sandbox/exec.py`, `guards.scan_code`, `code_tasks.py` + task packs | unit: infinite loop killed; mem hog killed; `os.system` flagged; known-good→1.0 / known-bad→0.0 deterministically |
| M4 | Runtime | `runtime.py`, `session`, `module_api`, `loader` | integration: scripted agent passes 3 tasks; loader rejects non-ABI file; ABI `step()` drives loop |
| M5 | Memory | episodic, insights, playbook, retrieve | unit per layer; integration: reflection retrieved for similar task not dissimilar; playbook rejects unbounded rewrite |
| M6 | Evolution engine v1 | engine, proposer, selection, archive; full loop w/ mock LLM | flagship deterministic test: A accepted+archived, B rejected → rollback+reflection events; golden `events.jsonl`; same seed → identical bytes |
| M7 | Architecture surface + recursion | MODULE evolution; META artifacts; scheduler fast/slow | integration: module edit passes gates, changes descriptors; META edit gated behind approver |
| M8 | Safety hardening | gates, drift, budget, approvers, rollback wired | budget exhaustion aborts cleanly; canary regression → auto-rollback w/ `Restore`; drift alarm forces approval; forbidden module rejected pre-execution |
| M9 | CLI + observability | `init/run/evolve/status/inspect/rollback/report`, render | CLI integration tests on seeded mock workspace; snapshot tests for `status` |
| M10 | Docs + live smoke + design verification | `docs/design.md`, quickstart, live smoke; spot-check ~6 citations against local PDFs | `pytest -m live` passes (~$1 cap); example runs end-to-end; citation notes in design doc |
| M11 | Task-agnosticism proof | second objective (exact-match) + `examples/custom_objective.py` | same engine improves both objectives, zero engine changes |
| M12 | Overall review & optimization | `/code-review` + `/simplify` pass; end-to-end demo reviewed from event log; design↔implementation audit; fixes; close out status table | findings fixed & re-verified; full pytest green; goldens updated deliberately |

Ordering: M0 → (M1 ∥ M2) → M3 → (M4 ∥ M5) → M6 → M7 → M8 → M9 → M10 → M11 → M12.

## Part D — Testing & verification strategy (end-to-end)

- **Layout:** `tests/{unit, integration, golden, live}`; `addopts = "-m 'not live'"`.
- **Determinism:** explicit `random.Random` threading; `ScriptedProvider` queues; LLM disk cache + `seed.json` → bit-reproducible runs; golden `events.jsonl` hash tests.
- **Offline guard:** conftest fixture blocks `socket.socket`.
- **Sandbox (macOS, no Docker):** `subprocess` + `python -I` + temp cwd + wall/CPU timeouts + best-effort rlimits; same executor for agent code, skill self-tests, unit-test scoring.
- **Final end-to-end verification (post-M12):** full offline suite green; `rsif init && rsif evolve --generations 3` scripted demo; `rsif status/report` render; `pytest -m live` real-model smoke (~$1 cap) demonstrating a real improvement or correctly-rejected regression.

## Part E — Explicit non-goals (v1)

No weight training; no distributed eval pool; no Docker/VM sandbox; no web UI; no embeddings/external retrieval services; no multi-agent debate orchestration; the evolution engine itself is not an editable artifact (only improver templates/operators are, via the META surface).

## Key risks

Eval overfitting → splits+canaries+CIs [2605.23904, 2510.16657] · Cost blowout → cascade screening + cache + hard budget [2506.13131] · Self-modification breaking the loop → trust boundary + ABI + guards + auto-rollback [2505.22954] · Intrinsic self-correction degradation → execution-grounded acceptance only [2310.01798] · Provider abstraction creep → 3-method Protocol, capped adapters · Misevolution → drift monitors, approvals, rollback [2509.26354, 2603.06333] · Memory collapse → verified-trajectory-only distillation [2510.16657].
