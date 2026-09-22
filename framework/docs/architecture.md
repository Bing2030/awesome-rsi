# Architecture — the system map

How rsif is put together: the trust boundary, the components, the data flow
of one evaluation, and the on-disk layout. Terms are defined in
[concepts.md](concepts.md); the dynamic view (what happens, in what order)
is [lifecycle.md](lifecycle.md).

> **If you are new to agents:** the one idea this page rests on is that an
> "agent" is just *model + prompts + tools + memory + a control loop* —
> all ordinary text and code you can put under version control. rsif
> freezes the loop that does the versioning (trusted engine) and makes
> everything else editable data (artifacts). If that sentence isn't yet
> comfortable, [primer.md](primer.md) builds it from zero and
> [walkthrough.md](walkthrough.md) shows it happening; the diagram below
> will still be here.

## The trust boundary (the one diagram that matters)

rsif targets **harness-level recursive self-improvement**: LLM weights are
frozen; everything the agent *is* is evolvable *data* under a trusted,
frozen outer process. The engine, gates, store semantics, and sandbox can
never be edited by the thing being improved.

```
            ┌─────────────────────────────────────────────────────────┐
            │              TRUSTED, FROZEN (code)                     │
            │                                                         │
            │   EvolutionEngine — run() drives the five phases        │
            │   ├── Improver (reads META templates — data, evolvable) │
            │   ├── selection gates: screen → canary → val            │
            │   ├── Archive (MAP-Elites + superseded lineages)        │
            │   ├── Budget · DriftMonitor · Approvers · Rollback      │
            │   └── EventLog (phase-attributed, append-only)          │
            │                                                         │
            │   ArtifactStore — immutable versions + append-only      │
            │   lineage + active checkout        ┌────────────────┐  │
            │   Sandbox — subprocess python -I   │ MODIFIABLE     │  │
            │   AgentRuntime — interprets specs  │ (artifacts)    │  │
            │                                    │ skill/*        │  │
            │   build_spec(store, mapping) ──────┤ prompt/*       │  │
            │        resolves a mapping to a     │ memory/*       │  │
            │        runnable AgentSpec           │ module/*       │  │
            │                                    │ meta/* (slow)  │  │
            │                                    │ policy/*       │  │
            │                                    └────────────────┘  │
            └─────────────────────────────────────────────────────────┘
                          │                    │
                 LLMProvider (protocol)   Objective (protocol)
                 anthropic / openai /     code-tasks · exact-match ·
                 litellm / scripted /     regex_agent · harness_efficiency
                 demo (offline)
```

Two seams make the framework pluggable in both directions:

- **`Objective`** — the fitness function. The engine never imports a
  concrete objective (a structural guard test asserts this on the engine's
  source). Four real objectives run through it unchanged.
- **`LLMProvider`** — a one-method protocol (`complete(req)`). Adapters for
  Anthropic/OpenAI/LiteLLM, a `ScriptedProvider` for tests, a
  content-addressed `DemoProvider` for the offline CLI demo, and an optional
  disk cache for replay.

## Components and their files

