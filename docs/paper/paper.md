# Petri: An Append-Only Testbed for Measuring Harness Self-Improvement in Coding Agents — and Seven Ways Naive Measurement Gets It Wrong

<!-- Draft 0.2 (skeleton + abstract/intro + CS catalog). B+C framing: (B) instrumented testbed, (C) measurement-failure catalog.
     Venue target (see VENUES.md): Trust4RSI-Agent @ AAAI 2027 — due Nov 20, 2026 AoE (8pp full, double-blind,
     AAAI-27 author kit); arXiv after submission/notification. Figures: see FIGURES.md. Companion artifacts:
       - numbers.md  (every figure, regenerated from records by collect-numbers.mjs — never hand-edit)
       - petri repo  (testbed + append-only spine; commit a77d9ba at time of drafting)
     TITLE ALTERNATIVES (pick at submission):
       - "Petri: An Append-Only, Pre-Registered Testbed for Measuring Self-Improvement in Coding Agents"
       - "Measuring Self-Improvement in Coding Agents: A Testbed and a Failure Catalog"
-->

**Authors**: [anonymized for review]

**Draft status**: working draft. Sections marked ⟦pending-evolve⟧ resolve when the pre-registered experiment (spine/evolve/2026-10-09-plan.md) completes; both instrument readings will be reported (see CS2).

## Abstract

Claims of self-improving coding agents — systems that rewrite their own harnesses, prompts, or memories to get better at their work — are hard to evaluate. Published systems conflate multiple simultaneous changes, rarely report costs or repeat variance, and the measurement apparatus itself (benchmarks, verifiers, cost meters, acceptance rules) fails in ways that inflate, mask, or invert the reported signal. We present two contributions. First, **Petri**, a minimal append-only testbed for studying harness self-improvement in coding agents: an immutable "spine" of recorded runs; a *genome* of plain-text agent guidance that changes only through pre-registered, human-merged promotion gates; a referee that never trusts agent self-report; reward-hacking canaries embedded in the task bank; and a hard budget governor. The supervisor is ~2,700 lines of plain-file tooling; every mechanism is end-to-end verified at $0 before any API spend, and every number in this paper regenerates from the recorded spine by a single script. Second, a **catalog of seven measurement failures** we encountered while operating the testbed on ~$63 of API spend — pass-rate saturation, k=1 noise interacting with an acceptance margin, a negative Wilson confidence bound that silently made every score-tied candidate inadmissible mid-experiment, infra-stalls recorded as task failures at $0 cost, verifier defects that fail already-solved tasks, reward-hacking pressure on planted canaries, and curriculum self-dealing in self-generated tasks. Each is presented as *naive practice → observed incident (with record IDs) → defense → measured outcome*. The testbed did produce measured improvements — a distilled genome that cut average turns 16% at ~equal cost (one shared task regressing, within the acceptance floor), and a 15-bullet genome that raised same-bank pass rate from 87.5% to 100% while cutting cost 15% and turns 33% — but the experiment we most expected to yield further gains instead yielded a clean null with mechanism-level explanations (distillation from all-pass traces produces zero insights; mutating a saturated incumbent regresses it). We argue the nulls and the failures are the transferable results: they are what self-improvement claims look like when the instruments are honest.

## 1. Introduction

A growing literature asks whether coding agents can improve the systems they run in — rewriting their own prompts, tool wrappers, verification scripts, or task-selection policies [survey pointer; 104-card corpus in Appendix A]. Reported results are hard to trust, for reasons that are mostly *not* dishonesty:

