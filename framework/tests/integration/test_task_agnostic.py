"""M11 verification: the engine is task-agnostic.

The SAME EvolutionEngine (store, archive, safety, scheduler, runtime) drives
three objectives to improvement with zero engine changes:

1. code-tasks    (sandbox hidden tests)         - covered by the flagship test
2. exact-match   (plain-text equality)          - full loop via DemoProvider
3. arithmetic    (examples/custom_objective.py) - full loop via a FIFO
                                                  ScriptedProvider

The proof is behavioral: each objective is a distinct evaluation surface
(code fences vs. bare text vs. integer strings) and each improves on
held-out val through the identical evolve path. Nothing objective-specific
lives in `rsif/evolve/` - the engine receives an `Objective` instance and
never imports a concrete class.
"""

import importlib.util
import json
from pathlib import Path

from rsif.artifacts.store import ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.engine import EvolutionEngine
from rsif.llm.mock import ScriptedProvider, text_result
from rsif.objectives.base import Split
from rsif.objectives.exact_match import ExactMatchObjective
from rsif.observe.events import EventLog

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _load_custom_objective():
    """Load examples/custom_objective.py exactly as a user would plug it in."""
    spec = importlib.util.spec_from_file_location(
        "custom_objective", EXAMPLES / "custom_objective.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ArithmeticObjective


def _baseline_val(events):
    return next(e.payload["score"] for e in events
                if e.kind == "eval" and e.payload.get("label") == "baseline"
                and e.payload["suite"] == "val")


def test_exact_match_objective_improves(tmp_path):
    """A plain-text Q&A objective improves 1/6 -> 1.0 through the same loop
    (6-task val suite: each accept clears the paired net-gain floor)."""
    from rsif.llm.demo import DemoProvider

    cfg = RunConfig(generations=2, proposals_per_generation=1,
                    screen_tasks=2, seed=0)
    ws = RunWorkspace.init(tmp_path / "qa", cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    engine = EvolutionEngine(store=store, provider=DemoProvider("exact-match"),
                             objective=ExactMatchObjective(), cfg=cfg,
                             clock=lambda: 0.0)
    summary = engine.run()

    assert summary.accepted == 2 and summary.rejected == 0
    assert summary.best_fitness == 1.0
    assert summary.best_descriptor == ("prompt", 4, 0)

    # the improvement is real: baseline val 1/6, final val 6/6
    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    assert _baseline_val(events) == 1 / 6
    accepts = [e for e in events if e.kind == "accept"]
    assert [round(a.payload["val_child"], 4) for a in accepts] == \
        [round(2 / 6, 4), 1.0]
    assert [a.payload["promoted"] for a in accepts] == [True, True]

    # the same five phases the flagship asserts, on a non-code objective
    phases = {e.phase for e in events if e.phase}
    assert phases == {"proposal", "exploration", "design",
                      "verification", "correction"}


def test_custom_arithmetic_objective_improves(tmp_path):
    """The user's own examples/custom_objective.py improves via the same engine.

    Loaded from its file path (importlib), never imported by the engine. A
    FIFO ScriptedProvider supplies bare integer answers - no code fence, no
    sandbox - proving the runtime + objective + engine are fully decoupled
    from the code-tasks task shape.
    """
    ArithmeticObjective = _load_custom_objective()

    obj = ArithmeticObjective()
    suites = obj.suites()
    train = suites[Split.TRAIN].tasks    # 4 tasks
    canary = suites[Split.CANARY].tasks  # 1 task
    val = suites[Split.VAL].tasks        # 3 tasks

    p = ScriptedProvider()

    def block(tasks, n_correct):
        for i, t in enumerate(tasks):
            p.add("agent", "",
                  text_result(t.meta["answer"] if i < n_correct else "0"))

    # baseline: train 2/4, canary 1/1, val 1/3 -> 0.333
    block(train, 2)
    block(canary, 1)
    block(val, 1)
    # candidate A: train 3/4, canary 1/1, val 3/3 -> 1.0 ACCEPT
    block(train, 3)
    block(canary, 1)
    block(val, 3)
    p.add("improver", "", text_result(json.dumps({
        "surface": "prompt", "operator": "prompt/refine",
        "hypothesis": "carry-digit discipline improves arithmetic accuracy",
        "rationale": "baseline fails carry operations",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": "Solve arithmetic carefully, carry digits."},
                 "edit_kind": "replace"}],
    })))

    cfg = RunConfig(generations=1, proposals_per_generation=1,
                    screen_tasks=4, seed=0)  # screen == full train (memoized)
    ws = RunWorkspace.init(tmp_path / "arith", cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    engine = EvolutionEngine(store=store, provider=p, objective=obj,
                             cfg=cfg, clock=lambda: 0.0)
    summary = engine.run()

    assert summary.accepted == 1 and summary.rejected == 0
    assert summary.best_fitness == 1.0
    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    assert _baseline_val(events) == 1 / 3


def test_engine_has_no_concrete_objective_dependency():
    """Structural guard: the engine/evolve package never imports a concrete
    objective class - the seam is enforced in code, not just by convention."""
    import rsif.evolve.engine as engine_mod
    import inspect

    src = inspect.getsource(engine_mod)
    for name in ("CodeTasksObjective", "ExactMatchObjective", "ArithmeticObjective"):
        assert name not in src, f"engine leaked a concrete objective: {name}"
