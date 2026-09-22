# Primer — LLM agents from zero

*Everything you need before the rest of the docs, assuming no background in
agent or AI development. If words like "prompt" or "token" are new, read
this page first; it defines every term the other pages use.*

The pages after this one describe rsif precisely but tersely, the way
engineers document a database or a compiler. This page is slower: it builds
the vocabulary and the mental model from nothing, using comparisons to
ordinary software engineering. Nothing here is rsif-specific — it is the
shared background the other pages assume.

## 1. What is an LLM?

An LLM (large language model) is a function: **text in → text out**.

```
"You are a careful Python-solving agent. … Implement sum_list(xs)."
        │
        ▼
   ┌─────────┐
   │   LLM   │   a neural network with billions of trained parameters
   └─────────┘
        │
        ▼
"```python\ndef sum_list(xs): return sum(xs)\n```"
```

Three properties matter for everything that follows:

1. **It is stateless.** The model remembers nothing between calls. Every
   conversation you have ever had with a chatbot works only because the
   *software around the model* resends the whole conversation with every
   new message. "Memory" in an agent is always something the surrounding
   software assembles and re-injects.
2. **It is trained, not programmed.** Nobody wrote rules for grammar or
   Python; the behavior emerged from training on enormous amounts of text.
   Consequence: behavior is statistical. The same input usually gives
   similar output, but "usually" is doing work — and you cannot debug it
   by reading code.
3. **It is rented, not run by you.** You call it over an HTTP API. The
   company operating the model is the **provider** (Anthropic, OpenAI,
   …); the specific model is identified by a **model id**
   (`claude-sonnet-5`, …). You never download the weights.

## 2. The vocabulary

| Term | Meaning | The engineering analogy |
|---|---|---|
| **Prompt** | The full input text sent to the model. | A function's arguments — the *only* way to influence the output. |
| **System prompt** | The standing part of the prompt: role, rules, style. Set once, prepended to every call. | A base config applied to every request. |
| **Completion** | The text the model returns. | The function's return value. |
| **Token** | The unit models read and write — roughly ¾ of an English word. Providers bill and cap by tokens. | Bytes on the wire: the unit of both cost and limits. |
| **Context window** | The maximum prompt + completion size a model accepts. | A fixed-size request buffer. |
| **Temperature** | A 0–1 randomness dial (0 ≈ same answer every time, 1 ≈ varied). | A seedable RNG for the output. |
| **Provider** | The service that runs the model behind an HTTP API. | A cloud vendor. |
| **LLM call** | One request/response round trip. | One RPC. Latency hundreds of ms to minutes; this is why agents are slow. |

Two cost consequences worth internalizing, because the framework treats
them as first-class concerns:

- **Money**: every token processed costs money (fractions of a cent, but
  an agent loop makes hundreds of calls — unbounded loops are a real
  billing incident).
- **Context bloat**: everything you "give the agent" — instructions,
  memories, tool descriptions — is tokens resent on every call. More
  context = more cost, and past some point, *worse* accuracy. An agent's
  context is a budget, not a shopping cart.

## 3. From chatbot to agent

A chatbot answers once. An **agent** is a loop around the model that lets
it *act*:

```
            ┌──────────────────────────────────────────┐
            │                agent loop                │
  task ──►  │  build prompt (system + task + history)  │
            │        │                                 │
            │        ▼                                 │
            │     LLM call                            │
            │        │                                 │
            │   answer says:                           │
            │   • final answer ──────────────► done    │
            │   • "run tool X with args Y"             │
            │        │                                 │
            │        ▼                                 │
            │   execute X in some sandbox              │
            │        │                                 │
            │        ▼                                 │
            │   append result to history, repeat       │
            └──────────────────────────────────────────┘
```

- A **tool** (rsif calls it a **skill**) is a function the model may ask
  the harness to run: a calculator, a web search, a Python sandbox. The
  model never executes anything itself — it *emits a request* ("call
  `run_tests(code=…)`) and trusted code decides whether and how to run it.
- The **harness** is the trusted code around the model: it assembles
  prompts, runs tools, enforces limits, records what happened. rsif is a
  harness. The model is a component *inside* it, not the program itself.

So "an agent" = **model + tools + control loop + context**, and crucially,
the last three are *ordinary code and text that you choose*. That leads to
the uncomfortable question the framework exists to answer.

## 4. Why agents are hard to improve today

Everything that makes an agent good — the system prompt, the tool set, the
memories, the control-flow policy — is hand-written configuration. Teams
tune it by intuition:

- someone rewords a prompt and the agent gets better on the tasks they
  tried and silently worse on tasks they didn't;
- there is no regression suite, so a "fix" shipped last week is undone by
  a "tweak" this week;
- nobody can say *which* instruction in a 2,000-word prompt is load-bearing.

Compare with ordinary software: we long ago stopped "improving" programs
by hand-editing machine code and hoping. We have version control, tests,
and CI. Agent configuration has none of that discipline by default — and
the thing being tuned (a prompt) doesn't even behave deterministically.

**This is the gap rsif fills**: treat the agent's own configuration as
*data under version control*, and let a search process propose changes
that a **test-gated pipeline** must accept before anything deploys.

## 5. What "self-improvement" means here (and what it does not)

