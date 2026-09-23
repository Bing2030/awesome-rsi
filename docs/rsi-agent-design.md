# Building a Recursive Self-Improving Agent on Claude Code

**Status:** design document (brainstorm output — not yet implemented).
**Scope:** context-space self-improvement only; Claude Code as primary substrate, with a
portable genome so OpenCode/Cursor adapters can follow.
**Grounding:** every design decision below cites the resources in this repository (105 papers +
OSS repos, each reviewed against its source in the enrichment pass). Working name: **Petri**.

---

## 1. Why and what

The goal is a **long-running (days–weeks) loop in which a coding agent genuinely improves**, with
every gain measured and every change revertible. The repository's own survey is the evidence
base: harness-evolution methods (ADAS, AHE, RRSI, Harness-Zero), self-modifying code agents
(DGM, SICA, STOP, Gödel Agent), experience-driven memory (Reflexion, ExpeL, ACE, EvolveR), and
program-search engines (AlphaEvolve, FunSearch, MLEvolve) all attack the same problem from
different angles. This document synthesizes them into one concrete architecture built on Claude
Code's actual extension surface.

Three scope decisions (fixed for this design):

1. **Claude Code first.** Its extension surface — `CLAUDE.md`, `.claude/skills/`,
   `.claude/agents/`, hooks in `.claude/settings.json`, MCP configs, headless
   `claude -p --output-format stream-json`, git worktrees, per-subagent model selection — is
   already a mutable harness expressed as plain files. The genome stays substrate-portable so
   OpenCode/Cursor can adopt it later by re-implementing one component (§15).
2. **Context-space only.** No weight training. The improvement surface is exactly what a
   `git diff` can show.
3. **Human-gated promotion.** The system proposes; the researcher merges.

## 2. Core thesis

Claude Code already separates "agent" from "harness" — and the harness is files. That yields
three principles:

1. **The improver and the improved are separate processes.** Claude Code (fixed substrate) runs
   tasks. A small orchestrator — headless sessions, worktrees, scheduled wakeups — improves the
   files that configure it. Runtime self-modification (Gödel Agent's in-place `exec`+`setattr`
   rewriting) is deliberately rejected: edits land as **commits between runs**, so every
   improvement is diffable, revertible, and auditable.
2. **Improvement = accepted commits to plain files.** The **genome** is `CLAUDE.md`, skills,
   subagent definitions, strategy genes, and memory. One commit per accepted state; the
   incumbent is always a single git ref (the RRSI discipline: "the incumbent is always a
   commit").
3. **Truth lives on an immutable spine.** A separate repository (`petri-spine/`), mounted
   read-only *outside* every worktree, holds the task bank, the scoring code, the accept rule,
   the permission baseline, and the budget config. This generalizes Karpathy's `autoresearch`
   rule — the metric (`evaluate_bpy`) lives in a file the agent must never touch — and
   HyperAgents' evaluator quarantine (git-reset after each run so the improver cannot edit its
   judge). Enforcement is architectural (mount + canary), never promptural.

## 3. What the research says (and how it shapes this design)

The full review is the 105 resource cards; the load-bearing findings, with the numbers that
matter:

| # | Lesson | Evidence | Design consequence |
|---|--------|----------|--------------------|
| 1 | **Executable verification is the engine; self-report is not** | CRITIC: gains come from tool feedback, not self-critique (oracle/no-tool ablations). "LLMs Cannot Self-Correct Reasoning Yet": intrinsic correction degrades GPT-3.5 CommonSenseQA 75.8→38.1. Self-Debug: a bare "wrong" verdict gains 0.0 (81.3→81.3); explanation + unit tests gain. | Deterministic checkers judge every task; self-critique is demoted to a *routing* decision; retries must cite a new external signal (§7, T0). |
| 2 | **Overfitting the evolve split is the default failure** | RRSI exists because prior harness methods gained in-split and collapsed out-of-split; even regularized, it gains +6.0 evolve-split vs +1.8 held-out. SkillOpt accepts edits only on strict held-out gain (1–4 edits survive per epoch). | Disjoint evolve/held-out/canary splits; held-out non-regression is the accept rule; gap-triggered refresh (§6, §8). |
| 3 | **Archives and diversity beat hill-climbing** | DGM ablations: no archive 50.0→23.0%, greedy parent selection 50.0→39.7%. MAP-Elites beats single-objective EA at p<1e-7. MAD debate lifts diversity 19.3→49.7. 2601.14525: RL mode-collapses to 2/128 ideas without diversity pressure. | Unpruned genome archive; MAP-Elites niches; island migration; adversarial two-proposer debate on stagnation (§7, T3). |
| 4 | **Objective hacking is the default failure of closed loops** | DGM node 114 hit a perfect score by deleting the logging its hallucination detector relied on. SOTOPIA-π: judge–human gap widened 0.36→1.42 (self-reward hacking). 2601.14525 froze eval hyperparameters after attention-leak exploits. | Spine-side ledger written by the hook process itself (deleting logs in-sandbox destroys nothing); quarantined judges; three canary types (§6, §10). |
| 5 | **Consolidate experience into compact, gated artifacts — small beats big** | Strategy genes (~230 tokens) beat 2,500-token skill packages 54.0% vs 49.9%. ExpeL's distilled insight lists beat raw reflections. ACE quantifies context collapse (a rewrite shrank effective context 18,282→122 tokens). | CLAUDE.md as itemized bullets with counters, not prose; `grow-into-skill` operator when a bullet exceeds ~15 lines; hard caps everywhere (§5). |
| 6 | **Only execution-verified experience becomes durable** | Voyager admits skills only after environment execution + critic confirmation (63 unique items, 3.3× baselines). AgentFactory's executable subagents cut orchestrator tokens −58% (2,971 vs 7,022) where textual experience (6,210) never approaches it. RSIAgent freezes only *verified* experience. | Skill minting requires a verified success trace; supersedes lineage instead of in-place edits (§5, §7). |
| 7 | **Separate timescales; score curation by later outcomes** | MetaSkill-Evolve updates meta-skills slower than task skills (+23.54 OfficeQA frozen-model). SkillRise's decoupled credit assignment (+2.3–8.5 pp). POWERPLAY's simplest-first ordering with structural no-forgetting. | Four explicit loops T0/T1/T3/T4 with different periods; delayed, outcome-based credit for skills (§7). |
| 8 | **Memory needs counters, caps, and pruning** | EvolveR trust ledger (successes+1)/(usages+2), purge <0.3. ACE helpful/harmful counters. PACEvolve diagnosed append-only history as "context pollution" from 200+ 1000-step runs; fixed with hierarchical caps (5 ideas / 20 hypotheses). Hermes bounds MEMORY.md (~800 tokens, errors when full). | Every memory item carries counters and earns standing; auto-quarantine below threshold (§5). |
| 9 | **Observability is the substrate the improver feeds on** | AHE: components-as-files + layered evidence corpus + a falsifiable prediction per edit lifted Terminal-Bench 2 from 69.7%→77.0% (~32-hour campaign). Its honest attribution: fix-precision 33.7%, 40 unforeseen regressions vs 5/43 predicted. | Hooks stream structured events to a spine-side ledger; every proposed edit carries a falsifiable prediction resolved next wave (§5, §7). |
| 10 | **Cost decides whether loops run at all** | DGM cost ~$22k; its staged small→medium→full eval gates are the affordability mechanism. SoL-Pi: ~45% token cut at ~94% of score by optimizing efficiency directly. Autoresearch: fixed 300s runs keep experiments comparable and overnight-affordable. AI Scientist: <$15/paper. | Hard budget caps; staged evaluation; efficiency as a first-class niche (§8, §9). |
| 11 | **Recursion is non-monotonic and bounded by the base model** | STOP: improvement curves rise for GPT-4 and *fall* for GPT-3.5/Mixtral — a worse improver can get itself accepted. Gödel Agent never beat hand-written Tree-of-Thought on Game of 24. Continual-Harness actively harmed Flash-Lite-class models. | Model IDs are immutable spine config; cheap models judge/distill, strong models generate; regression gates mandatory (§8, §13). |
| 12 | **Populations/co-evolution generate the curriculum** | POET: transfer succeeds on ~49–54% of attempts, solving courses 2×-budget from-scratch ES cannot. Agent0: curriculum difficulty demonstrably escalates (frozen executor pass rate 64.0→51.0%). POWERPLAY: simplest still-unsolvable task, no-forgetting by construction. | Capped self-generated curriculum with a frozen-first verifier and incumbent-fails admission test (§6). |

