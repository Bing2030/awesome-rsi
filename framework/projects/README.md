# projects/ — real projects built on rsif

Each project uses the framework through its **public seams only** (custom
`Objective` + `EvolutionEngine` API + a provider) and doubles as a live
validation that those seams hold.

## regex_agent — a third objective, run against a real model

The agent must produce a regular expression matching given positive and
negative examples; grading compiles and executes the pattern in the sandbox
(`projects/regex_agent/objective.py`). Run it live through the gateway:

```bash
cd framework
uv run python -m projects.regex_agent.run --run ../runs/regex \
    --model glm-5.3-flash --generations 2 --proposals 1
```

- Reads the gateway from `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`.
- Hard budgets: `--budget-usd` (1.0), `--budget-calls` (120),
  `--budget-wall-s` (1800). Responses are disk-cached — a same-seed re-run
  replays without new spend.
- META edits are fail-closed when non-interactive (pass `--tty` for the
  y/N approver).
- Prints the val trace (baseline → each candidate), accept/reject lines,
  and the sealed test split on the archive best after the run.

Offline deterministic proof (no network, no cost):
`tests/integration/test_regex_project.py` — val 0.2 → 0.4 → 1.0 through two
accepted prompt edits, plus a solvability invariant over the task pack
(every reference pattern must pass its own examples — this caught
`colou?r` matching inside "colorr" before it could poison scoring).

## Live run record (2026-09-21, glm-5.3-flash via gateway)

2 generations × 1 proposal, 29 LLM calls total (caps: 120 calls / $1 / 30 min),
exit 0, budget held, no ratchet:

```
baseline:  train 6/6   canary 2/2   val 3/5 = 0.60   <- real held-out gap
g1p1: prompt/refine "add a verification pass"   -> child train 0.5 -> REJECT at screen
g2p1: prompt/refine "restated requirements + FINAL ANSWER line"
                                              -> child train 0.0 -> REJECT at screen
active agent stayed at seed (val 0.60); sealed test on archive best: 0.50
```

What this demonstrated on a real model:

1. **The cascade screen did its job**: both plausible-sounding prompt edits
   regressed train performance and were rejected at the *cheapest* gate —
   the canary/val gates never had to run (AlphaEvolve-style cost control).