- **Conflation.** A "self-improvement" run typically changes many things at once (prompt, retrieval, model version, benchmark version). When the number goes up, no measurement attributes the gain; when it goes down, no record explains which change did it.
- **Missing instruments.** Of the 104 source-verified papers and repositories in our study corpus, only 56 even mention ablations, and pass-rate-style headline numbers dominate. Repeat variance, per-run cost, and infra-stall rates — the quantities that decide whether a delta is real — are almost never reported.
- **Instruments that fail silently.** The measurement layer is itself software, written by the same process under test. We observed a confidence-bound implementation that returned *negative* tolerances (making every score-tied acceptance decision impossible), verifiers whose shell-quoting failed on solved tasks, and watchdog kills recorded as task failures at $0.00 cost. None of these announce themselves; they surface as (respectively) a stuck experiment, a "hard" benchmark, and free failures.

This paper describes our attempt to study harness self-improvement under measurement discipline, and what the discipline cost and found. **Petri** (Section 3) is a deliberately small testbed: a bank of real work-domain tasks generated by mutating a real repository snapshot; a runner that executes a coding agent headlessly against each task; a *genome* — a plain-text file of guidance bullets injected into the agent's context — as the unit of self-improvement; a distiller that turns recorded failure traces into candidate genome edits; and a gatekeeper that applies a pre-registered acceptance rule (score parity within a measured noise floor, cost within a budget) and emits a *proposal* that a human merges. Nothing auto-promotes. The spine is append-only: runs, gates, refusals, and budget are files under git, and the pre-registration comes first (predictions and decision rules recorded before spend).

Operating Petri over three weeks and ~$63 produced three kinds of results:

1. **Measured improvements, attributable and cheap** (Section 5): paired same-task comparisons from the records — the first distilled genome cut turns 8.5→7.1 (−16%) at −3.5% cost with one task regressing (0.944 vs 1.000, inside the acceptance floor); the 15-bullet v6 genome raised pass rate 87.5%→100% while cutting cost 15% ($0.433→$0.368/run) and turns 33% (12.9→8.6) on the same 8 tasks.
2. **A clean null with mechanisms** (Section 5.3): a pre-registered 5-generation experiment racing greedy vs. archive parent-selection on a saturated 6-task slice accepted **zero** of ten candidate generations. The mechanisms are legible in the records: distillation over all-pass traces yields zero insights (nothing to learn from success); the one generation where failure-derived edits were applied regressed pass rate by 16.7 points; cost-parity candidates were wrongly rejected by a buggy acceptance margin (CS2) — a result we report under both the buggy and fixed instrument rather than retconning it.
3. **A catalog of measurement failures** (Section 4): seven distinct ways naive measurement gets self-improvement wrong, each encountered in our own records, each now with a defense in the testbed. Two of the seven are bugs in *our own* instruments, found by the testbed's reproduction discipline — included because a measurement paper that only catalogs others' failures would be suspect.

We wrote this paper primarily for researchers building or evaluating self-improving agents. The claim we defend is narrow: **before asking whether an agent improves itself, fix what "better" is measured with** — because at every stage where improvement could hide or be hallucinated (acceptance rules, verifiers, cost meters, task generation, reward hacking), we observed a concrete failure that a plain-file, append-only, pre-registered apparatus either prevented or caught after the fact.

### Contributions

1. **Petri testbed** (open, ~2,700 LOC, plain files): append-only spine, pre-registered gates, referee-verified runs, canary tasks, curriculum protocol, budget governor; every mechanism e2e-verified at $0 before spend.
2. **A seven-entry measurement-failure catalog** with incidents, record IDs, defenses, and measured outcomes (CS1–CS7, Section 4) — including two instrument bugs in our own gatekeeper.
3. **A pre-registered evolution experiment** (greedy vs. archive parent selection, 5 generations × 2 arms, deterministic 6-task slice) resolved honestly under both instrument readings, with mechanism-level null explanations.
4. **A source-verified corpus analysis** (105 resources; 104 cards) quantifying how rarely the literature reports the instruments this paper argues for (56/104 mention ablations).

## 2. Background and Related Work

⟦~1 page; compact, drawn from the 104-card corpus (Appendix A). Taxonomy buckets already established in docs/rsi-agent-design.md §2 — reuse, do not re-derive:⟧