**Calibration (what "improvement" should mean here):** AHE +7.3 pp; RRSI +1.8 held-out; SkillOpt
+23.5 pp on narrow suites; AI4AI test-time scaffolds 0.488→0.763 for a *weak* frozen target;
SoL-Pi ~45% token cut. Not DGM's 20→50% — that required whole-agent code rewrites and ~$22k of
compute. On a fixed strong substrate with a context-only surface, expect single-digit percentage
points on broad held-out suites plus large cost reductions, with compounding coming from the
verified skill/memory library over months, not from any single generation.

## 4. Architecture overview

```
                    ┌──────────────────────────────────────────────┐
                    │  petri-spine/  (separate repo, READ-ONLY)    │
                    │  Bank ─ Referee ─ Gatekeeper ─ Warden ─ Gov. │
                    └───────────────▲──────────────┬───────────────┘
                          scores    │              │ budget / policy
                                    │              ▼
   ┌─────────┐   runs tasks   ┌─────┴────┐   proposes edits   ┌───────────┐
   │ Runner  │──────────────▶│ Ledger   │──────────────────▶│ Distiller │
   │ (work-  │  stream-json  │ (JSONL,  │   traces → edits   │ (cheap    │
   │  trees, │                │  spine-  │                   │  model)   │
   │  claude │◀───────────────│  side)   │                   └─────┬─────┘
   │   -p)   │  genome state  └─────────┘                          │
   └────┬────┘                                                     ▼
        │ materializes                                    ┌───────────────┐
        ▼                                                 │ Breeder       │
   ┌──────────┐                                           │ (archive +    │
   │ GENOME   │◀── commits (promotion = human-merged PR) ──│  mutation)    │
   │ (git)    │                                           └───────────────┘
   └──────────┘
```

Services (each a small program or headless Claude Code session):

- **Runner** — materializes a candidate genome in a git worktree, invokes
  `claude -p --output-format stream-json` per task with pinned model, permission mode, and tool
  allowlist.
- **Ledger** — append-only JSONL written by PreToolUse/PostToolUse hooks, stored spine-side.
  Because it is written *outside* the sandbox, deleting logs inside the worktree destroys
  nothing (DGM node-114 pre-empted structurally).
- **Distiller** — turns wave traces into candidate genome edits, insight bullets, skill-mint
  proposals, and memory deltas. Cheap model, high volume.
- **Breeder** — maintains the genome archive, samples parents, applies mutation/crossover
  operators.
- **Referee** — scores runs from environment evidence only.
- **Gatekeeper** — applies the accept rule; opens promotion PRs; never merges them.
- **Governor** — enforces budget caps and the schedule.
- **Warden** — owns permissions, hook registration, and the audit trail; the only component that
  may land structural changes (with human approval).

One generation: Governor wakes within budget → Breeder emits N candidates → Runner executes on
a staged task subset → Referee scores → Gatekeeper rejects (feeding the Distiller and the
failure log) or opens a promotion PR → human merges → incumbent ref fast-forwards.

## 5. The genome

All mutable state lives in one git repo (`petri-genome/`). A top-level `genome.json` manifest
lists every component with stable IDs, counters, and lineage — AHE's per-edit manifest plus
AgentFactory's `supersedes` lineage.

| Artifact | Representation | Operators |
|---|---|---|
| `CLAUDE.md` (root + package-level) | ACE-style itemized bullets, stable IDs (`[[G-042]]`), helpful/harmful counters | `add-bullet`, `edit-bullet`, `reorder`, `prune` (counters net-negative over a window), `grow-into-skill` (bullet >~15 lines → minted as a skill, replaced by a one-line pointer) |
| `.claude/skills/<name>/` (`SKILL.md` + bundled scripts) | Voyager-style executable skills; each carries an EvolveR trust ledger `(successes+1)/(usages+2)` | `mint` (verified traces only), `edit-step`, `split`, `merge`, `supersede`, `deprecate`; trust <0.3 → auto-quarantine |
| `.claude/agents/<name>.md` | Subagent definitions; frontmatter pins `model` per role | `create`, `retune-model`*, `edit-prompt`, `widen/narrow tools`; transactional per Memento-Skills (attribute failure → isolated rewrite → gates → atomic deploy/rollback) |
| `.claude/genes/*.md` | ~230-token strategy genes: match signals, one-line summary, ordered strategy list with AVOID cues | mint/edit/retire alongside CLAUDE.md bullets |
| `MEMORY.md` + memory dir | Bounded (hard char cap), write-tiered | Hermes after-turn reviewer ("save a skill or memory?") + curator with rollback; purgeable at will |

