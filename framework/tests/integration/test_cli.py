"""M9 verification: the full CLI lifecycle on the offline scripted demo.

init -> evolve -> status -> inspect -> run -> rollback -> report, plus a
cross-process determinism check (same seed -> identical event stream with
timestamps stripped, identical archive bytes).
"""

import json

from rsif.cli import main
from rsif.observe.events import EventLog

EVOLVE = ["evolve", "--generations", "3", "--proposals", "1"]


def _init_evolve(root, tag):
    run = root / tag
    assert main(["init", str(run), "--provider", "scripted", "--seed", "0"]) == 0
    assert main([*EVOLVE, "--run", str(run)]) == 0
    return run


def test_cli_full_demo_lifecycle(tmp_path, capsys):
    run = _init_evolve(tmp_path, "demo")

    # -- status renders archive + checkout read-only ---------------------------
    assert main(["status", "--run", str(run)]) == 0
    out = capsys.readouterr().out
    assert "objective:   code-tasks" in out
    assert "3 accepted   0 rejected" in out
    assert "[prompt, 4, 0] | 1.0000  | 2   | g2p1" in out
    assert "[seed, 2, 0]   | 0.6000  | 0   | seed" in out
    assert "prompt/system          | v3" in out  # active agent = level-3 strategy
    assert "alarms:      none" in out

    # -- inspect: filtered events show the two-level acceptance story ----------
    assert main(["inspect", "--run", str(run), "--events",
                 "--filter", "kind=accept"]) == 0
    out = capsys.readouterr().out
    assert out.count("accept ") == 3
    assert '"promoted": true' in out
    assert '"promoted": false' in out  # g3 stepping stone was NOT deployed

    # -- run: the active agent scores 1.0 on val; task filter works -----------
    assert main(["run", "--run", str(run), "--split", "val"]) == 0
    assert "fitness: 1.0000" in capsys.readouterr().out
    assert main(["run", "--run", str(run), "--split", "val",
                 "--tasks", "val/01,val/02"]) == 0
    assert "(2/2 passed)" in capsys.readouterr().out
    assert main(["run", "--run", str(run), "--split", "val",
                 "--tasks", "val/99"]) == 2

    # -- rollback: v1 (seed strategy) scores 0.6; restore v3 -> 1.0 ------------
    assert main(["rollback", "--run", str(run),
                 "--artifact", "prompt/system", "--to", "1"]) == 0
    assert main(["run", "--run", str(run), "--split", "val"]) == 0
    assert "fitness: 0.6000" in capsys.readouterr().out
    assert main(["inspect", "--run", str(run), "--artifact", "prompt/system"]) == 0
    assert "restore | v4 -> v1" in capsys.readouterr().out
    assert main(["rollback", "--run", str(run),
                 "--artifact", "prompt/system", "--to", "3"]) == 0
    assert main(["run", "--run", str(run), "--split", "val"]) == 0
    assert "fitness: 1.0000" in capsys.readouterr().out
    # rolling back to a nonexistent version is a clean CLI error
    assert main(["rollback", "--run", str(run),
                 "--artifact", "prompt/system", "--to", "99"]) == 2

    # -- report: sealed test split, evaluated on the archive best --------------
    assert main(["report", "--run", str(run)]) == 0
    out = capsys.readouterr().out
    assert "sealed test split" in out
    assert "fitness: 1.0000" in out
    assert "test/05" in out

    # the report evaluation is visible in the event log
    events = EventLog(run / "events.jsonl").read()
    assert any(e.kind == "eval" and e.payload.get("label") == "report-test"
               for e in events)


def test_cli_demo_is_deterministic_across_processes(tmp_path):
    """Two workspaces, same seed: identical event streams (ts stripped) and
    byte-identical archives."""
    a = _init_evolve(tmp_path, "det_a")
    b = _init_evolve(tmp_path, "det_b")

    def strip_ts(run):
        return [(e.seq, e.kind, e.phase, e.generation, e.payload)
                for e in EventLog(run / "events.jsonl").read()]

    assert strip_ts(a) == strip_ts(b)
    assert (a / "archive.json").read_bytes() == (b / "archive.json").read_bytes()
    assert (a / "checkout.json").read_bytes() == (b / "checkout.json").read_bytes()


def test_cli_demo_story_matches_expected_scores(tmp_path):
    """The scripted demo is not just 'it runs': the baseline/level-2/level-3
    val scores are the designed 0.6 / 0.8 / 1.0 and only real improvements
    get promoted."""
    run = _init_evolve(tmp_path, "story")
    events = EventLog(run / "events.jsonl").read()
    accepts = [e for e in events if e.kind == "accept"]
    assert [a.payload["val_child"] for a in accepts] == [0.8, 1.0, 0.8]
    assert [a.payload["promoted"] for a in accepts] == [True, True, False]

    checkout = json.loads((run / "checkout.json").read_text())
    assert checkout["prompt/system"] == 3  # level-3 strategy is the active agent

    baseline_val = next(e.payload["score"] for e in events
                        if e.kind == "eval" and e.payload.get("label") == "baseline"
                        and e.payload["suite"] == "val")
    assert baseline_val == 0.6
