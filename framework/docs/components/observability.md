# Component guide — observability, CLI, determinism

*One append-only event log is the backbone: what the CLI renders, what
memory learns from, and what makes runs replayable.*

Files: `src/rsif/observe/{events,render}.py`, `src/rsif/cli.py`,
`src/rsif/commands.py`, `src/rsif/llm/cache.py`. Verified by
`tests/unit/test_events.py`, `tests/integration/test_cli.py`,
`tests/golden/`.

## The event log (`observe/events.py`)

Append-only JSONL at `<run>/events.jsonl`. Every engine action appends one
event:

```json
{"seq": 42, "ts": 1758…, "kind": "gate", "phase": "verification",
 "generation": 1, "payload": {"proposal_id": "g1p1", "gate": "val",
 "passed": true, "child": 0.8, "parent": 0.4, "threshold": 0.02}}
```

The 18 kinds: `run_start · run_end · proposal · patch · screen · eval ·
gate · accept · reject · reflect · archive_update · rollback · budget ·
llm_call · approval · error · meta_confirm · meta_revert`. The five phases
(`proposal / design / exploration / verification / correction`) stamp
every phase-relevant event; `llm_call` events attribute every completion
to a role and token counts (edit attribution [2604.25850]).

Payload discipline — **ids, scores, decisions only**: never wall-times,
never sandbox stderr, never request ids. That is what makes the golden log
byte-stable and diffs meaningful. The clock is injectable; deterministic
tests pin it to 0.

`EventLog` is a plain reader/writer (`read / tail / filter(kind,
generation)`); everything else renders from it.

## The CLI (`cli.py` + `commands.py`)

```
rsif init <dir> [--objective …] [--provider …] [--model …] [--seed …]
        scaffold the workspace + seed artifacts
rsif evolve --run <dir> [--generations N] [--proposals N] [--budget-usd X]
        run the loop; prints the summary (accepted/rejected/best/stop_reason)
rsif run --run <dir> --split val|train|test [--tasks all|ids]
        evaluate the ACTIVE agent through the evolve-time path
rsif status --run <dir>
        archive table (descriptor/fitness/gen), checkout, spend, alarms
rsif inspect --run <dir> [--events] [--filter kind=accept] [--artifact <id>] [--tail N]
        query events or an artifact's lineage
rsif rollback --run <dir> --artifact <id> --to <version>
        time travel (append-only restore)
rsif report --run <dir>
        unseal the test split on the archive best + bootstrap CI
```

- Rendering is **timestamp-free** (seq/kind/phase/generation/payload), so
  outputs are diff-stable and snapshot-testable.
- `run`/`report` call `engine.evaluate_active` / `evaluate_snapshot` — the
  *same* memoized, event-logged evaluation path as evolution; CLI scores
  are directly comparable to evolve-time scores.
- `report` unseals the sealed test split **only on the archive best**, with
  a seeded bootstrap CI — the guard against lucky-task claims.
- `status` reads archive + events + budget snapshot: one screen answers
  "what is deployed, what is known, what did it cost".

## Determinism & replay

The reproducibility stack, layer by layer:

1. **Explicit RNG threading** — one `random.Random(cfg.seed)` in the
   engine; no global randomness. Seeded providers (temperature/seed passed
   through to APIs that accept them).
2. **Scripted/demo providers** — `ScriptedProvider` (strict FIFO per role)
   for tests; `DemoProvider` (content-addressed by role + request text) for
   the offline CLI demo — deterministic regardless of evaluation order.
3. **Eval memoization** — each (mapping, split, task-ids) evaluated exactly
   once per run; scorebooks persisted to `evals/gen_NNNN/`.
4. **Timestamp-free payloads** + injectable clock (tests pin 0).
5. **Golden test** — a full 2-proposal run reproduces `events.jsonl`,
   `archive.json`, `checkout.json`, `lineage.jsonl` **byte-identically**
   across processes and against the committed golden; regenerate
   deliberately with `RSIF_UPDATE_GOLDEN=1 pytest tests/golden`.
6. **Offline guard** — the test suite blocks `socket.socket` (except
   `live`-marked tests), so accidental network calls fail loudly.
7. **Real-provider replay** — `seed.json` + the disk response cache
   (`llm/cache.py`, content-addressed) lets a live run be re-executed with
   zero new spend; the regex_agent runner uses exactly this.

## Reading a run like the maintainers do

```bash
uv run rsif status --run ../runs/demo        # where is the agent now?
uv run rsif inspect --run ../runs/demo --filter kind=accept
uv run rsif inspect --run ../runs/demo --filter kind=reject   # every death + reason
uv run rsif inspect --run ../runs/demo --artifact prompt/system  # its whole history
uv run rsif report --run ../runs/demo        # the sealed verdict + CI
```

The rejection reasons you will see, and what they mean:

| `reason` | Meaning |
|---|---|
| `parse` | improver output wasn't one valid JSON proposal |
| `surface` | surface closed this generation (META cadence) |
| `approval` | META edit denied / no approver (fail-closed) |
| `meta_pending` | another META window is open |
| `bounded` / `operator` / `apply` | patch failed validation/materialization |
| `scan` / `load` | code unsafe or unloadable (pre-execution) |
| `screen` | cascade screen: ≥ ε below parent on probe tasks |
| `canary` | canary regression — hard reject |
| `val` | no held-out gain past θ + paired net-gain floor |
