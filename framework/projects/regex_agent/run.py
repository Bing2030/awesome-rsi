"""Run the regex-agent project end-to-end: a real model through the gateway.

Usage (from framework/):

    uv run python -m projects.regex_agent.run --run ../runs/regex \
        --model glm-5.3-flash --generations 2 --proposals 1

Reads the gateway from the environment (ANTHROPIC_BASE_URL /
ANTHROPIC_AUTH_TOKEN - the same vars Claude Code uses). Hard budgets cap the
run; responses are disk-cached so a re-run with the same seed replays
without new spend. META edits are fail-closed in non-interactive runs (by
design - pass --tty to get the y/N approver on a real terminal).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rsif.artifacts.store import ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.engine import EvolutionEngine
from rsif.llm.factory import provider_from_config
from rsif.observe import render
from rsif.objectives.base import Split


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="workspace directory")
    ap.add_argument("--model", default="glm-5.3-flash")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--generations", type=int, default=2)
    ap.add_argument("--proposals", type=int, default=1)
    ap.add_argument("--budget-usd", type=float, default=1.0)
    ap.add_argument("--budget-calls", type=int, default=150)
    ap.add_argument("--budget-wall-s", type=float, default=1800.0)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--tty", action="store_true",
                    help="wire the interactive approver for META edits")
    args = ap.parse_args(argv)

    cfg = RunConfig(
        objective="regex-tasks",  # identifies THIS project's objective
        provider="anthropic", model=args.model, seed=args.seed,
        temperature=args.temperature,
        generations=args.generations, proposals_per_generation=args.proposals,
        screen_tasks=2,
        budget_usd=args.budget_usd, budget_llm_calls=args.budget_calls,
        budget_wall_clock_s=args.budget_wall_s,
    )

    ws = RunWorkspace.init(Path(args.run), cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws)
    store.seed_defaults(cfg)

    approver = None
    if args.tty and sys.stdin.isatty():
        from rsif.safety.approvers import CLIApprover

        approver = CLIApprover()

    engine = EvolutionEngine(
        store=store,
        provider=provider_from_config(cfg, cache=ws.cache_dir / "llm"),
        objective=_objective(),
        cfg=cfg, approver=approver,
    )
    summary = engine.run()
    print(render.run_summary(summary))

    # what actually happened: baseline vs final on the held-out val split
    events = engine.events.read()
    val_evals = [e for e in events if e.kind == "eval"
                 and e.payload.get("suite") == "val"]
    if val_evals:
        print(f"\nval trace: " + " -> ".join(
            f"{e.payload['score']:.2f}" for e in val_evals))
    accepts = [e for e in events if e.kind == "accept"]
    for a in accepts:
        print(f"accept g{a.generation} {a.payload['proposal_id']}: "
              f"val {a.payload['val_parent']:.2f} -> {a.payload['val_child']:.2f} "
              f"(promoted={a.payload['promoted']})")
    rejects = [e for e in events if e.kind == "reject"]
    for r in rejects:
        print(f"reject g{r.generation} {r.payload['proposal_id']}: "
              f"{r.payload['reason']}")

    # sealed test split: only looked at AFTER the run, for the report
    best = engine.archive.best()
    if best is not None:
        book = engine.evaluate_snapshot(best.spec_snapshot,
                                        _objective().suites()[Split.TEST],
                                        label="final-test")
        print(f"\nsealed test split on archive best: {book.mean():.2f}")
    return 0


def _objective():
    from projects.regex_agent.objective import RegexObjective

    return RegexObjective()


if __name__ == "__main__":
    raise SystemExit(main())