```
framework/src/rsif/
├── config.py            RunConfig — every knob (see below)
├── spec.py              AgentSpec / SkillSpec — the resolved agent
├── cli.py, commands.py  rsif init | run | evolve | status | inspect | rollback | report
│
├── artifacts/           WHAT evolves (versioned data)
│   ├── model.py         ArtifactType, Patch ops, LineageEntry, content hashes
│   ├── store.py         ArtifactStore: versions, lineage, checkout, seeding
│   └── workspace.py     RunWorkspace: the on-disk run layout
│
├── evolve/              HOW it evolves (the trusted loop)
│   ├── engine.py        EvolutionEngine — the five phases, gates, acceptance
│   ├── proposer.py      Improver — assembles the improver prompt, parses output
│   ├── proposal.py      Proposal schema + tolerant JSON parsing
│   ├── operators.py     reads/validates the operator catalog (a META artifact)
│   ├── scheduler.py     fast/slow surfaces per generation
│   ├── selection.py     pass_screen / pass_canary / accept_val
│   ├── archive.py       MAP-Elites grid, parent sampling, backtracking
│   └── assembler.py     build_spec: mapping → AgentSpec (incl. policy cap)
│
├── runtime/             HOW an agent runs
│   ├── runtime.py       AgentRuntime: dispatch loop, budget, traces
│   ├── module_api.py    the module ABI: AgentModule, Actions, ModuleContext
│   ├── loader.py        exec + ABI validation of module source
│   └── types.py         Attempt, TraceStep
│
├── objectives/          WHAT "better" means
│   ├── base.py          Objective protocol, Task/Suite/ScoreBook, splits
│   ├── code_tasks.py    built-in: hidden-test-scored Python tasks
│   └── exact_match.py   built-in: plain-text equality
│
├── memory/              WHAT the agent remembers
│   ├── episodic.py      ReflectionStore (Reflexion)
│   ├── insights.py      InsightStore (ExpeL) — distill / retire
│   ├── playbook.py      bounded section edits (ACE)
│   └── retrieve.py      TF-IDF retriever behind a Protocol
│
├── safety/              WHAT KEEPS IT SAFE
│   ├── budget.py        hard caps, exhausted()/overshot()
│   ├── drift.py         canary/active regression, stagnation
│   ├── rollback.py      auto-rollback to archive best
│   └── approvers.py     FakeApprover / CLIApprover (fail-closed)
│
├── sandbox/             WHERE untrusted code runs
│   ├── guards.py        AST import whitelist (static scan)
│   └── exec.py          subprocess python -I, rlimits, scrubbed env
│
├── llm/                 WHO answers
│   ├── base.py          LLMProvider protocol, Message/Usage/requests
│   ├── anthropic_provider.py · openai_provider.py · litellm_provider.py
│   ├── mock.py          ScriptedProvider (FIFO role queues)
│   ├── demo.py          DemoProvider (content-addressed offline demo)
│   ├── cache.py         disk response cache (replay)
│   └── factory.py       provider_from_config
│
└── observe/             WHAT YOU SEE
    ├── events.py        EventLog, 18 kinds, phases
    └── render.py        terminal rendering (timestamp-free)
```

Plus, outside `src/`:

```
framework/
├── projects/            real objectives built through the public seams only
│   ├── regex_agent/         third objective + live gateway runner
│   └── harness_efficiency/  fourth objective: cost-aware fitness (SoL-Pi)
├── examples/custom_objective.py   ~30-line custom objective
└── tests/               unit / integration / golden / live (126 offline)
```

## Data flow of one evaluation

The same path scores baselines, candidates, `rsif run`, and `rsif report` —
scores are always comparable because there is exactly one evaluation path:

```
mapping {artifact_id → version}            (active checkout, or a candidate)
        │
        ▼
build_spec(store, mapping, extra_memory)   assembler
        │  reads each artifact's checked-out-or-candidate version
        │  PROMPT  → system_prompt
        │  SKILL   → skills[] (code + manifest)
        │  MEMORY  → memory text (playbook rendered)
        │  MODULE  → module_source
        │  POLICY  → memory cap (max_memory_chars)
        │  META    → ignored (improver-side, not agent-side)
        ▼
AgentSpec ── compose_system() → system context (prompt + skills + memory)
        │
        ▼
AgentRuntime.run(task_prompt, spec)        runtime
        │  loads the module (exec behind the whitelist scan)
        │  loop: module.step(ctx) → dispatch action
        │     LLMAction   → provider.complete (through budget + event log)
        │     ToolAction  → skill executed in the sandbox
        │     ReflectAction → self-critique appended to the session
        │     SubmitAction → done
        ▼
Attempt (result, ok, usage, input_chars, steps, trace)
        │
        ▼
objective.evaluate(task, attempt) → TaskScore
        ▼
ScoreBook.mean() → fitness        (memoized per mapping+split+tasks)
```

The injected `extra_memory` (retrieved insights + reflections, TF-IDF-ranked
per task) is appended to the spec's memory *after* playbook rendering and
*before* the policy cap truncates it — so the policy bounds the total
injected memory, not just the playbook.

## The workspace (one run on disk)

```
<run>/
  config.json        RunConfig as JSON (the run is self-describing)
  seed.json          RNG seed — with the LLM cache this replays the run
  events.jsonl       append-only event log (the observability backbone)
  lineage.jsonl      append-only artifact history
  artifacts/<id>/vN/ immutable version dirs (+ meta.json each)
  checkout.json      the ACTIVE agent: artifact_id → version
  archive.json       MAP-Elites cells + history
  evals/gen_NNNN/    per-candidate scorebooks (val_child.json, …)
  cache/llm/         provider response cache (optional, for replay)
  memory/            reflections.jsonl, insights.jsonl
```