2. **Reflection fed forward**: the g1 reflection correctly diagnosed the
   failure ("a zero is qualitatively different — a hard failure, not a
   marginal miss"), and the g2 improver proposal was visibly shaped by it
   (smaller patch, explicit output-format fix).
3. **Emergent harness lesson** (recorded, not fixed here): instructing the
   model to "verify before answering" makes it emit reasoning prose first,
   and the objective's extractor takes the first non-empty line — so
   strategy prompts that add discipline *break the output contract*. The
   g2 "FINAL ANSWER:" line was the right repair direction but lands
   mid-text; a follow-up should teach the extractor to prefer a marked
   final line. The gates prevented this interaction from ever deploying.
4. **No improvement was found in 2 proposals** — reported honestly. Correct
   rejection of regressions is the machinery working; fitness improvement
   on this objective likely needs more generations or the extractor fix.

## Live run record #2 (2026-09-21, glm-5.3-flash, second seed trajectory)

3 generations × 1 proposal, ~35 calls (cap 120), exit 0 — and a richer gate
story than run #1: **three different gates fired on live traffic**:

```
baseline:  train 4/6   canary 2/2   val 4/5 = 0.80
g1p1: child train 0.0                       -> REJECT at screen
g2p1: screen passed (0.5)                   -> REJECT at canary (0.5 < 1.0)
g3p1: screen PERFECT (train probes 1.0!)    -> REJECT at canary (0.5 < 1.0)
active stayed at seed (val 0.80); sealed test on archive best: 0.75
```

g3 is the diagnostic highlight: the improver found a prompt that aced the
train probes yet still could not deploy, because it broke the trivial
canary tasks — train-visible improvement + canary regression is exactly
the misevolution the never-regress gate exists to block [2509.26354].

## Live run record #3 (2026-09-21, glm-5.3-flash, first run with the M15 extractor fix)

3 generations × 1 proposal, baseline val 0.80 — and the **first live
candidate to clear the canary gate**:

```
baseline:  train 6/6   canary 2/2   val 4/5 = 0.80
g1p1: child train 1.0 (screen passed)   -> REJECT at canary (0.5 < 1.0)
g2p1: child train 1.0 (screen passed)   -> canary 1.0 (PASSED — first ever)
    -> train 1.0 -> val acceptance eval -> gateway RateLimitError (5-hour limit)
run aborted cleanly (stop_reason error:RateLimitError)
```

g2 is the payoff of the M15 fix: the task contract now *permits* step-by-step
reasoning and demands a marked final line, and `extract_pattern` prefers that
line — so a candidate that reasons in prose no longer scores 0 on the canaries.
All five pre-M15 proposals died on this exact interaction (reasoning prose
scored as the "pattern"); g2 is the first to survive it.

The only blemish: `run.py`'s post-run sealed-test evaluation re-invoked the
provider after the clean abort, and the uncaught `ProviderError` made the
process exit 1. **Fixed in M15**: the sealed-test evaluation is now wrapped,
a rate limit / budget hit there prints a "skipped" line and exits 2 instead of
tracebacking (see the decision log). The engine's own clean abort was never in
doubt — `run_end` was written before the crash.

Cross-run conclusion (7 live proposals, 6 correctly rejected, 1 pending a
rate limit, zero regressions deployed): the recurring failure mode is confirmed —
verbosity-adding prompts break the first-line extraction contract, and the
simplest tasks (canaries) detect it first. **Fixed in M15**: the task
contract now permits reasoning and demands a marked final line, and the
extractor prefers that marked line (see `objective.py`).

See `docs/investigation.md` §10/§12 and the decision log (M14/M15).

## harness_efficiency — the first cost-aware objective (SoL-Pi)

The fourth objective, and the first that prices token spend. Instead of a
separate efficiency gate, `EfficiencyObjective`
(`projects/harness_efficiency/objective.py`) folds cost into the per-task
score:

```python
score = correctness - LAMBDA * min(1, (input_chars / 4 + out_tokens) / TOKEN_BUDGET)
```

with `LAMBDA = 0.1`, `TOKEN_BUDGET = 500`. This is a **quality-first scalar
floor**: cost can never promote a wrong answer nor push a correct one below
0.9, so the existing val threshold + M13 paired net-gain floor enforce
SoL-Pi's "predeclared capability floor" [2609.20519] *unchanged*.

The task pack is a deliberately trivial echo task (output the target after
an `ANSWER:` marker) so correctness and token cost are the *only* things
that vary. Two proofs, both offline and deterministic:

- **Output efficiency (3a)** — `tests/integration/test_harness_efficiency.py`
  `test_efficiency_objective_prefers_concise_over_verbose`: a concise-correct
  candidate is accepted over a verbose-correct one (val 0.91 → 0.97) while a
  concise-wrong candidate is screened (~−0.01).
- **Context efficiency (3b)** — a new `POLICY` artifact (`policy/context`)
  bounds injected memory via `max_memory_chars`; tightening it lowers
  `input_chars` and is accepted as context compaction under the same floor
  (`test_context_policy_bounds_injected_memory`,
  `test_context_policy_tightening_is_accepted`).

A `run.py` (mirroring `regex_agent/run.py`) drives the same objective live
through the gateway — same budgets, disk cache, and fail-closed META — but
no live-run record is committed here; the seam is proven deterministically,
with **zero engine changes**. The only engine-adjacent touch is
`Attempt.input_chars`, an additive field the runtime records (system + task
prompt length) so a cost-aware objective *can* see input cost — it defaults
to 0 and changes no other objective or golden byte.

See `docs/investigation.md` §10/§12 and the decision log (M16).
