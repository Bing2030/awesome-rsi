"""Terminal rendering for `rsif status/inspect/run/report`.

Pure formatting over workspace files and engine results - no I/O of its
own except reading the workspace, no timestamps (rendered output must be
snapshot-testable and diff-stable).
"""

from __future__ import annotations

import json

from rsif.objectives.base import ScoreBook, Split, TaskSuite


# -- generic table -----------------------------------------------------------


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    sep = "-+-".join("-" * w for w in widths)

    def fmt(row: list[str]) -> str:
        return " | ".join(str(c).ljust(w) for c, w in zip(row, widths))

    lines = [fmt(headers), sep]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


# -- events ------------------------------------------------------------------


def event_line(e) -> str:
    payload = json.dumps(e.payload, sort_keys=True, default=str)
    if len(payload) > 96:
        payload = payload[:93] + "..."
    phase = e.phase or "-"
    return f"{e.seq:>4}  {e.kind:<14} {phase:<12} g{e.generation:<4} {payload}"


def events_table(events: list) -> str:
    if not events:
        return "(no events)"
    return "\n".join(event_line(e) for e in events)


def lineage_table(entries: list) -> str:
    if not entries:
        return "(no lineage entries)"
    rows = [[str(e.seq), e.artifact_id, e.op, f"v{e.from_v} -> v{e.to_v}",
             e.proposal_id or "-", str(e.generation)] for e in entries]
    return table(["seq", "artifact", "op", "version", "proposal", "gen"], rows)


# -- run / report ------------------------------------------------------------


def scorebook(book: ScoreBook, suite: TaskSuite) -> str:
    rows = [[s.task_id, "pass" if s.score >= 1.0 else "FAIL",
             s.detail[:60]] for s in book.scores]
    out = table(["task", "result", "detail"], rows)
    out += f"\n{suite.split.value}: {book.mean():.4f} "
    out += f"({int(sum(1 for s in book.scores if s.score >= 1.0))}/{len(book.scores)} passed)"
    return out


def run_summary(summary) -> str:
    best = f"{summary.best_fitness:.4f}" if summary.best_fitness is not None else "-"
    desc = _fmt(summary.best_descriptor) if summary.best_descriptor else "-"
    lines = [
        f"generations: {summary.generations}",
        f"accepted:    {summary.accepted}",
        f"rejected:    {summary.rejected}",
        f"best:        fitness {best}  descriptor {desc}",
    ]
    if summary.stop_reason:
        lines.append(f"stop_reason: {summary.stop_reason}")
    return "\n".join(lines)


def report(test_book: ScoreBook, lo: float, hi: float, baseline_note: str) -> str:
    lines = [
        "sealed test split (now unsealed - do not evolve against it)",
        f"fitness: {test_book.mean():.4f}",
        f"95% bootstrap CI: [{lo:.4f}, {hi:.4f}]",
        baseline_note,
        "",
        scorebook(test_book, TaskSuite(Split.TEST, [])),
    ]
    return "\n".join(lines)


# -- status ------------------------------------------------------------------


def status(ws) -> str:
    """Read-only overview of a workspace: archive, spend, alarms, checkout."""
    from rsif.observe.events import EventLog

    cfg = ws.config()
    events = EventLog(ws.events_path).read()

    lines = [f"run:         {ws.root}",
             f"objective:   {cfg.get('objective', '?')}   seed: {cfg.get('seed', '?')}"]

    run_ends = [e for e in events if e.kind == "run_end"]
    if run_ends:
        last = run_ends[-1].payload
        stop = last.get("stop_reason", "none")
        lines.append(f"runs:        {len(run_ends)}   last stop: {stop}")
    else:
        lines.append("runs:        0 (evolve not started)")

    llm = [e for e in events if e.kind == "llm_call"]
    tin = sum(e.payload.get("in_tokens", 0) for e in llm)
    tout = sum(e.payload.get("out_tokens", 0) for e in llm)
    lines.append(f"llm:         {len(llm)} calls   {tin} in / {tout} out tokens")

    accepted = sum(1 for e in events if e.kind == "accept")
    rejected = sum(1 for e in events if e.kind == "reject")
    lines.append(f"proposals:   {accepted} accepted   {rejected} rejected")

    # archive
    archive_path = ws.root / "archive.json"
    if archive_path.exists():
        data = json.loads(archive_path.read_text(encoding="utf-8"))
        cells = data.get("cells", [])
        lines.append(f"archive:     {len(cells)} cells")
        rows = [[_fmt(c["descriptor"]), f"{c['fitness']:.4f}",
                 str(c.get("generation", "-")), c.get("proposal_id") or "seed"]
                for c in sorted(cells, key=lambda c: -c["fitness"])]
        lines.append(table(["descriptor", "fitness", "gen", "source"], rows))
        if cells:
            best = max(cells, key=lambda c: c["fitness"])
            lines.append(
                f"best:        {best['fitness']:.4f}  "
                f"descriptor {_fmt(best['descriptor'])}")
    else:
        lines.append("archive:     (empty)")

    # checkout
    checkout = json.loads(ws.checkout_path.read_text(encoding="utf-8"))
    rows = [[aid, f"v{v}"] for aid, v in sorted(checkout.items())]
    lines.append("checkout:")
    lines.append(table(["artifact", "active"], rows))

    # alarms / denied approvals
    denied = [e for e in events if e.kind == "approval" and not e.payload.get("approved")]
    if denied:
        for e in denied:
            lines.append(
                f"alarm:       g{e.generation} {e.payload.get('action', 'approval')} "
                f"NOT approved ({', '.join(e.payload.get('alarms', [])) or 'meta'})")
    else:
        lines.append("alarms:      none")
    return "\n".join(lines)
