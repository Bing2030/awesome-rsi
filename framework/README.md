# rsif — Recursive Self-Improvement Framework

`rsif` is a Python framework for building agents that improve themselves through a
verified evolution loop:

```
idea proposal → idea exploration → idea design → verification & validation → correction
```

Every change to the agent (prompt, skill, memory rule, architecture code, or the
improver's own templates) is a **versioned artifact** that is only activated after it
**empirically improves fitness on a held-out validation split** — never on the model's
own judgment of itself.

Every design mechanism is grounded in the RSI literature; `docs/design.md` carries the
full citation map into the [awesome-rsi](../README.md) library and local PDFs in
`../resources/`.

## Quick start

```bash
cd framework
uv sync                      # stdlib-only core; dev group brings pytest
uv run pytest                # offline, deterministic suite
uv run rsif init ../runs/demo --objective code-tasks
uv run rsif evolve --run ../runs/demo --generations 3     # scripted provider demo
```

For a real model: `uv run --extra anthropic rsif init ../runs/live --provider anthropic
--model claude-sonnet-5` with `ANTHROPIC_API_KEY` set. Full walkthrough
(status / inspect / run / report / rollback, live-mode notes):
`docs/quickstart.md`.

## The loop (one generation)

1. **Proposal** — an Improver meta-agent proposes one bounded patch, grounded in the
   archive frontier, recent reflections, and distilled insights.
2. **Exploration** — cheap probe-task screening before full evaluation.
3. **Design** — the patch materializes as concrete artifact edits (bounded: ≤ k ops).
4. **Verification** — gate chain: static code scan → canary suite → train-split eval →
   held-out **val-split acceptance** (`val(child) > val(parent) + threshold`, with a
   paired net-task-gain floor). META-only edits (the improver improving itself) are
   accepted provisionally and confirmed or reverted by a deferred evaluation window.
5. **Correction** — rejected proposals produce Reflexion-style reflections; regressions
   trigger rollback to an archived ancestor; the MAP-Elites archive keeps search
   open-ended instead of collapsing to one lineage.

## Layout

- `src/rsif/artifacts/` — versioned artifacts, lineage, rollback
- `src/rsif/llm/` — provider-agnostic LLM protocol + adapters (anthropic / openai / litellm)
- `src/rsif/runtime/` — agent runtime + evolvable module ABI
- `src/rsif/objectives/` — pluggable fitness (code-tasks benchmark, exact-match example)
- `src/rsif/memory/` — reflections (Reflexion), insights (ExpeL), playbook (ACE)
- `src/rsif/evolve/` — the engine, improver, archive (MAP-Elites), scheduler, skill assembler
- `src/rsif/safety/` — budgets, drift monitors, approvals, rollback (gate chain in `evolve/selection.py` + `sandbox/guards.py`)
- `src/rsif/observe/` — event log + terminal rendering

Skills are first-class `SKILL` **artifacts** (code + manifest) — assembled by
`evolve/assembler.py`, exposed as tools by the runtime, and executed through the
sandbox — not a standalone `skills/` package.

## Documentation

Start at [`docs/index.md`](docs/index.md) — reading paths plus one guide per
subsystem:

| Doc | What it covers |
|---|---|
| [`docs/quickstart.md`](docs/quickstart.md) | 10-minute offline walkthrough |
| [`docs/architecture.md`](docs/architecture.md) | trust boundary, component map, data flow, config knobs |
| [`docs/concepts.md`](docs/concepts.md) | the glossary (artifact, checkout, niche, gates, …) |
| [`docs/lifecycle.md`](docs/lifecycle.md) | one proposal through every gate, event, rejection reason |
| [`docs/components/`](docs/components/) | deep dives: artifacts · engine · runtime · memory · objectives · efficiency · safety · observability |
| [`docs/design.md`](docs/design.md) | mechanisms ↔ papers ↔ code ↔ tests (citation map) |
| [`docs/investigation.md`](docs/investigation.md) | file-by-file implementation walkthrough |
| [`docs/plan.md`](docs/plan.md), [`docs/decision-log.md`](docs/decision-log.md) | milestone status; decisions & corrections |
| [`docs/changes.md`](docs/changes.md) | change register: status + lesson sources (paper / code / internal) per change |

See `docs/plan.md` for milestone status and `docs/design.md` for the referenced design.