`RunWorkspace.init` creates the layout (and refuses a non-empty directory);
`ArtifactStore` is the only writer of artifacts/lineage/checkout.

## Configuration — every knob

`RunConfig` (all fields in `src/rsif/config.py`; defaults shown). The same
object configures engine, runtime, improver, and safety — one source of
truth, serialized to `config.json` per run.

| Field | Default | Meaning |
|---|---|---|
| `objective` | `code-tasks` | Objective name. **Open set**: any non-empty name identifies a user-supplied `Objective`; built-ins dispatch in `objective_from_config`. |
| `charter` | *"Improve task fitness… never regress safety canaries."* | Safety charter text. |
| `provider` | `scripted` | `anthropic` / `openai` / `litellm` / `scripted` (env `RSIF_PROVIDER` overrides). |
| `model` / `improver_model` | `""` | Model ids; empty improver model = same as agent model. |
| `temperature`, `seed` | 0.7, 0 | Threaded to providers and to `random.Random(seed)`. |
| `max_steps_per_task` | 8 | Runtime step budget per attempt. |
| `max_output_tokens` | 4096 | Per-completion cap. |
| `generations` | 3 | Outer loop iterations. |
| `proposals_per_generation` | 2 | Candidates per generation. |
| `screen_tasks` | 2 | Probe-task count for the cascade screen. |
| `screen_epsilon` | 0.30 | Screen passes at `child ≥ parent − ε`. |
| `acceptance_threshold` | 0.02 | Val gain required: `val(child) > val(parent) + θ`. |
| `meta_every_k` | 3 | META surface opens every k-th generation. |
| `meta_eval_window` | 3 | Generations a provisional META edit runs before confirm/revert. |
| `max_patch_ops` | 3 | Bounded edits: ops per patch. |
| `max_playbook_sections` | 12 | Playbook size cap. |
| `budget_usd` / `budget_llm_calls` / `budget_wall_clock_s` | 1.0 / 2000 / 3600 | Hard budget dimensions. |
| `require_approval_for_meta` | True | META edits need an approver (fail-closed). |
| `sandbox_timeout_s` / `sandbox_mem_mb` | 10 / 512 | Sandbox rlimits. |
| `reflections_max` | 50 | Episodic buffer size. |
| `insights_distill_every` | 3 | Generations between insight distillation/retirement passes. |

## Extension points (and what is deliberately *not* one)

| You can plug in | How | Example |
|---|---|---|
| An objective | Implement the `Objective` protocol; pass the instance to `EvolutionEngine` (or name it in `RunConfig` and dispatch yourself) | `projects/regex_agent/objective.py` |
| A provider | Implement `LLMProvider.complete`; wrap with the disk cache if you want replay | `llm/anthropic_provider.py` |
| A retriever | Implement the `Retriever` protocol (embeddings slot in here) | `memory/retrieve.py` |
| An approver | Implement `Approver.approve(proposal_id, summary) → bool` | `safety/approvers.py` |

Not extension points in v1: the engine, the gate chain, the store's
immutability semantics, and the sandbox. The improver *does* improve itself
— but only through META *artifacts* (its template and operator catalog),
under cadence + approval + a deferred evaluation window. The evolution
engine itself is not an editable artifact; that is the trust boundary.

## Design invariants worth internalizing

1. **Activation requires empirical validation** — `apply_patch` cannot
   activate; only `promote` (post-gates) writes the checkout. This is a
   structural property of the store, not a convention.
2. **One evaluation path** — baseline, candidates, CLI `run`, and `report`
   all score through the same memoized `_evaluate`; numbers are comparable.
3. **History is append-only** — rollback appends `restore`; nothing is ever
   rewritten or deleted (deactivation = version 0 in the checkout).
4. **Verification is execution-grounded** — acceptance signals come only
   from executed evaluation (sandbox tests, splits); LLM self-critique is
   advisory context, never a gate.
5. **Determinism by construction** — explicit seeded RNG, scripted/demo
   providers, timestamp-free event payloads, memoized evaluation; the
   golden test reproduces a full run byte-identically across processes.
