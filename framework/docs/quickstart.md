# rsif Quickstart

A complete offline walkthrough in under a minute — no API key, no network.
(The scripted demo provider plays both the agent and the improver; see
`src/rsif/llm/demo.py`. The story it tells: the agent's val fitness goes
0.6 → 0.8 → 1.0 through two promoted prompt edits; a third, weaker edit is
kept as an archive stepping stone but **not** deployed.)

```bash
cd framework
uv sync

# 1. scaffold a workspace (versioned artifacts + seed agent)
uv run rsif init ../runs/demo --objective code-tasks --provider scripted

# 2. run the self-improvement loop: 3 generations x 1 proposal
uv run rsif evolve --run ../runs/demo --generations 3 --proposals 1
#   generations: 3
#   accepted:    3        (two promoted, one stepping stone)
#   best:        fitness 1.0000  descriptor [prompt, 4, 0]

# 3. inspect the run
uv run rsif status --run ../runs/demo          # archive table, spend, alarms
uv run rsif inspect --run ../runs/demo --events --tail 15
uv run rsif inspect --run ../runs/demo --filter kind=accept
uv run rsif inspect --run ../runs/demo --artifact prompt/system

# 4. evaluate the active agent
uv run rsif run --run ../runs/demo --split val          # 1.0000 (5/5)

# 5. unseal the test split on the archive best (bootstrap CI included)
uv run rsif report --run ../runs/demo

# 6. time travel (history is append-only; v2+ files are kept)
uv run rsif rollback --run ../runs/demo --artifact prompt/system --to 1
uv run rsif run --run ../runs/demo --split val          # back to 0.6000
uv run rsif rollback --run ../runs/demo --artifact prompt/system --to 3
```

## With a real model

```bash
export ANTHROPIC_API_KEY=sk-...
uv sync --extra anthropic
uv run --extra anthropic rsif init ../runs/live --provider anthropic \
    --model claude-sonnet-5
uv run --extra anthropic rsif evolve --run ../runs/live \
    --generations 2 --proposals 1 --budget-usd 1.0
```

META edits (the improver improving its own template) pause for an
interactive y/N approval when stdin is a TTY; non-interactive runs deny
them fail-closed. Hard budgets (`--budget-usd`, plus call/wall-clock caps
in `config.json`) stop the run cleanly at any boundary.

## Where to look next

- `docs/design.md` — every mechanism, its paper citation, code path, test
- `docs/plan.md` — milestone status table; `docs/decision-log.md` — decisions
- `tests/golden/test_flagship_evolution.py` — the byte-reproducible loop
- `examples/custom_objective.py` — plug in your own objective (~30 lines)