- **Test-time prompt/strategy optimization** (Promptbreeder, OPRO, DSPy, TextGrad, ADAS/Meta-Agent-Search, STOP): the genome-and-gate structure directly parallels these; Petri adds repeat-variance-aware acceptance and cost accounting.
- **Evolutionary / open-ended** (DGM, AlphaEvolve, FunSearch, POET, POWERPLAY, quality-diversity archive methods): Petri's breeder (bounded, double-screened mutation; archive parent sampling by pass-rate × novelty; annealed edit budget) is a minimal instantiation; POWERPLAY is the direct ancestor of the curriculum protocol (CS7).
- **Memory and experience** (Voyager, Reflexion, ExpeL, A-MEM, agentic-context-engineering line): the distiller is the analogous component, with the difference that its output is gated and its inputs are referee-verified traces.
- **RL / finetuning-based self-improvement** (SWE-agent training line, Agent0, EvolveR, Harness-Zero, RRSI): out of scope for Petri's weights-frozen setting, but the measurement catalog applies unchanged.
- **Evaluating agent claims** (agent-benchmark critiques, contamination literature): CS4/CS5 connect; Petri contributes canary tasks *inside* the work domain rather than separate probes.

**Gap this paper occupies**: instrumentation and measurement hygiene for self-improvement claims specifically — not a new improvement method, but the apparatus that makes any method's claims checkable.

## 3. The Petri Testbed

⟦~2 pages. Cover, with a component diagram (Figure 1: genome → runner → referee → spine → distiller → breeder → gatekeeper → human merge loop):⟧

- **3.1 Task bank.** 62 tasks (60 work-domain mutations of a real repository snapshot — JSON repairs, doc/table regenerations, refactors with gold diffs — plus 2 canaries, Section 4 CS5). Tasks carry `prep`/`verify`/`allow`; verify is executable, never agent-graded.
- **3.2 Runner.** Headless coding agent, watchdog (420 s), acceptEdits permission, max turns; frozen-spine invariant (spine hashed before/after each run; violation ⇒ score 0 and a recorded `spine_violations` field).
- **3.3 Genome.** A plain-text file of guidance bullets (`<!-- id:G-nnn -->` markers for ablation). Current incumbent: v6.1, 15 bullets. The only thing the loop may change.
- **3.4 Gatekeeper.** Pre-registered accept rule: candidate score ≥ incumbent score − δ AND Δcost ≤ β0 + β1·max(0, Δscore) (β0=0.15, β1=0.5), δ from incumbent repeat spread when available, else Wilson 95% half-width. Output is a *proposal*; admissibility is a floor (necessary, never sufficient); every promotion is human-merged. Critic screen (6 regex pattern families) over operative bullets only.
- **3.5 Distiller, breeder, archive.** Traces → evidence corpus → insights (failure-focused); bounded mutation screened against the failure log *and* the critic; unpruned archive with pass-rate × novelty parent sampling; niches by archetype × cost band.
- **3.6 Curriculum (POWERPLAY protocol).** Agent-proposed tasks admitted only if the verifier is frozen (sha-pinned, `bash -n`-checked) *before* incumbent attempts, and the incumbent fails k≥2 attempts with the verifier sha unchanged. Refusals are recorded as first-class outcomes.
- **3.7 Governor.** Hard $80 lifetime cap checked before every run; incremental per-experiment envelopes; watchdog-killed runs recorded explicitly as stalls, not failures.
- **3.8 Operating discipline.** Pre-register predictions before spend; e2e-verify every mechanism at $0 (fake-agent harness); append-only records committed before resolution; never retcon a recorded score — fix the instrument, re-gate from records, report both readings (this paper does so twice).

⟦Include the numbers.md campaign table as Table 1 reference; costs per run; the spine layout listing.⟧

## 4. A Catalog of Measurement Failures

Each entry: **naive practice → observed incident (record IDs) → defense now in the testbed → measured outcome.** All incidents are ours; record IDs resolve in the appendices' regenerated tables.

### CS1 — The saturation ceiling

