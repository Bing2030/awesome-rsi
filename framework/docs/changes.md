# Change register — every change, its status, and where the lesson came from

rsif changes are learned from somewhere: a paper's mechanism or failure
analysis, another codebase's design or implementation, or one of our own live
runs and audits. This register records **every change with that provenance**,
and tracks its lifecycle. It is the single place to answer "what is being
changed, why, based on what source, and where does it stand?"

| Question | Answered by |
|---|---|
| What was built, in what order, with what verification? | [plan.md](plan.md) — milestone status table |
| Which decisions were made, reversed, or corrected — and why? | [decision-log.md](decision-log.md) |
| **Where did each change's lesson come from, and what is its status now?** | **this page** |

A change enters this register when it is first *proposed* (before any code),
moves through the statuses below, and ends up either landed (with its
milestone and verification evidence) or rejected (with the reason — rejected
lessons are lessons too, and recording them prevents re-litigating).

## Entry format

Every entry carries:

- **ID** — `CR-n` (change register); `CRX-n` for rejected/not-adopted items.
- **Status** — ⬜ proposed · 🔬 design agreed · 🔄 in progress · ✅ landed ·
  ⏸ deferred (reason) · ❌ rejected (reason).
- **Sources** — each tagged with its kind:
  - `paper <arxiv-id> §<section>` — mechanism, result, or failure analysis;
  - `code <repo> <path/mechanism>` — a design or implementation lesson taken
    from reading or running another codebase;
  - `internal <run/audit>` — one of our own live runs, reviews, or audits.
- **Change**, **touchpoints** (rsif files), **guards** (what keeps it safe),
  **verification** (how "landed" will be proven).

Entry IDs are stable forever; a landed entry never renumbers.

---

## Open entries

First opened 2026-09-22 from the design review of **RSIAgent**
(paper `2609.15364`, repo `AetherLabsAI/RSIAgent`) — the closest large-scale
cousin of rsif's design published so far: training-free multi-agent RSI
(curriculum/actor/verifier) with memory as the only evolving artifact,
verifier isolated from the actor's reasoning, and frozen-memory test-time
reuse. None of the four adoptions below touch the trust boundary.

### CR-1 — Failure-aware improver context (the "gap map") ✅

**Status:** ✅ landed (2026-09-22, milestone M17). Train-split failure summary
injected as the `{gaps}` slot of `meta/improver-template`; train-only, val
stays aggregate, test sealed. Derived from the memoized active train book
(no extra evaluation). Verified: `tests/unit/test_m17.py::test_improver_
build_prompt_renders_gaps`, `test_train_gaps_text_is_train_only` (val/test
task ids absent; eval-event count unchanged).

**Motivation.** The improver proposes mutations without knowing *where* the
active agent fails. Its prompt
(`src/rsif/evolve/proposer.py`, `build_prompt`) contains only artifact
previews, archive fitness values, and lessons — no per-task outcome
information at all. RSIAgent's #1 failure mode is exactly this blindness:
"insufficiently targeted exploration" — practice that never challenges the
decisions responsible for the target-specific weakness (75% of that mode's
audited cases were target-skill mismatch).

**Change.** Inject a train-split failure summary into the improver prompt (a
`{gaps}` template slot): per-task id, score, and error signature for tasks
the *active* agent fails, capped to a few lines. The data already exists —
`_evaluate` memoizes per-task scorebooks and persists them under
`evals/<gen>/` with error text (`objectives/code_tasks.py` keeps a 300-char
error snippet) — this only surfaces it to the generator.

**Hard constraint (this is where rsif must NOT copy RSIAgent).** RSIAgent's
curriculum sees the target task — its evaluation *is* the benchmark, so there
is no holdout to protect. rsif's val split is an acceptance gate: the gap map
must be **train-split only**; val stays aggregate means; test stays sealed.
Otherwise the improver starts tailoring to specific held-out tasks and the
val gate's meaning erodes.

