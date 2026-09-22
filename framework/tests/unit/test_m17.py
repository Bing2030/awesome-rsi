"""M17 verification: the three RSIAgent-inspired change-register entries.

CR-1 (train-split gap map): the improver sees which TRAIN tasks the active
    agent fails, never val/test task detail [2609.15364 §3.2/§4.6].
CR-2 (infra failures are unscored): sandbox timeout/spawn/signal-kill carry no
    verdict, so means and paired gates skip them rather than read 0.0
    [2609.15364 §4.1: "an infrastructure failure is unscored"].
CR-3 (scoped insights): insights record an "applies when…" condition so a
    lesson is not over-applied [2609.15364 §4.6 rule-scope loss].
"""

from rsif.artifacts.store import ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.archive import Archive, Individual
from rsif.evolve.engine import EvolutionEngine
from rsif.evolve.proposer import Improver
from rsif.evolve.selection import paired_scores
from rsif.llm.mock import ScriptedProvider, text_result
from rsif.memory.insights import InsightStore
from rsif.objectives.base import ScoreBook, Split, TaskScore
from rsif.objectives.code_tasks import CodeTasksObjective
from rsif.sandbox.exec import ExecutionOutcome


# -- CR-1: train-split gap map ---------------------------------------------------


def _parent():
    return Individual(descriptor=("prompt", 3), fitness=0.5, val_score=0.5,
                      spec_snapshot={"prompt/system": 1}, generation=1,
                      proposal_id="seed")


def test_improver_build_prompt_renders_gaps(store):
    store.seed_defaults(RunConfig())
    archive = Archive()
    parent = _parent()
    archive.add(parent)
    improver = Improver(ScriptedProvider(), RunConfig())
    system, user = improver.build_prompt(store, archive, "(lessons)",
                                         parent, gaps="- train/03: fails")
    assert "Train-split gaps" in user
    assert "- train/03: fails" in user
    assert "Current agent" in user  # other slots still filled


def test_train_gaps_text_is_train_only(tmp_path):
    """The active agent's train failures reach the improver; val/test do not."""
    cfg = RunConfig(generations=1, proposals_per_generation=1, seed=0)
    ws = RunWorkspace.init(tmp_path / "run", cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    obj = CodeTasksObjective()

    p = ScriptedProvider()
    for split in (Split.TRAIN, Split.CANARY, Split.VAL):
        for t in obj.suites()[split].tasks:
            fn = t.meta["function_name"]
            p.add("agent", "", text_result(
                f"```python\ndef {fn}(*args):\n    return None\n```"))
    engine = EvolutionEngine(store=store, provider=p, objective=obj, cfg=cfg,
                             clock=lambda: 0.0)
    root = engine._baseline()
    engine._active_snapshot = dict(root.spec_snapshot)  # as run() sets it

    n_eval_before = sum(1 for e in engine.events.read() if e.kind == "eval")
    gaps = engine._train_gaps_text()
    n_eval_after = sum(1 for e in engine.events.read() if e.kind == "eval")

    assert "train/01" in gaps          # failing train tasks surface
    assert "val/" not in gaps          # held-out split stays sealed
    assert "test" not in gaps
    assert n_eval_after == n_eval_before  # memo lookup: no extra evaluation


# -- CR-2: infra failures are unscored -------------------------------------------


def test_scorebook_mean_ignores_infra():
    book = ScoreBook()
    book.add(TaskScore("a", 1.0))
    book.add(TaskScore("b", 0.0, infra=True))  # timeout: no verdict
    assert book.mean() == 1.0
    assert book.n_scored == 1 and book.n_infra == 1


def test_paired_scores_excludes_infra():
    child = ScoreBook([TaskScore("a", 1.0), TaskScore("b", 0.0, infra=True)])
    parent = ScoreBook([TaskScore("a", 0.0), TaskScore("b", 0.0)])
    c, p = paired_scores(child, parent)
    assert c == [1.0] and p == [0.0]  # only commonly-scored task a compared


def test_paired_scores_none_when_no_common():
    child = ScoreBook([TaskScore("a", 0.0, infra=True)])
    parent = ScoreBook([TaskScore("b", 0.0, infra=True)])
    assert paired_scores(child, parent) is None


def _outcome(**kw):
    d = dict(ok=False, exit_code=1, stdout="", stderr="", timed_out=False,
             wall_s=0.0)
    d.update(kw)
    return ExecutionOutcome(**d)


def _code_obj(sandbox):
    return CodeTasksObjective(sandbox=sandbox)


def _train_task(obj):
    return obj.suites()[Split.TRAIN].tasks[0]


def _attempt():
    from rsif.runtime.types import Attempt
    return Attempt(task_id="x", result="```python\ndef add(a, b):\n    return a + b\n```")


def test_timeout_classified_infra():
    obj = _code_obj(lambda prog: _outcome(timed_out=True, exit_code=-1))
    score = obj.evaluate(_train_task(obj), _attempt())
    assert score.score == 0.0 and score.infra is True


def test_signal_kill_classified_infra():
    obj = _code_obj(lambda prog: _outcome(exit_code=-9))
    score = obj.evaluate(_train_task(obj), _attempt())
    assert score.infra is True


def test_spawn_error_classified_infra():
    def boom(prog):
        raise OSError("fork failed")
    obj = _code_obj(boom)
    score = obj.evaluate(_train_task(obj), _attempt())
    assert score.infra is True


def test_behavioral_failure_not_infra():
    obj = _code_obj(None)  # real sandbox: wrong answer -> exit 1 traceback
    task = obj.suites()[Split.TRAIN].tasks[0]
    from rsif.runtime.types import Attempt
    score = obj.evaluate(task, Attempt(task_id="x",
                                       result="```python\ndef add(a, b):\n    return a - b\n```"))
    assert score.score == 0.0 and score.infra is False


# -- CR-3: scoped insights -------------------------------------------------------


def test_insight_scope_roundtrip(tmp_path):
    store = InsightStore(tmp_path / "i.jsonl", clock=lambda: 0.0)
    store.distill([("t1", "use a loop not recursion", "short inputs")])
    assert store.all()[0].scope == "short inputs"
    reloaded = InsightStore(tmp_path / "i.jsonl", clock=lambda: 0.0)
    assert reloaded.all()[0].scope == "short inputs"


def test_insight_scope_rendered(tmp_path):
    store = InsightStore(tmp_path / "i.jsonl", clock=lambda: 0.0)
    store.distill([("t1", "use a loop not recursion", "short inputs")])
    out = store.render_for_context("loops")
    assert "[applies when: short inputs]" in out


def test_insight_unscoped_has_no_prefix(tmp_path):
    store = InsightStore(tmp_path / "i.jsonl", clock=lambda: 0.0)
    store.distill([("t1", "use a loop not recursion")])
    out = store.render_for_context("loops")
    assert "[applies when:" not in out
