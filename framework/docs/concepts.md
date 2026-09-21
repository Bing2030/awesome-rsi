# Concepts — the rsif glossary

Every term the framework uses, grouped by where it lives. File anchors point
into `framework/`; see [architecture.md](architecture.md) for how the pieces
fit together and [lifecycle.md](lifecycle.md) for the dynamic view.

## The agent and what it is made of

| Term | Meaning | Where |
|---|---|---|
| **Agent** | The thing being improved. Fully described by an `AgentSpec`: system prompt + skills + memory text + architecture module. | `src/rsif/spec.py` |
| **AgentSpec** | The resolved, runnable form of one agent *version-mapping*: `system_prompt`, `skills`, `memory`, `module_source`. Assembled from a checkout by `build_spec`. | `src/rsif/spec.py`, `src/rsif/evolve/assembler.py` |
| **Artifact** | Anything improvable, stored as versioned files. Six types: `skill`, `prompt`, `memory`, `module`, `meta`, `policy`. IDs are namespaced (`prompt/system`, `skill/strings`). | `src/rsif/artifacts/model.py` |
| **Surface** | Which artifact type a proposal edits ("the prompt surface", "the META surface"). Surfaces gate *when* and *whether* a proposal is even considered. | `src/rsif/evolve/scheduler.py` |
| **Skill** | An executable tool: `module.py` (a `main(**args)` function) + `manifest.json` (name/description). Runs in the sandbox; advertised to the model as a tool. | assembler `_skill()`, `runtime._run_skill` |
| **Module (architecture)** | The agent's control loop as code: a class implementing `AgentModule.step(ctx) → Action`. Loaded/exec'd in-process behind the static scan. | `src/rsif/runtime/module_api.py` |
| **META artifact** | An artifact that changes the *improver* instead of the agent: the improver prompt template and the operator catalog. Evolves on a slow cadence under approval. | `meta/improver-template`, `meta/operator-catalog` |
| **POLICY artifact** | A runtime tuning knob as an artifact — currently `policy/context`, bounding how much memory may be injected into the context (`max_memory_chars`). | `src/rsif/constants.py`, assembler `_policy_cap` |
| **Operator** | A typed mutation in the improver's vocabulary, e.g. `prompt/refine`, `skill/add`, `policy/bound-context`. A proposal's operator must exist in the catalog *and* match its claimed surface. | `src/rsif/evolve/operators.py` |

## Versioning and state

