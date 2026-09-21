"""Real-project verification (offline, deterministic): the regex_agent
project improves through the identical engine with zero engine changes.

Also checks the task pack's own solvability invariant: every reference
pattern passes its examples (a bad task cannot silently poison scoring -
the count_words incident in M13 is the precedent).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from projects.regex_agent.objective import _TASKS, RegexObjective, extract_pattern
from rsif.artifacts.store import ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.engine import EvolutionEngine
from rsif.llm.mock import ScriptedProvider, text_result
from rsif.objectives.base import Split

_REFERENCE = {
    key: ref for key, _pos, _neg, ref in _TASKS
}
_WRONG = "zzz"  # compiles, matches nothing: deterministic wrong answer


def _answer(key: str, ok: bool) -> str:
    pat = _REFERENCE[key] if ok else _WRONG
    return f"```python\n{pat}\n```"


def test_task_pack_reference_patterns_are_solvable():
    from rsif.sandbox.exec import run_python

    for key, positives, negatives, ref in _TASKS:
        program = (
            "import re\n"
            f"rx = re.compile({ref!r})\n"
            f"for s in {positives!r}: assert rx.search(s), ('missed', s)\n"
            f"for s in {negatives!r}: assert not rx.search(s), ('hit', s)\n"
        )
        out = run_python(program)
        assert out.ok, f"{key}: reference pattern {ref!r} fails its own task"


def test_extract_pattern_accepts_fenced_bare_and_quoted():
    assert extract_pattern("```python\na+\n```") == "a+"
    assert extract_pattern(r"\d{4}") == r"\d{4}"
    assert extract_pattern("'colou?r'") == "colou?r"
    assert extract_pattern("") == ""


def test_regex_project_improves_through_the_engine(tmp_path):
    cfg = RunConfig(generations=2, proposals_per_generation=1,
                    screen_tasks=6, seed=0)
    p = ScriptedProvider()

    train_ok = [True, True, True, False, False, False]  # 3/6 baseline ability
    canary_ok = [True, True]
    val_ability = [
        [False, False, True, False, False],   # baseline: 1/5
        [True, False, True, False, False],    # candidate 1: 2/5
        [True, True, True, True, True],       # candidate 2: 5/5
    ]
    keys = {s: [t.id for t in RegexObjective().suites()[Split(s)].tasks]
            for s in ("train", "canary", "val")}

    def block(suite, oks):
        for key, ok in zip(keys[suite], oks):
            p.add("agent", "", text_result(_answer(key, ok)))

    # baseline + two candidates, in exact consumption order
    for val_oks in val_ability:
        block("train", train_ok)
        block("canary", canary_ok)
        block("val", val_oks)
    p.add("improver", "", text_result(json.dumps({
        "surface": "prompt", "operator": "prompt/refine",
        "hypothesis": "enumerate positives and negatives before writing",
        "rationale": "misses come from untested negatives",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": "STRATEGY: enumerate examples"},
                 "edit_kind": "replace"}],
    })))
    p.add("improver", "", text_result(json.dumps({
        "surface": "prompt", "operator": "prompt/refine",
        "hypothesis": "verify the pattern against every example",
        "rationale": "level-2 strategy still fails structural tasks",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": "STRATEGY: enumerate + verify"},
                 "edit_kind": "replace"}],
    })))

    ws = RunWorkspace.init(tmp_path / "regex", cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    engine = EvolutionEngine(store=store, provider=p,
                             objective=RegexObjective(), cfg=cfg,
                             clock=lambda: 0.0)
    summary = engine.run()

    assert summary.accepted == 2 and summary.rejected == 0
    assert summary.best_fitness == 1.0
    assert store.active_version("prompt/system") == 3

    events = engine.events.read()
    val_scores = [e.payload["score"] for e in events
                  if e.kind == "eval" and e.payload.get("suite") == "val"]
    assert val_scores == [0.2, 0.4, 1.0]  # baseline -> accept -> accept
    accepts = [e for e in events if e.kind == "accept"]
    assert [a.payload["promoted"] for a in accepts] == [True, True]
    # grading really went through the sandbox: eval details exist on misses
    assert any(e.kind == "eval" for e in events)