**Touchpoints.** `evolve/proposer.py` (summary assembly), the improver
template seed (`meta/improver-template`), optionally `evolve/engine.py`
(pass the active agent's train book).

**Guards / verification.** Determinism: the summary is a pure function of
persisted scorebooks. Unit-test prompt contents (train task ids present, val
task ids absent); golden event log regenerated deliberately with unchanged
verdicts.

**Sources.**
- paper `2609.15364` §3.2 (curriculum role: pick tasks from knowledge gaps),
  §4.6 failure mode 1 "insufficiently targeted exploration" + Fig 5a.
- code `AetherLabsAI/RSIAgent` `explore/` — curriculum orchestration from
  gaps; `docs/ARCHITECTURE.md` role table.
- internal: `proposer.py` context audit (2026-09-22).

### CR-2 — Infrastructure failures are not behavioral failures ✅

**Status:** ✅ landed (2026-09-22, milestone M17). `TaskScore.infra` +
infra-aware `ScoreBook.mean` (unscored tasks leave the mean, never read as
0.0); `code_tasks.evaluate` classifies sandbox timeout / spawn `OSError` /
signal-kill as infra; `selection.paired_scores` aligns over commonly-scored
tasks and returns `None` when none compare; the val gate fail-closes when
inconclusive; EVAL events and persisted scorebooks carry `n_infra`/`infra`.
Verified: `tests/unit/test_m17.py` CR-2 block; golden regenerated (9 EVAL
lines gain `"n_infra":0`, verdicts unchanged).

**Motivation.** Today a sandbox timeout, OOM kill, or spawn failure scores
`TaskScore(task, 0.0, error)` — byte-identical to a wrong answer
(`objectives/code_tasks.py::evaluate`). In live runs this can val-reject a
good candidate for infrastructure flakiness and distill insights from
wins that were partly infra noise. Provider-level errors are already handled
correctly (they abort the run cleanly — M13/M15); per-task sandbox-infra
outcomes are the remaining mis-attribution.

**Change.** `TaskScore` gains an infra classification (or an exclude-and-
retry policy) for sandbox outcomes that are infrastructure-class (timeout,
resource kill, executor spawn failure) as opposed to test failure. Gates
treat infra outcomes as *unscored*, never as evidence about the candidate.

**Touchpoints.** `objectives/base.py` (`TaskScore`), `code_tasks.py`
(classify `outcome`), `evolve/selection.py` + `engine.py` (gate arithmetic),
`observe/events.py` (event payload carries the classification).

**Guards.** Determinism: any retry must be bounded, seeded, and logged; the
memo key must not change meaning. An objective that cannot distinguish infra
from behavior keeps today's semantics (the field is optional metadata to the
engine).

**Sources.**
- code `AetherLabsAI/RSIAgent` `docs/ARCHITECTURE.md` (Phase 3): "An
  infrastructure failure is unscored; it is not an official zero";
  `STALLED`/budget exits kept distinguishable from convergence.
- paper `2609.15364` §4.1/Appendix C (protocol: infra errors never become
  PASS or FAIL).
- internal: decision-log M15 (clean-abort on provider errors — same
  principle, different layer).

### CR-3 — Scoped insights (memory entries carry their conditions) ✅

**Status:** ✅ landed (2026-09-22, milestone M17). `Insight.scope` field
(round-trips through persistence, defaults ""); `distill` accepts
`(traj_id, summary, scope)`; `render_for_context` prefixes scoped insights
with `[applies when: …]`; the accept-path distill records `{surface}/{operator}`
as scope. Retirement unchanged. Verified: `tests/unit/test_m17.py` CR-3 block.

**Motivation.** RSIAgent's memory-failure audit found **66.7% of unreliable-
consolidation cases were "rule scope loss"** — a rule learned in one context
retained without its conditions and reused where it is wrong (their example:
treating missing-data markers as valid answers). rsif's `Insight`
(`memory/insights.py`) is free text + provenance + usage counters; retirement
is reactive (`failures_after_use >= 2` — the rule must first *cause* failures
before leaving context). Their phrasing of the lesson is the design note:
*"memory must preserve the conditions and uncertainty of an experience,
rather than treating local acceptance as evidence of general validity."*

