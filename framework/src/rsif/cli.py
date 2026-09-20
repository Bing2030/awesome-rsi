"""rsif command-line interface.

Subcommands are wired up milestone by milestone; `rsif --help` always works.
"""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rsif",
        description="Recursive Self-Improvement Framework: evolve agents through a "
        "verified propose -> explore -> design -> verify -> correct loop.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="scaffold a run workspace with seed artifacts")
    p_init.add_argument("rundir", help="directory to create the workspace in")
    p_init.add_argument("--objective", default="code-tasks", choices=["code-tasks", "exact-match"])
    p_init.add_argument("--provider", default="scripted")
    p_init.add_argument("--model", default="")
    p_init.add_argument("--seed", type=int, default=0)

    p_run = sub.add_parser("run", help="evaluate the active agent on a task split")
    p_run.add_argument("--run", default=".", help="workspace root")
    p_run.add_argument("--split", default="val", choices=["train", "val", "test"])
    p_run.add_argument("--tasks", default="all", help="'all' or comma-separated task ids")

    p_evolve = sub.add_parser("evolve", help="run the self-improvement loop")
    p_evolve.add_argument("--run", default=".", help="workspace root")
    p_evolve.add_argument("--generations", type=int, default=None)
    p_evolve.add_argument("--proposals", type=int, default=None,
                          help="proposals per generation")
    p_evolve.add_argument("--budget-usd", type=float, default=None)

    p_status = sub.add_parser("status", help="archive table, best fitness, spend, alarms")
    p_status.add_argument("--run", default=".", help="workspace root")

    p_inspect = sub.add_parser("inspect", help="query events / artifact lineage")
    p_inspect.add_argument("--run", default=".", help="workspace root")
    p_inspect.add_argument("--events", action="store_true")
    p_inspect.add_argument("--filter", default=None, help="e.g. kind=accept")
    p_inspect.add_argument("--artifact", default=None, help="artifact id for lineage")
    p_inspect.add_argument("--tail", type=int, default=20)

    p_rb = sub.add_parser("rollback", help="roll an artifact back to a version")
    p_rb.add_argument("--run", default=".", help="workspace root")
    p_rb.add_argument("--artifact", required=True)
    p_rb.add_argument("--to", type=int, required=True)

    p_report = sub.add_parser("report", help="evaluate archive frontier on the sealed test split")
    p_report.add_argument("--run", default=".", help="workspace root")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", False) and not args.command:
        from rsif import __version__

        print(__version__)
        return 0
    if not args.command:
        parser.print_help()
        return 0

    from rsif import commands

    handler = getattr(commands, f"cmd_{args.command}", None)
    if handler is None:
        print(f"command not implemented yet: {args.command}", file=sys.stderr)
        return 2
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