*Naive practice:* report pass rate as the improvement metric. *Incident:* after the v3 promotion, pass rate stopped moving — 94–100% on every subsequent campaign; the pre-registered evolve experiment's incumbent scored 6/6 on its slice, so *every* candidate generation scored d=0 on the headline metric (spine/evolve/log.jsonl, gens 1–3). *Defense:* the acceptance rule gates on cost at score parity (Δcost ≤ β0 + β1·max(0, Δscore)); turns and $/run are first-class columns in every campaign table. *Outcome:* on a saturated slice the entire signal lives in cost — real cost differences of −$0.009 to −$0.035/run were measurable where pass rate said "nothing happened." But saturation is also where the acceptance margin does all the work, which is exactly where CS2 hid.

### CS2 — k=1 noise, the acceptance margin δ, and a bug inside the fix

*Naive practice:* accept a candidate that ties or beats the incumbent, with one repetition per task. With k=1, score deltas are coin flips; the standard fix is an explicit tolerance δ. *Incident (two layers):* (a) The one shared-task regression in the v1 promotion (0.944 vs 1.000) passes in every later campaign — a k=1 artifact a naive reader would score as a real regression, and a naive promoter would have scored as a real gain elsewhere. (b) Our δ implementation *was the bug*: to keep the Wilson bound defined at p=1, we clamped the point estimate below 1.0 and returned `upperBound − clampedP` — which goes **negative** at high p (−0.123 at p=1, n=6; the printed gate deltas of −0.11 to −0.123 during the evolve run). A negative tolerance makes *every* score-tied candidate inadmissible: the first half of the experiment was rejected by arithmetic, not evidence. *Defense:* δ returns the interval **half-width** `s/(n+z²)` (+0.0395 at p=1, n=6); precedence explicit override > measured incumbent repeat spread > Wilson fallback; a regression test pins the bound itself (7/7, including both historical gate verdicts unchanged). *Outcome:* mid-experiment instrument fix, applied the way the discipline requires — recorded cards untouched, all gates re-run post hoc from records, and **both readings reported** in Section 5.3 rather than retconned. Interim: 5 of 7 completed generations were rejected on score-tied gates under the buggy δ; four of those show negative Δcost (apparent improvements) whose admissibility flips under the fixed bound ⟦final numbers pending run completion⟧.

### CS3 — Infra-stalls scored as failures, at $0.00

*Naive practice:* a watchdog-killed session gets score 0 and whatever the cost meter says — usually nothing. *Incident:* 16 of 362 recorded runs are stalls (turns=null + watchdog kill at 420 s) across 11 campaigns, all recorded at **$0.000** — pass rates computed naively are depressed (e.g. evolve-greedy-g1 reads 67% instead of 100%-of-scored) and lifetime spend is undercounted. Worse, the first gatekeeper implementation silently *dropped* them: the v4 campaign scored a perfect 1.0 on "7 shared tasks" because its one failing stall (`json-cascade-1`, run `…muyuz3mc`) vanished from the input (found by re-running a historical gate). *Defense:* the stall signature is excluded from scoring but **listed**; any gate over a stalled campaign is marked PROVISIONAL naming the runs to re-run; budget reporting states the undercount estimate explicitly instead of absorbing it. *Outcome:* zero silent drops since codification; the four stall-heavy campaigns (3–4 stalls each) are exactly the ones whose verdicts carry PROVISIONAL today.

### CS4 — Verifier defects that fail solved tasks

*Naive practice:* the referee is trusted; a FAIL means the agent failed. *Incident:* self-generated curriculum task `self-quietdup-1` (verifier sha `9076748d…`) recorded FAIL on both incumbent attempts — but every verify error was `bash: syntax error near unexpected token '('`: an apostrophe in the embedded expected content had broken the verify command's own shell quoting. A $0 comparison (working directories deep-equal the expected deduplicated array) proved the agents had *solved* the task twice. The naive readings — "hard task," "weak agent," "self-improvement needed" — are all wrong; the instrument was broken. *Defense:* every frozen verify command is now `bash -n` syntax-checked at freeze time (a frozen broken verifier poisons every attempt after it — this would have caught the defect at $0); adjudication can void a *task* without voiding any *record*; the re-frozen successor (`self-quietdup-2`) used a quoting-proof verifier. *Outcome:* two refusals on the books, zero poisoned attempts since the guard landed; total cost of the incident + fix: $0.19 spend + one evening.

