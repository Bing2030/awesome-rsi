# rsif documentation

**rsif** is a Python framework for building agents that improve themselves
through a verified evolution loop:

```
proposal → exploration → design → verification → correction
```

Everything the agent *is* — prompts, skills, memory, architecture code, the
improver's own templates, even the context-assembly policy — is a
**versioned artifact**. An artifact is only activated after it
**empirically improves fitness on a held-out validation split**, never on
the model's judgment of itself. The engine that enforces this is trusted,
frozen code; the agent is modifiable data.

- **Status:** 16 milestones (M0–M16), 126 offline deterministic tests +
  live gateway runs; see [plan.md](plan.md).
- **Core:** Python 3.11+, stdlib-only (providers are optional extras).
- **Where the mechanisms come from:** every design decision is grounded in
  the RSI literature — [design.md](design.md) carries the full citation map.
- **New to agents/LLMs entirely?** [primer.md](primer.md) defines every
  term from zero; [walkthrough.md](walkthrough.md) then narrates one
  complete run.

## Reading paths

| You want to… | Read |
|---|---|
| **Learn the background first** — no agent/LLM knowledge assumed | [primer.md](primer.md) |
| **See one complete run narrated** — every artifact, gate, and event explained | [walkthrough.md](walkthrough.md) |
| **Run it in the next 10 minutes** (offline demo, no API key) | [quickstart.md](quickstart.md) |
| **Preempt the questions your team will ask** | [faq.md](faq.md) |
| **Understand the big picture** — components, trust boundary, data flow | [architecture.md](architecture.md) |
| **Decode the vocabulary** — artifact, checkout, niche, canary, gate… | [concepts.md](concepts.md) (the glossary) |
| **Trace one proposal** through every gate, event, and rejection reason | [lifecycle.md](lifecycle.md) |
| **Read/modify a specific subsystem** | the component guides below |
| **Write your own objective** and run the engine on your task | [components/objectives.md](components/objectives.md) |
| **Understand why it is built this way** (papers ↔ mechanisms) | [design.md](design.md), [decision-log.md](decision-log.md) |
| **Audit the implementation** file by file | [investigation.md](investigation.md) |

**Presenting to teams new to agents?** The on-ramp that works: primer →
walkthrough (one session, ~20 minutes of reading), then whichever
subsystem page owns their question. The FAQ is organized to be skimmed
live during Q&A.

## The component guides

Each guide covers one subsystem: what it does, the files and key classes,
the exact semantics and invariants, the configuration knobs, the events it
emits, and the tests that pin it down.

| Guide | Subsystem | Key code |
|---|---|---|
| [components/artifacts.md](components/artifacts.md) | The artifact store: versioning, lineage, checkout, patches, operators | `src/rsif/artifacts/` |
| [components/engine.md](components/engine.md) | The evolution engine: phases, gates, archive, scheduler, improver, META recursion | `src/rsif/evolve/` |
| [components/runtime.md](components/runtime.md) | Agent runtime: spec assembly, the module ABI, skills, the sandbox | `src/rsif/runtime/`, `src/rsif/sandbox/`, `src/rsif/spec.py` |
| [components/memory.md](components/memory.md) | Memory: reflections, insights, playbook, retrieval, injection | `src/rsif/memory/` |
| [components/objectives.md](components/objectives.md) | The task-agnostic seam: the `Objective` protocol + four real objectives | `src/rsif/objectives/`, `projects/` |
| [components/efficiency.md](components/efficiency.md) | Cost-aware evolution: the efficiency objective and the POLICY artifact | `projects/harness_efficiency/` |
| [components/safety.md](components/safety.md) | Safety stack: budgets, drift, rollback, approvals, code scanning | `src/rsif/safety/`, `src/rsif/sandbox/guards.py` |
| [components/observability.md](components/observability.md) | Events, CLI, rendering, determinism & replay | `src/rsif/observe/`, `src/rsif/cli.py` |

## Project records

These are historical/engineering records rather than reference docs:

- [plan.md](plan.md) — the milestone status table (M0–M16) and the original
  approved plan.
- [decision-log.md](decision-log.md) — per-milestone decisions, bugs caught,
  and corrections to earlier claims.
- [investigation.md](investigation.md) — the code-level implementation
  walkthrough (mechanism ↔ design point ↔ evidence).

## The one-paragraph mental model

In one sentence, for newcomers: **rsif is a CI pipeline for agent
configuration** — an LLM proposes changes the way a contributor opens pull
requests, and nothing merges without passing held-out tests. With that
framing, the precise version:

An **Improver** meta-agent proposes one **bounded patch** to the agent's
artifacts (a prompt tweak, a new skill, a playbook rule, an architecture
edit, or a mutation of its own template). The engine materializes the patch
as *candidate* versions — the active agent is untouched — then scores the
candidate on the objective's task suites behind a cascade of gates: a static
code scan, a cheap train-split screen, a never-regress canary suite, and
finally strict held-out **val acceptance** (`val(child) > val(parent) + θ`
plus a paired net-gain floor). Accepted candidates enter a MAP-Elites
**archive** (one elite per behavior niche); only candidates that also beat
the *active* agent are **promoted** into the checkout. Rejections become
Reflexion-style reflections that shape future proposals. Hard budgets,
drift monitors, and append-only lineage bound the whole process. Everything
is recorded in a phase-attributed event log that is byte-reproducible from
the seed.

Once that paragraph feels obvious, you know rsif.
