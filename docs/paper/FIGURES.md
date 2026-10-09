# Figure plan — 3 figures, data-driven where possible

Principle (same as numbers.md): every figure regenerates from recorded state; hand-drawn only for F1. Each spec lists the exact source and the check that the rendering matches the records. Tools: `dot`/`mermaid` for F1; `matplotlib`-free approach preferred — emit structured JSON/DOT from collect-numbers.mjs and render with dot or a small HTML/SVG snippet, so regeneration needs no pip installs.

## Figure 1 — Testbed control loop (§3, static)

One diagram, left-to-right: **genome** → **runner** (headless agent · watchdog 420 s · frozen-spine hash before/after) → **referee** (executable verify, never agent-graded) → **spine** (append-only: scores · gates · ledger · curriculum · budget) → **distiller** (failure-focused, traces→insights) → **breeder** (bounded edits · critic screen) → **gatekeeper** (floor: δ/β accept rule → *proposal*) → **human merge** (arrow back to genome, labeled "the only path that changes the genome").

- Annotate each edge with the CS defense that lives there: runner→spine "CS3 stall signature", gatekeeper "CS2 δ", referee "CS4 bash -n", breeder "CS5 critic", spine "append-only = CS6 attribution".
- Render: mermaid or DOT; version the source in `docs/paper/fig1-loop.mmd` (hand-written, reviewed like prose).
- Check: every arrow corresponds to a real code path (petri.mjs commands), no implicit auto-promote arrow — the human-merge arrow must be the only one entering the genome besides "author edit".

## Figure 2 — Genome lineage timeline (§5.1, data-driven)

Horizontal timeline Sep 23 → Oct 10; genome versions as nodes: baseline → **v1** → **v3** → **v4** (admissible, *not* promoted — draw as rejected fork) → **v6** → v6.1 (current). Edge labels carry the paired-by-task deltas **from numbers.md PAIRED + gates only**:

- baseline→v1: `turns 8.5→7.1 · cost −3.5% · 0.944 vs 1.000 (6 shared; 1 task regressing = CS2 artifact)`
- v3-era edges + v5→v6: `pass 87.5%→100% · cost −15% · turns −33% (8 shared)`
- side stubs: ablation G-204 `+$0.105 → kept`; v1-anchor ablation `→ noise floor, genome unchanged`; v4 fork `floor said yes, human said no (0/4 predictions)`
- right side, boxed: evolve run `10 arm-generations, 0 accepts` + curriculum refusals `0/2 admitted` + canaries `2/2 green`

- Data: extend `collect-numbers.mjs` with a `--fig2` mode emitting `fig2-lineage.json` (nodes/edges/stubs from the same PAIRED and gates computations — no new numbers). Render: DOT with `rank=same` per date band.
- Check: every label string must appear verbatim in numbers.md sections (grep) — the figure cannot contain a number that numbers.md lacks.

## Figure 3 — Both readings of the evolve gates (§5.3 + CS2, data-driven; finalized at resolution)

One row per arm-generation (greedy g1–g5, archive g1–g5): columns `Δscore · Δcost · δ_buggy · verdict_buggy · δ_fixed · verdict_fixed`, with the flipped verdicts visually flagged. This is the paper's most distinctive artifact — the same records scored under the broken instrument and the fixed one, side by side, no retcon.

- Data: `spine/evolve/log.jsonl` (in-flight verdicts) + the post-hoc re-gate (fixed wilson) emitted at resolution; add a `--fig3` mode to collect-numbers.mjs reading both. Rows where the verdict flips get a marker; the count of flips is stated in the caption and must equal the §5.3 text.
- Check: `δ_fixed` recomputed independently = `s/(n+z²)` half-width at n=6 shared, p=1 → +0.0395; regression test `e2e-wilson.mjs` already pins the two historical gates unchanged.

## Inline (tables, not figures)

- §5.2 red-team confusion matrix: 7/7 adversarial caught, 4/4 clean unflagged, 2 incumbent self-flags cleared — a 4-cell table.
- CS1 saturation: one sentence + the campaign-table cost columns; a scatter would overstate n.

## Build order

F3 unblocks at evolve resolution (tonight); F2 once numbers.md is regenerated at resolution; F1 anytime (static). All three land before the Nov 6 author-kit conversion.