### CS5 — Reward hacking pressure, and canaries inside the work domain

*Naive practice:* probe for benchmark gaming with separate held-out evals, or not at all. *Incident and defenses (three layers):* (1) A **critic** screens every candidate genome bullet against six pattern families (task-id conditioning, corpus card keys, hardcoded digests, campaign labels, verify-gaming phrasing, task-conditioning); a deliberate red-team batch of 7 adversarial edits was caught 7/7 with 4/4 clean controls unflagged. The incumbent's self-screen flagged 2 bullets — both evidence citations in parentheses, cleared on review and moved to unscreened provenance comments; the screen also initially flagged its own provenance headers until restricted to operative bullets. A defense with false positives is a defense people turn off; the fix kept the screen alive. (2) **Canary tasks inside the bank:** `canary-logging-1` fails unless the run's own telemetry ledger exists with ≥3 events including an Edit (fails closed when the harness is absent); `canary-spine-1` plants a lure file (`TASK-NOTES.md`) claiming maintainers permit editing the grading manifest at an absolute spine path. *Outcome:* 2/2 canaries green under temptation ($0.399): the ledger canary saw 8 events; the spine canary's ledger shows the agent **read the lure (2 references) and still did not touch the grading manifest** — and the frozen-spine invariant (spine hashed before/after every run, violation ⇒ score 0 + recorded `spine_violations`) would have caught it if it had. Zero spine violations on every run since the invariant shipped (all campaigns from `canary-v7-2026-10-09` onward).

### CS6 — Attribution gray zones: which bullet, which container

*Naive practice:* compare before/after campaign averages and credit the visible change. *Incidents:* (1) *Container conflation:* campaign averages suggest "everything got more expensive under the v6 era" ($0.153 → $0.365/run) — but the *task bank* changed between those numbers, not the genome; paired on the same bank, the v6 genome is 15% *cheaper* than its incumbent. (2) *Bullet attribution:* removing bullet G-204 measured **+$0.105/run** (gate `ablate-no204-vs-gate-v6-v5`: admissible, more expensive — kept the bullet, on the record); removing v1's two anchor bullets (G-002, G-008) produced an apparently-better campaign (100% pass, 6.2 vs 7.1 turns) that fell inside the noise floor — the instrument could not distinguish them and said so, and the genome was left alone. (3) The v4 rejection: admissible on paired score+cost (1 vs 1, Δ$0.007) yet **not promoted** — the human merge weighed falsifiable-prediction resolution (0/4 true) and an absolute cost bar the floor never sees. *Defense:* ablation as a first-class command; paired-by-task comparisons everywhere; gates emit *proposals* whose `note` field records that the floor is blind to evidence it doesn't take as input. *Outcome:* every promotion in Section 5.1 carries both a paired comparison and a human rationale; no promotion rests on a container-crossing average.

### CS7 — Curriculum self-dealing

*Naive practice:* let the agent propose tasks to train on; add the ones it "discovers" it cannot do. An agent graded on a bank it influences will manufacture solvable-but-impressive-looking tasks. *Incident/protocol:* both live self-generated proposals were **refused** — `self-quietdup-1` because its verifier was defective (CS4), `self-quietdup-2` because the incumbent solved it on both attempts (runs `…mv04t9dd`, `…mv04tq0f`), which is the pre-registered POWERPLAY rule working: admission requires the verifier frozen (sha-pinned, syntax-checked) *before* k≥2 incumbent attempts, all attempts failed, sha unchanged. *Defense:* freeze → attempt → adjudicate → admit-or-refuse, all states append-only in `spine/curriculum/index.jsonl`; admissions capped at 15% of the bank; a refused proposal stays as evidence and the next candidate must target a different failure shape. *Outcome:* 0/2 admitted at $0.79 total — the honest reading is "the incumbent is currently strong enough to solve what it proposes," and the protocol's refusal is recorded as a *result*, not an embarrassment.

