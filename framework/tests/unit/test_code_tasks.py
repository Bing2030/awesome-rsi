"""M3 verification: code-tasks objective scores deterministically."""

from rsif.objectives.base import Split
from rsif.objectives.code_tasks import CodeTasksObjective
from rsif.runtime.types import Attempt


def _objective():
    return CodeTasksObjective()


def _attempt(code: str) -> Attempt:
    return Attempt(task_id="x", result=f"```python\n{code}\n```")


def test_suites_load_all_splits():
    obj = _objective()
    suites = obj.suites()
    assert set(suites) == set(Split)
    assert len(suites[Split.TRAIN]) >= 3
    assert len(suites[Split.VAL]) >= 3
    assert len(suites[Split.TEST]) >= 3
    assert len(suites[Split.CANARY]) >= 3


def test_known_good_scores_1():
    obj = _objective()
    task = obj.suites()[Split.TRAIN].tasks[0]
    score = obj.evaluate(task, _attempt("def add(a, b):\n    return a + b\n"))
    assert score.score == 1.0


def test_known_bad_scores_0():
    obj = _objective()
    task = obj.suites()[Split.TRAIN].tasks[0]
    score = obj.evaluate(task, _attempt("def add(a, b):\n    return a - b\n"))
    assert score.score == 0.0
    assert score.detail  # error text preserved for reflection


def test_deterministic_repeat():
    obj = _objective()
    task = obj.suites()[Split.TRAIN].tasks[0]
    a = obj.evaluate(task, _attempt("def add(a, b):\n    return a + b\n"))
    b = obj.evaluate(task, _attempt("def add(a, b):\n    return a + b\n"))
    assert a.score == b.score == 1.0


def test_fitness_mean():
    from rsif.objectives.base import ScoreBook

    obj = _objective()
    train = obj.suites()[Split.TRAIN]
    book = ScoreBook()
    for t in train.tasks:
        book.add(obj.evaluate(t, _attempt("def {}(*a):\n    return None\n"
                                          .format(t.meta["function_name"]))))
    # all wrong -> mean 0
    assert obj.fitness(book) == 0.0