rsif does **not** train or modify the model's weights. The LLM is frozen,
rented, identical in every run. What evolves is the *configuration around
it* — and in rsif all of it is stored as versioned files called
**artifacts**:

| Artifact | What it is | The everyday equivalent |
|---|---|---|
| `prompt/*` | The system prompt. | A config file for behavior. |
| `skill/*` | Executable tools (Python modules). | Microservices the agent can call. |
| `memory/*` | A structured "playbook" of lessons. | A wiki the agent rereads every task. |
| `module/*` | The agent's control loop *as code* (ask model → maybe use tool → repeat → submit). | The `while` loop of the agent, written as a plugin. |
| `policy/*` | Numeric knobs (how much memory may be injected). | Resource limits. |
| `meta/*` | The improver's own template and mutation vocabulary. | The CI pipeline's own configuration. |

The loop that improves them is plain Darwin, applied to configuration:

1. An LLM called the **Improver** proposes one small, bounded change (a
   "prompt edit", a "new skill", …), with a stated hypothesis.
2. The change is applied to a **copy** — never the live agent.
3. The copy is **executed on real test tasks** and scored.
4. Only measured improvement on held-out tasks lets the change deploy;
   every rejection is remembered as a lesson for future proposals.

Why believe an LLM can propose such changes at all? Because the research
says yes when — and only when — a *mechanical* selector does the
accepting: prompt-evolution work (Promptbreeder), self-rewriting agents
(Darwin Gödel Machine), and code-search systems (AlphaEvolve, FunSearch)
all show real gains exactly in this "LLM proposes, evaluator disposes"
shape. The same literature shows the failure mode when the model judges
its own work: confident nonsense. Hence the rule below.

## 6. The one rule everything else follows

> **No change deploys on the model's say-so. Only measured, held-out
> performance deploys.** An LLM's opinion of a candidate is never an
> input to acceptance.

Everything in the safety docs is that rule made structural. A short tour
of what could go wrong and the corresponding mechanism, in the vocabulary
you'll meet later:

| Fear (reasonable!) | rsif's answer | Where to read |
|---|---|---|
| "The agent rewrites itself into something broken or dangerous." | Candidates never touch the live agent until promotion; even then, history is append-only and any regression auto-rolls back. | [architecture.md](architecture.md), [components/safety.md](components/safety.md) |
| "Evolved code does something malicious (read secrets, escape)." | Code changes pass a static import whitelist *before execution*, then run in a locked-down subprocess with no env secrets, CPU/time/memory caps. | [components/runtime.md](components/runtime.md) |
| "It finds a cheap way to cheat the tests." | Acceptance requires gains on a *held-out* split the proposals never see, plus a floor on trivial "canary" tasks, plus a per-task net-gain floor so noise can't fake a win. | [lifecycle.md](lifecycle.md) |
| "A run costs $500." | Hard budgets on calls, dollars, and wall-clock, enforced mid-run. | [components/safety.md](components/safety.md) |
| "It optimizes into a corner (only good at the drills)." | A quality-diversity **archive** keeps many behaviorally-different agents as stepping stones, not just the current best. | [components/engine.md](components/engine.md) |
| "Nobody can tell me why it changed." | Every proposal, score, gate and decision lands in an append-only, replayable event log. | [components/observability.md](components/observability.md) |

## 7. The analogy table (rsif ↔ what you already know)

| rsif concept | Familiar equivalent |
|---|---|
| Artifact store (versions, lineage, checkout) | Git: immutable commits, reflog, `HEAD` |
| Improver | A contributor opening a pull request |
| Patch (bounded ops) | A PR that may touch at most 3 files |
| Static scan gate | Lint/`deny` rules in CI, before any build |
| Cascade screen | A fast smoke test before the slow suite |
| Canary suite | The smoke tests that must *never* regress |
| Val acceptance | The merge gate: full suite on held-out tests |
| Promotion into checkout | Merging the PR — the only way code ships |
| Archive (MAP-Elites) | Keeping promising branches alive, not just `main` |
| Rejection → reflection | A failed PR with comments the next PR reads |
| Budget | spend limit + job timeout in CI |
| Auto-rollback | `git revert` + redeploy, done automatically |
| Golden test / replay | A byte-identical reproducible build |

## 8. What rsif is not

Worth stating plainly, because "self-improving agent" invites sci-fi
readings:

- **Not model training.** Weights are untouched; no GPUs, no datasets.
- **Not autonomous deployment.** Nothing leaves the run directory; a run
  is a batch job that starts, is bounded, and ends.
- **Not a chat product.** It is a Python library + CLI for running an
  *experiment loop* on agent configuration.
- **Not unbounded.** Every run is capped by budget and every accepted
  change is reversible through append-only history.
- **Not claiming the model understands itself.** The framework's entire
  design assumes the opposite: proposals are guesses; only execution
  decides.

## 9. Where to go next

- [walkthrough.md](walkthrough.md) — a complete real run narrated event by
  event (the fastest way to make this concrete).
- [quickstart.md](quickstart.md) — run that demo yourself in one minute,
  offline, no API key.
- [architecture.md](architecture.md) — the system map, now that the words
  are in place.
- [faq.md](faq.md) — the questions teams reliably ask on first contact.