| Term | Meaning | Where |
|---|---|---|
| **Version** | One immutable snapshot of an artifact's files: `artifacts/<id>/vN/` plus a `meta.json` (type, content hash, proposal id, accepted flag). Writing an existing version raises. | `src/rsif/artifacts/store.py` |
| **Lineage** | Append-only JSONL of every write: `create / update / delete / restore` with from/to versions and the responsible proposal. Rollback *appends*; history is never rewritten. | `lineage.jsonl`, `store._append_lineage` |
| **Checkout** | The active agent: `checkout.json`, a mapping `artifact_id → version`. Reading an active artifact = reading its checked-out version. | `store.checkout()`, `store.promote()` |
| **Patch** | A bounded set of operations (`CreateOp / UpdateOp / DeleteOp / RestoreOp`) plus a rationale and a falsifiable hypothesis. Max `max_patch_ops` (default 3) ops. | `src/rsif/artifacts/model.py` |
| **Candidate** | A patch materialized as new versions + a *proposed* mapping (parent snapshot overlaid with the patch's versions). Never active until promoted. | `store.apply_patch`, `engine._one_proposal` |
| **Snapshot (spec)** | A frozen `artifact_id → version` mapping; the archive stores one per individual so any archived agent can be reassembled. | `Archive.Individual.spec_snapshot` |
| **Workspace** | One run's on-disk layout: config, seed, events, lineage, artifacts, checkout, evals, cache, memory. | `src/rsif/artifacts/workspace.py` |
| **Seed artifacts** | The six created by `rsif init`: `prompt/system`, `memory/playbook`, `meta/improver-template`, `meta/operator-catalog`, `module/default`, `policy/context`. | `store.seed_defaults` |

## The loop and its actors

| Term | Meaning | Where |
|---|---|---|
| **Engine** | The trusted, frozen process running the loop. `EvolutionEngine.run()` drives generations × proposals through five phases. | `src/rsif/evolve/engine.py` |
| **Generation** | One outer iteration: `proposals_per_generation` candidate proposals, then insight distillation, META-window settlement, and a drift check. | `engine.run` |
| **Improver** | The meta-agent that proposes one bounded change per call. Its prompt is assembled from the *evolvable* META template, checkout summary, archive frontier, and lessons. | `src/rsif/evolve/proposer.py` |
| **Proposal** | Parsed improver output: surface, operator, hypothesis, rationale, ops. Invalid JSON/schema → a `parse` rejection. | `src/rsif/evolve/proposal.py` |
| **Runtime** | `AgentRuntime.run(task_prompt, spec)` — interprets the spec: loads the module, dispatches its actions (LLM/tool/reflect/submit), enforces step budget, records the `Attempt`. | `src/rsif/runtime/runtime.py` |
| **Attempt** | One agent run on one task: `result`, `ok`, token `usage`, `input_chars` (context size), `steps`, `wall_s`, `trace`, `error`. | `src/rsif/runtime/types.py` |
| **Objective** | The fitness function: supplies task suites, scores attempts, computes fitness and behavior descriptors. The single seam that makes the engine task-agnostic. | `src/rsif/objectives/base.py` |

## Evaluation and gates

| Term | Meaning | Where |
|---|---|---|
| **Split** | A slice of the objective's tasks: `train` (selection), `val` (acceptance), `test` (sealed until `rsif report`), `canary` (never regress). | `objectives/base.Split` |
| **Screen (cascade)** | Cheap first gate: candidate runs `screen_tasks` (default 2) sampled train tasks; must be within `screen_epsilon` (0.30) of the parent. Saves the expensive gates for plausible candidates. | `selection.pass_screen` |
| **Canary** | Trivial tasks the deployed agent must never regress on. `child ≥ parent` — any drop is a hard reject, and a drop on the *active* agent triggers auto-rollback. | `selection.pass_canary`, `safety/drift.py` |
| **Val acceptance** | The strict gate: `val(child) > val(parent) + θ` (θ = `acceptance_threshold`, 0.02) **and** a paired net-gain floor — across the val tasks, the child must beat the parent on ≥ 1 more task than it loses. | `selection.accept_val` |
| **Two-level acceptance** | Archive-acceptance (beats its *sampled parent* → stepping stone in the archive) vs **promotion** (also beats the *active* agent → becomes the deployed agent). Prevents ratcheting down via weak sampled parents. | `engine._one_proposal` phase 5 |
| **Gate chain** | The exact ordered checks a proposal passes: surface → approval (META) → bounded → operator → apply → scan → load (module) → screen → canary → val. | [lifecycle.md](lifecycle.md) |
| **Memoization (eval)** | Suites are evaluated once per `(spec mapping, split, task ids)` per run; parents' books are reused across proposals. | `engine._evaluate` |

## The archive and search

| Term | Meaning | Where |
|---|---|---|
| **Archive** | MAP-Elites grid: one elite per niche cell + full history. Persisted to `archive.json`. | `src/rsif/evolve/archive.py` |
| **Individual** | One archived agent: descriptor, fitness, val score, spec snapshot, generation, proposal id, parent ref, cost. | `archive.Individual` |
| **Behavior descriptor** | The niche key, supplied by the objective (e.g. `(surface, pass_band)`). Defines the axes of diversity. | `Objective.behavior_descriptors` |
| **Niche / cell** | One descriptor value; the best individual found there is kept (elitist replacement, ties broken by lower cost). | `Archive.add` |
| **Frontier** | The archive's current elites sorted by fitness. Parents are sampled from here. | `Archive.frontier` |
| **Superseded lineage** | Individuals once elite in their niche, later displaced by a fitter sibling. Kept in history; re-enter parent sampling with probability ε (backtracking pressure). | `Archive.superseded_individuals` |
| **Parent sampling** | Harmonic rank-biased over the frontier (weight `1/(rank+1)`, every elite selectable), ε = 0.2 to superseded lineages. | `Archive.sample_parent` |

## Memory

| Term | Meaning | Where |
|---|---|---|
| **Reflection** | Episodic entry created on every rejection ("proposal g1p2 rejected at val: …"). Retrieved per-task by TF-IDF. | `src/rsif/memory/episodic.py` |
| **Insight** | Distilled lesson from *verified successes only*, with provenance and usage-based retirement (`retire_correlated`). | `src/rsif/memory/insights.py` |
| **Playbook** | The structured, evolving context (sections with id/title/body) stored as the `memory/playbook` artifact; only bounded section edits allowed. | `src/rsif/memory/playbook.py` |
| **Injected memory** | What the agent actually sees: assembled playbook + retrieved insights + reflections, capped by the POLICY artifact's `max_memory_chars`. | assembler + `engine._agent_memory` |

## Safety

| Term | Meaning | Where |
|---|---|---|
| **Budget** | Hard caps on three dimensions: LLM calls, USD, wall clock. Checked before each proposal (`exhausted`) and after every call (`overshot` — overshoot bounded to one call). | `src/rsif/safety/budget.py` |
| **Drift monitor** | Generation-end check of the active agent: canary regression / active regression (→ auto-rollback) and stagnation (→ approval or stop). | `src/rsif/safety/drift.py` |
| **Auto-rollback** | Restore the checkout to the archive-best snapshot; append-only `restore` lineage; extras deactivated (v0), never deleted. | `src/rsif/safety/rollback.py` |
| **Approver** | Human-in-the-loop for high-stakes edits (META) and drift continuation. Fail-closed: no approver wired → deny. | `src/rsif/safety/approvers.py` |
| **Static scan** | AST **import whitelist** for evolved code (curated pure stdlib + `rsif.runtime.module_api` only) — before any execution, even screening. | `src/rsif/sandbox/guards.py` |
| **Sandbox** | Subprocess `python -I` with temp cwd, timeouts, rlimits, PATH-only env. Runs skill code and unit tests (hidden-test scoring). | `src/rsif/sandbox/exec.py` |

## Observability

| Term | Meaning | Where |
|---|---|---|
| **Event log** | Append-only `events.jsonl`; 18 kinds, every entry phase-attributed. The backbone for `status`/`inspect`, reflection, and replay. | `src/rsif/observe/events.py` |
| **Phase** | One of `proposal / design / exploration / verification / correction` — the framework's loop vocabulary, stamped on every relevant event. | `events.py` constants |
| **Golden test** | Full-loop byte-identical reproduction across processes against a committed `golden_events.jsonl`. | `tests/golden/` |
| **Stop reason** | How a run ended: `budget:<dim>`, `drift`, `error:<Origin>` (provider), `engine:<Type>` (bug), or `None` (completed). | `engine.run` |