**Change.** `Insight` gains an explicit **scope** ("applies when …");
distillation prompts phrase lessons scoped (hypothesis + where it applied);
retrieval surfaces the scope alongside the text. Retirement stays as-is
(usage-grounded), now with scope visible to the consumer.

**Touchpoints.** `memory/insights.py` (schema + render), `evolve/engine.py`
(distill call), improver template (phrasing), golden files regenerated.

**Verification.** Unit: scoped render; retire behavior unchanged; golden
regenerated deliberately.

**Sources.**
- paper `2609.15364` §4.6 failure mode 3 "unreliable memory consolidation"
  + Fig 5c (rule scope loss 2/3 = 66.7%, uncertainty-not-enforced 1/3).
- paper `2308.10144` (ExpeL — existing grounding for insights).
- paper `2510.16657` (model-collapse guard — the existing reason insights
  come only from verified wins).

### CR-4 — Broad-then-deep generation cadence ⏸

**Status:** ⏸ deferred until CR-1 lands (builds on the gap map; biggest of
the four).

**Motivation.** RSIAgent's stage ablation is the cleanest evidence yet for
rsif's archive design: broad-only 65.52 / **deep-only 56.50** (below baseline
on 2 of 4 tasks — pure exploitation from thin memory *hurts*) / both 74.54.
rsif already gets diversity from MAP-Elites + superseded-lineage sampling;
what it lacks is the *cadence*: today every generation is the same shape
(free parent sampling, insights distilled immediately on accept).

