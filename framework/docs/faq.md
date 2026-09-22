# FAQ — the questions teams ask on first contact

*Plain-language answers, each linking to the page with the details. Start
with [primer.md](primer.md) if any term here is unfamiliar.*

## Fundamentals

**Is this some kind of self-aware AI that rewrites itself?**
No. The LLM's weights are never touched — rsif is *harness-level*: the
model is a frozen, rented component, and what evolves is the
configuration around it (prompts, tools, memory, control-loop code,
policies), stored as versioned files. A second LLM call (the "Improver")
proposes edits; mechanical test gates decide. See
[primer.md §5](primer.md).

**So does it train or fine-tune a model?**
No. No datasets, no GPUs, no weight updates. "Learning" happens by
editing text and code artifacts — closer to a very disciplined engineer
improving a config file than to training.

**What does an improvement actually look like?**
In the demo run: two one-line additions to the system prompt took held-out
accuracy 0.40 → 0.60 → 1.00, each deployed only after measured gain. Other
surfaces evolve the same way: new sandboxed tools, playbook lessons,
control-loop code, context-size policies. The full story:
[walkthrough.md](walkthrough.md).

**How is this different from AutoGPT-style agent frameworks?**
Those frameworks *run* an agent loop; they don't improve it, and their
loops have no cost bounds or acceptance gates. rsif's subject is the loop
itself: every change to the agent must clear static analysis, smoke tests,
and a held-out performance gate before deploying, under hard budgets, with
append-only history. It's CI discipline applied to agent configuration.

**Why believe LLM-proposed changes help at all?**
Because the proposal mechanism is only the *generator* — selection is
mechanical. That "LLM proposes, evaluator disposes" split is exactly the
shape that works in the research (Promptbreeder, Darwin Gödel Machine,
AlphaEvolve/FunSearch), and the same literature shows generator-only self-
judgment fails — which is why the model's opinion is never an acceptance
signal here. Citations: [design.md](design.md).

## Safety and trust

**What stops the agent from doing something dangerous with its tools?**
Layered, and everything before execution: proposed code passes an import
*whitelist* static scan (pure stdlib only) before it ever runs; tool code
executes in a subprocess with no environment secrets, timeouts, and
CPU/memory caps; the module API structurally hides the engine, store, and
provider from evolved code. Residual limits are documented honestly (e.g.
network egress from the sandbox is not blocked — the env scrubbing removes
the *prize*, not the socket). See [components/runtime.md](components/runtime.md)
and [components/safety.md](components/safety.md).

**Couldn't it cheat the tests — overfit the benchmark or game the grader?**
Three independent floors: (1) acceptance is measured on a **held-out val
split** the proposals never see; (2) trivial **canary tasks** must never
regress; (3) a per-task net-gain floor means noise reshuffles can't fake a
win, and the final `rsif report` adds a bootstrap confidence interval on a
still-sealed test split. Overfitting to val can still happen — it's a
statistical guarantee, not magic — which is why the sealed split exists.

**What if it gets worse over time — gradual drift?**
A drift monitor re-checks the deployed agent every generation; any canary
or active regression triggers automatic rollback to the archive best, and
every change in history is reversible (append-only lineage — nothing is
ever deleted). The promotion gate itself makes regression structurally
hard: a candidate must beat the *currently deployed* agent, not just a
random parent.

**Can it change its own improvement machinery?**
Yes, but that's the most heavily guarded surface ("META"): those edits are
proposed at most every k-th generation, require an explicit human approval
(fail-closed — no approver wired means automatic denial), and run as a
controlled experiment that is auto-reverted unless the improver's own
success rate improves over an evaluation window. The engine, gates, and
store semantics are *not* editable artifacts at all — that's the trust
boundary. See [components/engine.md](components/engine.md).

**Is anything sent anywhere without my knowledge?**
The agent and improver calls go to whichever LLM provider you configure,
and nothing else; the offline test suite actively blocks network sockets.
With the disk cache + seed, live runs replay without any network at all.

## Cost and operations

**What does a run cost?**
Capped by construction: hard budgets on dollars, call count, and wall
clock (defaults $1 / 2000 calls / 1 hour; the demo is $0 — it runs offline
on a scripted provider). Real live runs so far: ~29–35 calls against a
small gateway model, well under a dollar. Budget enforcement aborts
mid-run cleanly with no half-applied proposals.

**Which models does it work with?**
Anything reachable through the provider adapters — Anthropic, OpenAI, or
LiteLLM (which fronts many models) — plus deterministic scripted/demo
providers for tests. The agent and the improver can even use different
models.

**Do I need GPUs / special infrastructure?**
No. Python 3.11+, stdlib-only core; `uv sync` and you're running. The
sandbox is an ordinary subprocess (documented limits apply on macOS).

**How do I know what a run did?**
Everything lands in one append-only event log (`events.jsonl`) — every
proposal, patch, score, gate decision, acceptance, rejection with reason.
`rsif status` / `rsif inspect` render it; runs are byte-reproducible from
the seed. See [components/observability.md](components/observability.md).

## Using it on your own problems

**My team's task isn't "write Python functions" — can it still help?**
That's the core seam: you implement an `Objective` — your tasks, your
grader, your definition of "better" — and the engine, gates, archive, and
safety stack run unchanged. Four real objectives have gone through it
(including a regex-builder and a token-cost-aware one). A minimal
objective is ~30 lines. See [components/objectives.md](components/objectives.md).

**What do I need to provide?**
A task pack split into train/val/test (+ a few trivial canaries), a
programmatic grader (an `evaluate` function returning 0..1), and an API
key if you want live models. Recipe, including the "write a solvability
test for your own grader" step that caught two real task-design bugs:
[components/objectives.md](components/objectives.md).

**Where do the seed artifacts come from — do I write the initial agent?**
`rsif init` scaffolds a sensible default (prompt, minimal control loop,
improver template, operator catalog). You can edit the seeds before the
first run; the loop improves from wherever you start.

**What's the difference between "accepted" and "promoted"?**
Accepted = beat its sampled parent → kept in the archive as a stepping
stone. Promoted = also beat the *currently deployed* agent → actually
became the live agent. The demo's third proposal was accepted and not
promoted — that distinction is the anti-ratchet. See
[walkthrough.md §6](walkthrough.md).

## Engineering details

**Why is the core stdlib-only?**
Determinism and auditability: fewer moving parts, no hidden dependency
behavior, runs anywhere. Adapters (Anthropic/OpenAI/LiteLLM) are optional
extras; embeddings-based retrieval is explicitly left as a pluggable seam,
not a dependency.

**Can I use it on Windows / in Docker?**
The code is portable Python; the sandbox uses process-level isolation
(timeouts, rlimits where available, scrubbed environment) — on macOS there
is no seccomp-style network blocking, which is documented as a residual
limitation rather than pretended away. No Docker requirement.

**How is correctness of the framework itself tested?**
126 offline deterministic tests, including a golden test that reproduces a
full evolution run byte-identically across processes, plus structural
guard tests (e.g. the engine source provably imports no concrete
objective). Test map: [investigation.md](investigation.md).

**Where are the known limitations listed?**
Honestly, in several places: the limitations table in
[investigation.md](investigation.md) (with codes M2–M4, L2, L3), the
per-component "known limitations" sections, and the decision log's
corrections. Nothing in this framework is claimed to be more than it is.
