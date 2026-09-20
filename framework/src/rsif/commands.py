"""CLI command implementations.

`scripted` workspaces run the whole lifecycle offline against DemoProvider
(deterministic, no network); real providers get a disk-cached adapter.
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

from rsif.config import RunConfig


# -- shared plumbing -----------------------------------------------------------


def _workspace(run: str):
    from rsif.artifacts.workspace import RunWorkspace

    return RunWorkspace.open(Path(run))


def _provider(cfg: RunConfig, ws):
    name = os.environ.get("RSIF_PROVIDER", cfg.provider)
    if name == "scripted":
        from rsif.llm.demo import DemoProvider

        return DemoProvider(objective=cfg.objective)
    from rsif.llm.factory import provider_from_config

    return provider_from_config(cfg, cache=ws.cache_dir / "llm")


def _engine(cfg: RunConfig, ws):
    """Build an engine over an existing workspace (no side effects until used)."""
    from rsif.artifacts.store import ArtifactStore
    from rsif.evolve.engine import EvolutionEngine
    from rsif.objectives import objective_from_config

    store = ArtifactStore.open(ws)
    approver = None
    if cfg.require_approval_for_meta and sys.stdin.isatty():
        from rsif.safety.approvers import CLIApprover

        approver = CLIApprover()
    return EvolutionEngine(store=store, provider=_provider(cfg, ws),
                           objective=objective_from_config(cfg), cfg=cfg,
                           approver=approver)


# -- commands --------------------------------------------------------------------


def cmd_init(args) -> int:
    from rsif.artifacts.store import ArtifactStore
    from rsif.artifacts.workspace import RunWorkspace

    rundir = Path(args.rundir)
    cfg = RunConfig(
        objective=args.objective,
        provider=args.provider,
        model=args.model,
        seed=args.seed,
    )
    ws = RunWorkspace.init(rundir, cfg.to_dict(), cfg.seed)
    store = ArtifactStore.open(ws)
    store.seed_defaults(cfg)
    print(f"initialized workspace at {rundir} (objective={cfg.objective}, provider={cfg.provider})")
    return 0


def cmd_evolve(args) -> int:
    from rsif.observe import render

    ws = _workspace(args.run)
    cfg = RunConfig.from_dict(ws.config())
    if args.generations is not None:
        cfg.generations = args.generations
    if args.proposals is not None:
        cfg.proposals_per_generation = args.proposals
    if args.budget_usd is not None:
        cfg.budget_usd = args.budget_usd
    summary = _engine(cfg, ws).run()
    print(render.run_summary(summary))
    return 0


def cmd_run(args) -> int:
    from rsif.llm.base import ProviderError
    from rsif.objectives.base import Split, TaskSuite
    from rsif.observe import render

    ws = _workspace(args.run)
    cfg = RunConfig.from_dict(ws.config())
    engine = _engine(cfg, ws)
    split = Split(args.split)
    suite = engine.objective.suites()[split]
    if args.tasks != "all":
        wanted = {t.strip() for t in args.tasks.split(",") if t.strip()}
        suite = TaskSuite(split, [t for t in suite.tasks if t.id in wanted])
        missing = wanted - {t.id for t in suite.tasks}
        if missing:
            print(f"unknown task ids: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    try:
        book = engine.evaluate_active(suite, label=f"run-{args.split}")
    except ProviderError as e:
        print(f"provider error: {e}", file=sys.stderr)
        return 2
    print(render.scorebook(book, suite))
    print(f"fitness: {engine.objective.fitness(book):.4f}")
    return 0


def cmd_status(args) -> int:
    from rsif.observe import render

    print(render.status(_workspace(args.run)))
    return 0


def _filter_events(events, spec: str | None):
    if not spec:
        return events
    for clause in spec.split(","):
        if "=" not in clause:
            raise SystemExit(f"bad --filter (want key=value): {clause!r}")
        key, value = clause.split("=", 1)
        if key == "generation":
            events = [e for e in events if e.generation == int(value)]
        else:
            events = [e for e in events if getattr(e, key, None) == value]
    return events


def cmd_inspect(args) -> int:
    from rsif.artifacts.store import ArtifactStore
    from rsif.observe import render
    from rsif.observe.events import EventLog

    ws = _workspace(args.run)
    if args.artifact:
        store = ArtifactStore.open(ws)
        print(render.lineage_table(store.lineage(args.artifact)))
        return 0
    events = _filter_events(EventLog(ws.events_path).read(), args.filter)
    tail = events[-args.tail:] if args.tail > 0 else events
    print(render.events_table(tail))
    return 0


def cmd_rollback(args) -> int:
    from rsif.artifacts.store import ArtifactStore
    from rsif.observe.events import ROLLBACK, EventLog

    ws = _workspace(args.run)
    store = ArtifactStore.open(ws)
    try:
        store.restore(args.artifact, args.to, proposal_id="cli")
    except Exception as e:  # noqa: BLE001 - surface a clean CLI error
        print(f"rollback failed: {e}", file=sys.stderr)
        return 2
    EventLog(ws.events_path).append(
        ROLLBACK, phase="correction", action="manual",
        artifact=args.artifact, restored={args.artifact: args.to})
    print(f"rolled back {args.artifact} to v{args.to} (active checkout updated)")
    return 0


def cmd_report(args) -> int:
    from rsif.llm.base import ProviderError
    from rsif.objectives.base import Split
    from rsif.objectives.base import bootstrap_ci as _ci
    from rsif.observe import render

    ws = _workspace(args.run)
    cfg = RunConfig.from_dict(ws.config())
    engine = _engine(cfg, ws)
    best = engine.archive.best()
    if best is None:
        print("archive is empty - run `rsif evolve` first", file=sys.stderr)
        return 2
    test_suite = engine.objective.suites().get(Split.TEST)
    if not test_suite or not test_suite.tasks:
        print("this objective ships no sealed test split", file=sys.stderr)
        return 2
    try:
        book = engine.evaluate_snapshot(best.spec_snapshot, test_suite,
                                        label="report-test")
    except ProviderError as e:
        print(f"provider error: {e}", file=sys.stderr)
        return 2
    lo, hi = _ci([s.score for s in book.scores], rng=random.Random(cfg.seed))
    note = (f"archive best: fitness {best.fitness:.4f} "
            f"descriptor {tuple(best.descriptor)} (gen {best.generation})")
    print(render.report(book, lo, hi, note))
    return 0