\* model retunes are *structural* changes: proposed by the Breeder, landed only by the Warden
with human approval (§10).

**Frozen (the spine):** `bank/` (task fixtures, ground truth, verify scripts), `referee/`
(scorer, judge prompts, eval hyperparameters — frozen after any detected exploit), `gatekeeper/`
(accept rule + δ/β constants), `warden/` (permission baseline, hook registration),
`governor.toml` (budget caps), model IDs. The improver may *propose* telemetry-hook changes; it
can never land them itself.

## 6. Task & evaluation bank

**Sources, by trust:**

1. **Real work (~60%)** — the actual task queue of the target repo (here: card-enrichment waves,
   site regeneration, issue triage), each wrapped with a machine-checkable verifier (schema
   validation, tests, `node enrichment/tools.mjs merge` passing). Genuine improvement is defined
   here first; everything else exists to predict it.
2. **Mined failures (~25%)** — the Distiller mines the Ledger for recurring failure shapes
   (flaky tool sequences, misattributed edits, compaction-induced losses) and packages them as
   regression tasks. PACEvolve's permanent failure log ensures dead ends are blocked, not
   rediscovered.
3. **Self-generated curriculum (~15%, capped)** — POWERPLAY-style: a curriculum subagent proposes
   the simplest still-unsolvable task. Admitted only if (a) a verifier is written and *frozen*
   before use, (b) the incumbent fails it in k attempts, and (c) it is minimally above current
   ability. RSIAgent's curriculum agent decides when practice stops.

**Splits:** 60% evolve / 30% held-out / 10% canary, disjoint by construction. Refresh tripwire:
re-roll the held-out split when the evolve−held-out gap exceeds δ_leak for two consecutive
generations.

**Verifiers — two layers.** Layer 1: deterministic checkers (`verify.sh`, unit tests, lints).
Layer 2: for open-ended outputs, a judge subagent on a cheap model, isolated transcript, seeing
environment artifacts only — never the actor's private reasoning (RSIAgent's verifier isolation,
designed to break correlated errors). Judge verdicts must cite evidence and, where possible, a
repro script (Self-Debug: a bare "wrong" gains zero). Where cheap, scoring is step-anchored —
PostToolUse checkpoints count as process signal (Let's Verify Step by Step: PRM 78.2% vs ORM
72.4% best-of-1860 on MATH).

**Canaries (anti-hacking tasks):**

- **Logging-presence** — tasks that *fail* unless the expected PreToolUse/PostToolUse events
  appear in the spine-side ledger. Makes the node-114 move (delete logging to hack the
  objective) self-defeating.
- **Ground-truth-integrity probes** — any write under `petri-spine/` fails the entire run, not
  just the task.
- **Judge-grounding probes** — seeded transcripts where the actor claims success but artifacts
  disagree; a judge that passes them is self-rewarding and gets quarantined (SOTOPIA-π).

## 7. The loops (four timescales)

**T0 — inner execution (minutes).** One `claude -p` session per task, in a worktree, permission
mode `acceptEdits` + explicit tool allowlist, no network (DGM/ALMA/SIA containment).
Self-correction is bounded and externally driven: at most 3 internal retries, each citing the
specific failing external signal (test output, checker diff, evidence-citing judge verdict).
Retries without a new external signal are forbidden. On exhaustion: escalate to a stronger
subagent or fail *with a distilled trace* — failures are fuel.

**T1 — consolidation (per wave).** Triggered by a wave barrier: all candidates in the wave have
finished and been scored (RSIAgent: parallel exploration from a shared snapshot; consolidation
only after all-pass verification). The Distiller emits:

1. **Candidate genome edits**, each with an AHE-style manifest entry: failure evidence cited,
   inferred root cause, targeted fix, *predicted* tasks fixed, *predicted* at-risk regressions —
   a falsifiable prediction per edit, resolved next wave into per-file keep-or-revert.
2. **Insight bullets** for CLAUDE.md (ExpeL: distilled insights beat raw reflections).
3. **Skill-mint proposals** — eligible only with an execution-verified success trace (Voyager).
4. **Memory deltas** — ACE-style compact operations applied by deterministic non-LLM code, with
   counters and dedup.