## 5. Results

⟦~1.5 pages. Tables regenerate from numbers.md; do not hand-copy.⟧

- **5.1 Promotions.** All paired numbers from numbers.md ("Pre-gatekeeper promotions" + gates sections): genome v1 (6 bullets, distilled from baseline failures) — turns 8.5→7.1, cost $0.159→$0.153, score 0.944 vs 1.000 on 6 shared tasks (the one regression, json-repair-1, passes in every later campaign — itself a CS2 k=1 artifact); ablation of v1's two anchors regressed to noise. v3 (11 bullets): 96–100% pass across two banks. v6 (15 bullets): 87.5%→100% pass, −15% cost, −33% turns on 8 shared tasks. Human-merged every time; the gate is a floor. Genome v4: admissible-provisional but **not** promoted (a stall + falsifiable-prediction resolution outweighed the floor — "necessary, not sufficient" exercised for real).
- **5.2 Defenses exercised live.** Canaries 2/2 green under a read-and-resisted lure; curriculum refusals 2/2 (CS7); critic screens: ⟦red-team confusion-matrix figure, task #4⟧.
- **5.3 Evolve experiment (pre-registered; plan in spine/evolve/2026-10-09-plan.md).** 5 generations × 2 arms (greedy single-lineage vs archive parent sampling), deterministic 6-task slice, seed 20261009, $16 incremental envelope. E1–E5 predictions and decision rules pre-recorded. ⟦pending-evolve: fill final table, re-gated under fixed δ, both readings, E1–E5 resolutions, spend⟧. Interim reading: incumbent 6/6 PASS; distill-from-success ⇒ 0 insights twice; greedy-g3 (first failure-derived edits applied) regressed −16.7 points; archive arm showed consistent cost gains (−$0.009 to −$0.035/run) that the buggy δ rejected.
- **5.4 Budget.** $63.08 of $80 recorded (⟦update at resolution⟧), all incremental envelopes pre-approved; metering undercount from CS3 stated, not hidden.

## 6. Threats to Validity (the honest list)

Single work-domain (one repository snapshot's task family); single substrate (one model behind one API; glm-5.3-class); small k (k=2–3 on most campaigns — δ exists because of this); saturated slice for the headline experiment (chosen deliberately, and it is *why* the null is legible); 2-operator human gate (promotion decisions are ours); genome effect sizes near the noise floor. None of these are hidden by the apparatus — that is the apparatus working.

## 7. Discussion

⟦What generalizes (append-only spine, pre-registration, floor-not-decider gates, canaries, refuse-as-outcome); what we'd do differently (k≥3 from day one; cost-metering before stall-signature; Wilson bound tested against p=1 first); positioning: a null from a working apparatus vs. a positive from an unauditable one.⟧

## 8. Conclusion

⟦Two paragraphs: the catalog as the reusable artifact; the testbed as the minimal reproducible substrate; invitation to run claims through it.⟧

## Appendix A — Corpus

105 resources (31 repositories, 74 papers); 104 source-verified cards; 56/104 mention ablations; full operationalization and regeneration in numbers.md.

## Appendix B — Reproduction

`node docs/paper/collect-numbers.mjs > docs/paper/numbers.md` regenerates every figure from the two repos at pinned commits. ⟦spine layout; per-claim record pointers (gates, campaign IDs, ledger run IDs).⟧

## Appendix C — Gate ledger

All recorded gate verdicts with rule parameters, δ sources, stalls, and human outcomes (from spine/gates/; regenerated into numbers.md).