**Change.** The scheduler alternates generation kinds: **broad** generations
(diverse sampled parents; insight writes held to generation end — the "wave
memory barrier") and **deep** generations (parent = active best; improver
context = CR-1's gap map of that parent). Cadence knob alongside
`meta_every_k`.

**Touchpoints.** `evolve/scheduler.py`, `evolve/engine.py` (slot loop,
insight-write timing), config.

**Guards.** Determinism preserved (generation shape is a pure function of
generation number + config); golden regenerated; the two-level acceptance
rule is untouched.

**Sources.**
- paper `2609.15364` §3.3 (BRS/DRS staging), §4.4 (stage ablation numbers).
- code `AetherLabsAI/RSIAgent` `docs/ARCHITECTURE.md` Phase 1 (wave barrier:
  branches from a shared pre-wave snapshot, serial consolidation in authored
  order, budgets at wave boundaries).
- internal: `scheduler.py` fast/slow cadence is the existing precedent for
  cadence-by-generation.

---

## Rejected / deliberately not adopted

Recorded so the reasoning survives and is not re-litigated. All four date
from the 2026-09-22 RSIAgent review.

### CRX-1 — LLM verifier as an acceptance signal ❌

RSIAgent's verifier is an LLM reading environment evidence, and its own
§4.6 lists "incomplete verification" (verifier PASS without full requirement
coverage; fidelity gaps 50% of audited cases) as a core failure mode. rsif's
mechanical, executed held-out gates are strictly stronger; LLM judgment
stays advisory context, never a gate (design invariant 4). *Sources: paper
`2609.15364` §3.2, §4.6; internal design.md invariants.*

### CRX-2 — Runtime-grown task or canary packs ❌

RSIAgent's curriculum generates practice and stress-test tasks at runtime.
For rsif this would mean the acceptance instruments (canaries, splits) are
edited by the thing being measured — grader-gaming risk, and canaries must
stay static and trivial to be trustworthy. Task-pack growth belongs to
objective-design time (the solvability-test discipline in
[components/objectives.md](components/objectives.md)). *Sources: paper
`2609.15364` §3.2; internal safety design.*

### CRX-3 — Single-lineage serially-consolidated memory ❌

RSIAgent's memory is one evolving lineage; it cannot backtrack to a
superseded state. rsif's MAP-Elites archive + two-level acceptance
(archive-accept vs promote) supersedes this — the demo's generation 3
(accepted, not promoted) is exactly the capability RSIAgent lacks.
*Sources: paper `2609.15364` §3.3; internal archive design [1504.04909,
1901.01753].*

### CRX-4 — Target-task detail visible to the improver ❌

RSIAgent's curriculum uses the target query as reference — correct for its
setting, wrong for rsif's: our val split is an acceptance gate, and
per-task val detail in the improver context would invite tailoring to the
held-out set. The gap map (CR-1) is train-only by construction.
*Sources: paper `2609.15364` §3.3/§4.1; internal splits discipline
[2605.23904].*

---

## Landed history (backfill)

The register starts 2026-09-22; earlier changes are backfilled from
[plan.md](plan.md) and [decision-log.md](decision-log.md) with their lesson
sources. Full detail lives in those records; this table is the provenance
index.

| Milestone | Change (one line) | Lesson sources |
|---|---|---|
| M0 | Scaffold + tracked plan doc | internal (greenfield conventions) |
| M1 | Artifacts & lineage: immutable versions, append-only lineage, checkout | paper 2410.04444 (behavior as inspectable/rewritable code); paper 2510.04618 (bounded incremental edits) |
| M2 | LLM layer: one-method Protocol, capped adapters, disk cache | internal engineering (risk table: provider abstraction creep) |
| M3 | Sandbox + hidden-test objective | paper 2603.03329 (guard layers before execution); paper 2605.23904 (held-out splits discipline) |
| M4 | Runtime + module ABI (modules see only their context) | paper 2408.08435; paper 2410.04444 |
| M5 | Memory: episodic / insights / playbook / retrieval | paper 2303.11366 (Reflexion); paper 2308.10144 (ExpeL); paper 2510.04618 (ACE); paper 2502.12110 (A-MEM) |
| M6 | Engine v1 + MAP-Elites archive + golden determinism | paper 1504.04909; paper frontiers-quality-diversity-2016; paper 2505.22954 (DGM: only evaluated improvements kept); paper 1901.01753 (stepping stones) |
| M7 | Module surface + META recursion + fast/slow scheduler | paper 2310.02304 (STOP); paper 2309.16797 (Promptbreeder); paper 2607.05297 (two-timescale loop); paper 2408.08435 |
| M8 | Safety hardening: gate chain, drift, budget, approvers, rollback, two-level acceptance | paper 2509.26354 + 2603.06333 (misevolution expected); paper 2506.13131 (cascade + budgets) |
| M9 | CLI + phase-attributed observability + reproducible demo | paper 2604.25850 (edit-attribution observability) |
| M10 | design.md + live smoke + PDF citation spot-checks (5/6 confirmed, DGM partial) | internal (design.md §10 audit) |
| M11 | Second objective (exact-match) — task-agnostic seam proven | internal (requirement R2 proof) |
| M12 | Overall review: dead-code audit, design↔implementation reconciliation, provider-error clean abort | internal audit; paper 2310.01798 (self-correction negative result, grounding for gates) |
| M13 | External-review fixes: provisional META windows, import whitelist, paired net-gain floor, superseded-lineage ε-reseed | internal review; paper 2605.23904 (acceptance floor); paper 1901.01753 (reseed source) |
| M14 | Third objective (regex) via public seams + live gateway run | internal live run (decision-log M14) |
| M15 | Extraction-contract fix + clean abort on post-run provider errors | internal live run #3 (decision-log M15 — first candidate to clear canary after fix) |
| M16 | Fourth objective (harness-efficiency) + POLICY artifact bounding injected memory | paper 2609.20519 (SoL-Pi: predeclared capability floor; efficiency gated by non-regression) |
| M17 | CR-1 train-split gap map in improver prompt · CR-2 infra failures unscored · CR-3 scoped insights | paper 2609.15364 §3.2/§4.1/§4.6; code AetherLabsAI/RSIAgent ARCHITECTURE.md Phase 3; paper 2308.10144; paper 2510.16657 |

## Maintenance

- A new change gets a `CR-n` entry here **before** implementation starts.
- Moving ⬜→🔬 requires the design paragraph to be complete; 🔄 adds a plan.md
  milestone row; ✅ records verification evidence here and links the
  milestone; ❌/⏸ records the reason and date.
- Landed entries are never rewritten — corrections go to
  [decision-log.md](decision-log.md) and the register row gains a pointer.