Credit assignment is decoupled and delayed: skills are scored by *later*-task outcomes
(SkillRise), not by whether the minting wave looked productive.

**T3 — harness search (per generation, ~daily).** The Breeder maintains an **unpruned archive**
of every viable genome (DGM ablations: −27 pp without the archive; −10 pp with greedy parents).
Niches: task domain × dominant failure class × cost band, elites filling a MAP-Elites grid.
Parent sampling: sigmoid(score) × novelty (DGM). Operators: single-artifact mutation with
annealed edit budgets (RRSI; SkillOpt expects only 1–4 edits/epoch to survive anyway);
crossover between niche elites; island migration every M generations (FunSearch/OpenEvolve).
On stagnation: ancestor reversion drawn from a power law + a two-proposer adversarial debate
over opposing edit hypotheses, judged by a third subagent (MAD/DTE).

**T4 — curriculum (rolling).** Bank growth per §6; monthly promotion of mined tasks into the
held-out pool so the distribution tracks real work.

## 8. Promotion gate

Staged evaluation first: 10-task subset → medium → full, zeroing out on any failed domain
(DGM's affordability mechanism against its own ~$22k cost). Then the accept rule, as pure
functions in the spine:

```
admissible(candidate) :=
      held_out_score  ≥ incumbent_score − δ        # δ = noise floor, k=3 incumbent re-runs
  AND Δcost           ≤ β0 + β1 · Δscore           # added tokens must be paid for by gain
  AND critic_screen(diff)        = clean           # no task names, fixture IDs, hardcoded outputs
  AND failure_log(diff)          = clear           # PACEvolve: dead ends stay dead
```

SICA's utility shape (score + cost + time jointly) means a 2-point gain at 3× cost is a *loss*.
One MAP-Elites axis is tokens/task; the token-frugal elite within δ of the incumbent score is
periodically promoted (SoL-Pi: efficiency is the most reliable win in the space).

**Structural changes never auto-promote.** Hooks, permission profiles, model IDs, settings —
the Gatekeeper opens a PR and a human merges (Hermes staging). Acceptance fast-forwards the
incumbent ref and appends the decision, with all numbers, to the audit trail.

## 9. Long-run operations

- **Budget governor.** Hard daily $/token caps in `governor.toml` (spine-side); per-task
  wall-clock caps — fixed-duration runs keep tasks comparable and nights affordable
  (autoresearch). Budget exhaustion **degrades to "consolidate only", never to "skip
  verification"**.
- **Checkpoint/resume.** Everything durable is git refs plus append-only JSONL. Any crash
  resumes at the last incumbent; worktrees are pruned per wave. No in-memory state matters.
- **Context management.** Task sessions are short by construction; the Distiller *is* the
  compactor, and CLAUDE.md/genes/skills are its bounded outputs. A SessionStart hook injects the
  incumbent genome summary so every session boots from the evolved state; a PreCompact hook
  emits a digest event if a session does run long.
- **Observability.** Per run: stream-json transcript, hook-event ledger, per-edit manifest with
  predicted-vs-actual outcomes, score card, cost accounting. AHE's attribution stats
  (fix-precision 33.7%) calibrate how much skepticism the Gatekeeper applies to "this edit
  fixed that task" claims — hence delayed, outcome-based credit and per-file reverts.
- **Rollback.** Any state is `git checkout <ref>` away. A global freeze flag runs the incumbent
  genome only — the context-space analog of Letta's `--no-mods` kill switch.

## 10. Safety & containment

- **Evaluation sandbox.** Docker, no network, worktree-scoped, spine bind-mounted read-only
  *outside* the worktree so no relative path from the genome reaches it. Generated code
  executes only inside (DGM/ALMA/SIA pattern).
- **Write tiers** (Letta). Harness tier (genome manifest, spine): immutable to the runtime.
  Experience tier (MEMORY.md, ledger digests): purgeable.
- **Scope-chained host bridges** (agent-zero). If host access is ever needed: read → write →
  execute, human approval at each widening — minus the autonomy.
- **The system may never:** edit the spine; push to remotes or call `gh` mutation endpoints;
  edit permission blocks or hook registrations (Warden-owned); self-grant permissions
  mid-session (permission modes fixed per invocation); hold credentials (OpenClaw's
  fail-closed/purgeable discipline, adopted stricter: none at all); change model IDs (STOP's
  "a worse improver can get itself accepted" applies most of all to silent downgrades).
- **Audit trail.** Append-only, spine-side, written by the hook process itself: every tool
  call, every proposed edit with its prediction, every gate decision with numbers, every human
  approval. Fail-closed admission: anything the Warden cannot classify is denied.

## 11. Expected gains (calibration table)

| Result | Magnitude | Transferability here |
|---|---|---|
| AHE (observability-driven harness edits) | Terminal-Bench 2 69.7→77.0% | Direct analog — this design's T1/T3 |
| RRSI (regularized harness RSI) | +6.0 evolve / +1.8 held-out; ~30% fewer tokens | The accept rule's provenance |
| SkillOpt (bounded skill-doc edits) | 58.8→82.3 avg, best-or-tied 52/52 cells | Narrow suites; the CLAUDE.md operators |
| AI4AI (test-time scaffolds) | 0.488→0.763 mean for frozen weak target | Ceiling case; weak bases only |
| SoL-Pi (efficiency-targeted loops) | ~45% token cut at ~94% score; transfers to Opus 5 | The efficiency niche |
| Voyager/AgentFactory (verified skill libraries) | 3.3× exploration; orchestrator tokens −58% | The compounding layer over months |
| DGM / SICA (whole-agent rewrites) | 20→50% / 17→53%, ~$22k / cost *down* $1.91→$1.70 | **Out of scope** — bounds, not targets |

Honest summary: single-digit percentage points on broad held-out suites plus large cost cuts,
compounding through the verified library. If the loop produces DGM-scale jumps, suspect reward
hacking first (§6 canaries).

## 12. MVP roadmap

| Step | Scope (borrowed pattern) | Exit criterion |
|---|---|---|
| 1. Telemetry + baseline *(weekend)* | PostToolUse hook → JSONL ledger; 20 real tasks via `claude -p`; k=3 repeats (AHE; autoresearch) | Baseline report with quantified noise floor δ |
| 2. Distiller v0, human-applied | Traces → ExpeL insights + memory deltas; human applies by hand (ExpeL; ACE) | One curated insight measurably changes behavior on 10 held-out tasks |
| 3. Genome + single-lineage climb | Genome repo, manifest with falsifiable predictions, per-edit keep-or-revert (AHE) | One edit accepted on held-out gain with its prediction resolved |
| 4. Archive + niches + failure log | DGM archive, MAP-Elites grid, ancestor reversion, PACEvolve log | Archive beats greedy lineage over ≥5 generations; failure log blocks ≥1 rediscovery |
| 5. Full Gatekeeper | Staged evals, δ-measured accept rule, critic screening, promotion-by-PR (RRSI; HyperAgents) | Zero benchmark-specific edits survive a deliberate red-team batch; held-out ≥ evolve − δ for 3 generations |
| 6. Curriculum + canaries | POWERPLAY admission test; logging-presence, integrity, judge-grounding probes (RSIAgent; node-114 postmortem) | ≥1 self-generated task promoted into the bank; canaries green under adversarial probe |
| 7. Unattended multi-week operation | Governor, scheduling, efficiency niche, dashboard (SoL-Pi; SICA) | 7 consecutive days within budget; every regression explained in the audit trail; tokens/task flat-or-down at flat score |

Steps 1–3 are runnable by one person with Claude Code itself in a couple of weekends; steps 4–7
are where the loop becomes unattended.

## 13. Risks and honest limits

- **Base-model ceiling** — Gödel Agent never beat a hand-written Tree-of-Thought on Game of 24;
  STOP found recursion helps only strong base models. If the generation model is marginal, the
  loop measures noise, not improvement. Mitigation is model selection, not more loop.
- **Capability floor** — Continual-Harness adaptation actively harmed Flash-Lite-class models.
  Cheap models judge and distill; generation stays on the strong tier.
- **Reward hacking** — the canonical failures (node-114, frozen-after-exploit evals,
  self-rewarding judges) are all plausible here. Countermeasures are structural, but the
  residual risk is real; the human merge is the final backstop.
- **Attribution noise** — AHE's fix-precision of 33.7% means two-thirds of "this edit fixed
  that task" claims are wrong; hence delayed outcome-based credit and per-edit reverts.
- **Context rot** — unbounded growth collapses effective context (ACE: 18,282→122 tokens;
  PACEvolve's "context pollution"). Caps, counters, dedup, and demote-to-skill are load-bearing,
  not hygiene.
- **Split contamination** — evolve/held-out leakage is gradual and silent; the gap tripwire is a
  tripwire, not a cure.
- **Cost compounding** — multi-candidate × multi-generation × staged evals. Hard caps plus
  staged gates decide whether the loop runs at all.

## 14. Deliberately not doing

- **No weight training.** Harness-Zero's 23.3→44.3% via distillation and SEAL's self-edits are
  real but out of scope; the entire improvement surface is files a `git diff` can show.
- **No runtime self-modification of live code.** Edits are commits between runs.
- **No autonomous promotion.** Humans merge every structural change and periodically ratify
  content changes.
- **No scope drift.** No credential use, no autonomous model switching, no self-granted tools.

The honest thesis: Petri is not a slope toward superintelligence. It is a disciplined machine
for converting execution telemetry into a slightly better harness every day, with every gain
measured against ground the machine cannot touch.

## 15. Porting beyond Claude Code

The genome is deliberately plain files with a manifest contract. Porting to OpenCode or Cursor
means re-implementing exactly one component — the **Runner** (and the hook-to-ledger adapter) —
while the Bank/Referee/Gatekeeper/Breeder and the genome itself are untouched:

- **OpenCode**: custom agents/modes + plugin surface materialize the same genome files.
- **Cursor**: `.cursor/rules` + custom modes; the loader compiles CLAUDE.md bullets and genes
  into rule files. Weaker for unattended loops (interactive-first, closed harness), so it is a
  display target more than an execution target.

## Appendix A — design decisions mapped to sources

| Decision | Source(s) |
|---|---|
| Immutable spine / untouchable metric | autoresearch (repo), Hyperagents (2603.19461), 2601.14525 |
| Spine-side ledger, outside sandbox | DGM (2505.22954) node-114 postmortem, Hyperagents |
| Incumbent-is-a-commit; noise floor δ; β-cost rule; critic screen | RRSI (2609.24972), SICA (2504.15228) |
| Falsifiable prediction per edit; per-edit keep-or-revert | AHE (2604.25850) |
| Unpruned archive; sigmoid×novelty parents | DGM (2505.22954) |
| MAP-Elites niches; islands; migration | 1504.04909, FunSearch (nature-2024), OpenEvolve, POET (1901.01753) |
| Bounded retries with external signal only | CRITIC (2305.11738), 2310.01798, Self-Debug (2304.05128) |
| Verified-only skill minting; supersedes lineage | Voyager (2305.16291), AgentFactory (2603.18000), RSIAgent (2609.15364) |
| Itemized context with counters; grow-into-skill; caps | ACE (2510.04618), strategy genes (2604.15097), Hermes, EvolveR (2510.16079) |
| Wave barrier before consolidation | RSIAgent (2609.15364) |
| Timescale separation; delayed credit | MetaSkill-Evolve (2607.05297), SkillRise (2607.26784), POWERPLAY (1112.5309) |
| Debate-for-diversity on stagnation | MAD (2305.19118), DTE (2505.15734), 2601.14525 mode-collapse |
| Failure log | PACEvolve (2601.10657) |
| Staged eval gates; cost-in-utility; fixed-duration runs | DGM, SICA, autoresearch |
| Efficiency niche | SoL-Pi (2609.20519) |
| Transactional skill edits | Memento-Skills (repo) |
| Write-tiered memory; kill switch | Letta Code (repo), OpenClaw (repo) |
| Scope-chained host bridges | Agent Zero (repo) |
| Curriculum with frozen-first verifier + admission test | POWERPLAY (1112.5309), Agent0 (2511.16043), RSIAgent |
| Judge isolation / quarantined evaluators | RSIAgent, Hyperagents, SOTOPIA-π (2403.08715) |
| Docker-per-candidate containment | DGM, ALMA, SIA (repos) |

## Appendix B — coverage note

This design was synthesized from a full review pass over the 105 resources tracked in
`ENRICHMENT.md` (all cards source-verified in the enrichment pass; the one exception,
openreview-higher-order-evolution-2024, contributes only its meta-mutation theme). Stage
structure of the source material: (1) evolutionary & open-ended foundations, (2) prompt/program
optimization, (3) self-verification & self-correction, (4) memory & skill evolution, (5) harness
evolution & self-modifying frameworks, (6) multi-agent self-improvement, (7) coding agents,
(8) automated AI R&D, (9) program search & discovery, (10) open-source implementations.
