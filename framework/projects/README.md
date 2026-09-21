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

See `docs/investigation.md` §10/§12 and the decision log (M14).
