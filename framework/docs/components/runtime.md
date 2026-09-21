# Component guide — the runtime, module ABI, and sandbox

*How one agent runs one task: the spec is interpreted, the architecture is
code behind a fixed envelope, and untrusted execution happens in a
subprocess.*

Files: `src/rsif/spec.py`, `src/rsif/evolve/assembler.py`,
`src/rsif/runtime/{runtime,module_api,loader,types}.py`,
`src/rsif/sandbox/{exec,guards}.py`. Verified by
`tests/integration/test_runtime.py`, `tests/unit/test_sandbox.py`,
`tests/integration/test_meta_and_module.py`.

## Spec assembly (`build_spec`)

`build_spec(store, mapping, extra_memory="")` resolves an explicit
`artifact_id → version` mapping into an `AgentSpec` — *not* necessarily the
active checkout: the engine overlays candidate versions onto a parent
snapshot, which is what keeps apply/evaluate/accept decoupled.

Per artifact type:

- **PROMPT** → `system_prompt` (first of `system.md`/`prompt.md`/…).
- **SKILL** → `skills[]`: code from `module.py`/`code.py`, name/description
  from `manifest.json` (falling back to the id tail).
- **MEMORY** → rendered text: `playbook.json` parsed and rendered as
  sections; free-text payloads joined.
- **MODULE** → `module_source` + `module_path` (the version dir).
- **POLICY** → the memory cap (`max_memory_chars`, see
  [efficiency.md](efficiency.md)).
- **META** → skipped: improver-side machinery, not agent-side.

`extra_memory` (retrieved insights/reflections) is appended, and the policy
cap truncates the **total** — cap ≤ 0 means "inject everything".

`AgentSpec.compose_system()` builds the actual system context:
prompt + "## Available skills" (name: description lines) +
"## Memory / lessons". `compose_system()` is also what the runtime measures
for `Attempt.input_chars` (plus the task prompt) — the input-cost signal a
cost-aware objective reads.

## The runtime loop (`AgentRuntime.run`)

```
for step in range(max_steps):
    action = module.step(ctx)
    LLMAction     → provider.complete(session + optional overrides)
                    result recorded: usage, event, budget; assistant msg
    ToolAction    → skill executed in the sandbox; observation returned as
                    a tool message + user message (execution feedback)
    ReflectAction → "[self-critique] …" appended to the session (advisory)
    SubmitAction  → Attempt(result, ok=True, …); done
no submit within max_steps → Attempt(ok=False, error="max_steps exhausted")
any other exception        → Attempt(ok=False, error=str(e))
ProviderError / BudgetExhausted → re-raised (never scored 0; run aborts cleanly)
```

The `Attempt` (`runtime/types.py`) is the objective's evidence: `result`,
`ok`, `usage` (in/out tokens), `input_chars` (injected context size),
`steps`, `wall_s`, `trace` (one `TraceStep` per dispatch), `error`.

The runtime is deliberately boring — it interprets the spec. All
interesting agent behavior lives in the module (evolvable) or the model.

## The module ABI (`runtime/module_api.py`)

An agent's architecture is a class:

```python
class Module(AgentModule):
    name = "my-arch"
    def step(self, ctx: ModuleContext) -> Action: ...
```

- **Actions**: `LLMAction(system="", user="")`, `ToolAction(name,
  arguments_json)`, `ReflectAction(text)`, `SubmitAction(result="")`.
- **`ModuleContext`** — everything a module may see: `task_prompt`,
  `session` (messages + usage), `tools`, `steps_used`/`max_steps`,
  `last_completion`. **No store, no engine, no sandbox config** — the
  envelope keeps the trust boundary intact while still allowing ADAS-style
  architecture search and Gödel-style self-rewrites *of the artifact*.
- The seed module (`module/default`) is the minimal loop: one `LLMAction`,
  then submit. Evolved modules add retry policies, self-critique passes,
  tool chaining — e.g. the M7 test module reflects then retries, visibly
  changing the requests.

`loader.load_module_source` execs the source and validates the ABI (class
found, `step` callable); failures are `ModuleLoadError`. The engine's
design-phase **load gate** runs this before any evaluation, so a broken
module never reaches even the screen.

## The static scan (`sandbox/guards.py`)

An AST **import whitelist** applied to skill/module payloads before any
execution:

- Allowed: a curated set of pure stdlib (`math`, `re`, `json`, `itertools`,
  `statistics`, …) and exactly one framework module —
  `rsif.runtime.module_api`.
- Everything else — `os`, `sys`, `subprocess`, sockets, and *transitive
  attribute imports* like `from rsif.commands import os` — is rejected with
  a line-precise violation.

It is a whitelist, not a blacklist, precisely because blacklists are
bypassable via transitive imports (found and fixed in the M13 review).
Honest boundary: MODULE code is exec'd in-process (it must implement the
ABI in the engine process), so the scan is the primary barrier for that
surface; SKILL code additionally runs in the sandbox below, where the scan
is an early, explainable rejection.

## The sandbox (`sandbox/exec.py`)

One subprocess code path for skill execution and hidden-test scoring:

- `python -I` (isolated: no user site, no env vars), temp cwd,
- wall/CPU timeouts (`sandbox_timeout_s`, default 10 s),
- rlimits (`sandbox_mem_mb`, default 512 MB) where the platform supports
  them,
- **minimal environment — PATH only**: API keys and secrets are invisible
  to evolved code.

`ExecutionOutcome` carries ok/stdout/error; infinite loops are killed at
the timeout, memory hogs at the rlimit (both pinned by tests). Residual
limitation, documented: network egress from the child is *not* blocked (no
seccomp on macOS) — the scrubbed environment removes the exfiltration
prize, not the socket.

## Skills end to end

1. The improver proposes `skill/add` with `module.py` + `manifest.json` →
   design gates: static scan, then assembly.
2. `build_spec` turns the artifact into a `SkillSpec` (name, description,
   code); `compose_system()` advertises it ("## Available skills").
3. At runtime the provider may emit a tool call; `AgentRuntime._tool`
   looks the skill up by name and executes it in the sandbox via a small
   runner (`json.loads(args)` → `main(**args)` → printed result).
4. The observation returns to the session as tool + user messages —
   execution feedback the module can chain on [Voyager].

## Invariants (and where they're pinned)

1. Loader rejects non-ABI and forbidden-import sources *pre-execution*
   (`test_meta_and_module.py`, loader tests).
2. Sandbox kills infinite loops and memory hogs deterministically
   (`test_sandbox.py`).
3. A custom module can drive the loop with **zero** LLM calls
   (`test_runtime.py`) — the ABI is genuinely in control.
4. Evolved system prompt is really sent to the provider (fixed in M7; the
   runtime composes `spec.compose_system()` into every request).
