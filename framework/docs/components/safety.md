# Component guide — the safety stack

*Misevolution is expected, not exceptional. Every mechanism here assumes
the loop will misbehave and makes the misbehavior cheap, bounded, and
reversible.*

Files: `src/rsif/safety/{budget,drift,rollback,approvers}.py`,
`src/rsif/sandbox/{guards,exec}.py`, plus gate ordering in the engine.
Verified by `tests/unit/test_safety.py`,
`tests/integration/test_safety_loop.py`, `tests/unit/test_sandbox.py`.

## The defense map

```
before the loop        per proposal                    per generation         ever
──────────────         ──────────────────────────     ─────────────────      ─────
charter + config       static scan (whitelist)        drift monitor          append-only
budget caps            load gate (module ABI)          ├ regression →        lineage;
approver wiring        screen → canary → val           │  auto-rollback      immutable
sandbox rlimits        bounded patches                 └ stagnation →        versions;
                       META approval (fail-closed)       approve-or-stop      promotion-only
                       paired net-gain floor                                  activation
```

## Hard budget (`safety/budget.py`)

Three dimensions — LLM calls, estimated USD, wall clock — checked at two
points:

- **`exhausted()`** — before starting new work; fires *at* the limit.
- **`overshot()`** — after every recorded completion (the engine's
  `_EventfulProvider`); a call that pushes strictly *past* a limit raises
  `BudgetExhausted` immediately.

The two-point check bounds overshoot to **one call**, not one proposal
(~20–30 calls) — an M13 fix. On either path the run aborts cleanly: a
`budget` event with the full snapshot, `stop_reason="budget:<dim>"`, no
partial proposals, and `run_end` still lands. Defaults: 2000 calls, $1,
3600 s.

## Drift monitor (`safety/drift.py`)

Runs at every generation end **on the active agent**, all signals
execution-grounded (memoized scores, never self-judged):

| Alarm | Condition | Response |
|---|---|---|
| `canary_regression` | active canary < baseline canary | auto-rollback, run continues |
| `active_regression` | archive best > active val | auto-rollback, run continues |
| `stagnation` | ≥ threshold consecutive rejections (default `max(4, 2×proposals)`) | approval event; denied/unwired → stop (`drift`) |

Auto-rollback is defense-in-depth: the promotion gate already makes
regression of the deployed agent structurally very hard, and two-level
acceptance blocks the weak-parent ratchet — the monitor catches anything
that slips past (e.g. canary drift across many small accepted changes).

## Rollback semantics (`safety/rollback.py` + the store)

- Restoring an artifact **appends** a `restore` lineage entry — history is
  never rewritten (DGM backtracking semantics).
- Artifacts that did not exist in the target snapshot are *deactivated*
  (version 0 in the checkout), never deleted — files and lineage remain.
- Rollback targets: `rsif rollback --artifact X --to N` (manual,
  any version) or `auto_rollback` (engine, archive-best snapshot).
- META reverts use the same mechanism (`meta_revert` restores the pre-edit
  META versions mid-run).

## Approvers (`safety/approvers.py`)

`Approver.approve(proposal_id, summary) → bool` — the human/policy in the
loop for:

- **META edits** (the improver changing itself) — requested during phase 1;
- **drift continuation** (stagnation) — requested at generation end.

**Fail-closed everywhere**: no approver wired, EOF, or non-tty stdin ⇒
deny. `CLIApprover` prints a y/N prompt (attached only when stdin is a
TTY); `FakeApprover` serves tests/demos.

## Static scan (`sandbox/guards.py`) — see also [runtime.md](runtime.md)

An AST **import whitelist**: curated pure stdlib +
`rsif.runtime.module_api`, nothing else. Runs in the design phase, on
skill *and* module payloads, **before any execution** — including the cheap
screen. Line-precise violations; syntax errors are violations too.

Why whitelist: the M13 review showed the old blacklist was bypassable via
transitive attribute imports (`from rsif.commands import os`). Honest
boundary: MODULE code exec's in-process behind this scan (it must implement
the ABI in the engine process) — the scan is the primary barrier for that
surface. SKILL code runs in the subprocess sandbox where the scan is an
early, explainable rejection.

## Sandbox (`sandbox/exec.py`)

Subprocess `python -I`, temp cwd, wall+CPU timeouts, memory rlimits,
**PATH-only environment** — API keys invisible to evolved code. One code
path for skill execution and hidden-test scoring. Residual limitation
(documented, accepted): network egress from the child is not blocked (no
seccomp on macOS); the scrubbed env removes the exfiltration prize, not
the socket.

## Error paths (M13 hardening)

- **Provider failures** (`ProviderError`, with `origin`) propagate from
  the runtime → engine → CLI; abort cleanly with
  `stop_reason="error:<Origin>"`. Never a 0-score, never a fake "parse"
  rejection (an earlier bug: flaky gateways burned proposals as rejections).
- **Engine bugs** surface as `engine:<Type>` stop reasons — distinct from
  provider errors, so logs never misattribute framework bugs to
  infrastructure.
- `cmd_run` / `cmd_report` exit 2 on provider errors; the improver's own
  provider errors re-raise rather than masquerade as bad proposals.

## The trust boundary, restated

The engine, gates, store semantics, sandbox, and budget are **frozen,
trusted code**. The improver, prompts, skills, memory, architecture
modules, and policies are **artifacts — data**. The improver improving
itself is possible (META surface) but only through versioned, bounded,
approved, empirically-windowed edits. No artifact can reach the code that
evaluates it. `ModuleContext` exposes no store/engine handles; the
whitelist blocks importing them; the sandbox hides secrets; the budget
caps spend; the lineage makes every change reversible.

Where each guarantee is pinned:

| Guarantee | Test |
|---|---|
| Budget aborts cleanly, zero partial proposals, overshoot ≤ 1 call | `test_safety_loop.py` |
| Two-level acceptance blocks the weak-parent ratchet | `test_safety_loop.py` |
| Auto-rollback restores best snapshot, extras deactivated, history append-only | `test_safety.py`, `test_safety_loop.py` |
| Stagnation stops without approval, continues with it | `test_safety_loop.py` |
| Forbidden module rejected pre-execution | `test_meta_and_module.py` |
| Infinite loop / memory hog killed in the sandbox | `test_sandbox.py` |
| META approval fail-closed | `test_meta_and_module.py` |
| Provider error aborts cleanly (no fake scores) | `test_safety_loop.py` |
