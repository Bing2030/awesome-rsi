"""M8 integration verification: budget abort, ratchet-proof acceptance,
stagnation gate - on the full engine loop."""

import json

from rsif.artifacts.store import ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.engine import EvolutionEngine
from rsif.llm.mock import ScriptedProvider, text_result
from rsif.safety.approvers import FakeApprover

from helpers import CORRECT as _CORRECT
from helpers import WRONG as _WRONG
from helpers import TinyObjective


def _run(tag, cfg, provider, approver=None, root=None):
    import pathlib
    import tempfile

    root = root or pathlib.Path(tempfile.mkdtemp())
    ws = RunWorkspace.init(root / tag, cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    engine = EvolutionEngine(store=store, provider=provider,
                             objective=TinyObjective(), cfg=cfg,
                             clock=lambda: 0.0, approver=approver)
    return ws, engine.run()


def _improver(prompt):
    return text_result(json.dumps({
        "surface": "prompt", "operator": "prompt/refine",
        "hypothesis": "improve the prompt", "rationale": "n/a",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": prompt}, "edit_kind": "replace"}],
    }))


def test_budget_exhaustion_aborts_cleanly(tmp_path):
    # baseline alone consumes exactly 5 LLM calls (2 train + 1 canary + 2 val)
    cfg = RunConfig(generations=2, proposals_per_generation=2,
                    screen_tasks=2, budget_llm_calls=5, seed=0)
    p = ScriptedProvider()
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))

    ws, summary = _run("budget", cfg, p, root=tmp_path)
    assert summary.stop_reason == "budget:llm_calls"
    assert summary.accepted == 0 and summary.rejected == 0
    # nothing from generation 1 ran except the budget event itself
    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    kinds = [(e.kind, e.generation) for e in events]
    assert kinds[-1] == ("run_end", 2)
    assert kinds[-2] == ("budget", 1)
    assert not any(e.kind == "proposal" for e in events)


def test_provider_error_aborts_cleanly(tmp_path):
    """A provider/connection error mid-run must abort cleanly (run_end +
    error event + stop_reason), never an unhandled traceback [M12 finding:
    a real gateway RateLimitError crashed cmd_evolve]."""
    from rsif.llm.base import LLMProvider

    class _Failing(LLMProvider):
        def complete(self, req):
            raise ConnectionError("gateway down")

    cfg = RunConfig(generations=2, proposals_per_generation=1,
                    screen_tasks=2, seed=0)
    ws, summary = _run("error", cfg, _Failing(), root=tmp_path)
    assert summary.stop_reason == "error:ConnectionError"
    assert summary.accepted == 0 and summary.rejected == 0

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    assert events[-1].kind == "run_end"
    assert events[-1].payload["stop_reason"] == "error:ConnectionError"
    assert any(e.kind == "error" and e.payload["error"] == "ConnectionError"
               for e in events)


def test_improver_provider_error_is_not_a_parse_reject(tmp_path):
    """M1 (review): a provider failure during the improver call is an
    infrastructure error, not a malformed proposal - it must abort the run,
    never burn proposals as fake 'parse' rejections."""
    from rsif.llm.base import CompletionRequest, CompletionResult, LLMProvider
    from rsif.llm.base import Usage

    class _FailsOnImprover(LLMProvider):
        def __init__(self):
            self.agent_calls = 0

        def complete(self, req):
            if req.role == "improver":
                raise ConnectionError("gateway down")
            self.agent_calls += 1
            return CompletionResult(text=_WRONG, usage=Usage(1, 1))

    cfg = RunConfig(generations=2, proposals_per_generation=1,
                    screen_tasks=2, seed=0)
    p = _FailsOnImprover()
    ws, summary = _run("improver_err", cfg, p, root=tmp_path)
    assert summary.stop_reason == "error:ConnectionError"

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    assert not [e for e in events if e.kind == "reject"]
    assert not [e for e in events if e.kind == "reflect"]


def test_budget_overshoot_bounded_to_one_call(tmp_path):
    """M5 (review): the pre-proposal budget check alone allows overshoot of a
    whole proposal; the per-call check aborts the moment a call pushes past
    the limit (mid-proposal, generation-attributed budget event)."""
    cfg = RunConfig(generations=2, proposals_per_generation=1,
                    screen_tasks=2, budget_llm_calls=6, seed=0)
    p = ScriptedProvider()
    # baseline: exactly 5 calls (2 train + 1 canary + 2 val)
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    # gen1 p1: improver call #6 (== limit, allowed), first screen agent call
    # #7 pushes past -> abort mid-proposal
    p.add("improver", "", _improver("over budget"))
    p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_WRONG))  # never consumed

    ws, summary = _run("overshoot", cfg, p, root=tmp_path)
    assert summary.stop_reason == "budget:llm_calls"
    assert summary.accepted == 0 and summary.rejected == 0

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    llm_calls = [e for e in events if e.kind == "llm_call"]
    assert len(llm_calls) == 7  # 5 baseline + improver + one overshoot call
    budget_events = [e for e in events if e.kind == "budget"]
    assert budget_events[0].generation == 1
    assert budget_events[0].payload["dimension"] == "llm_calls"
    assert events[-1].payload["stop_reason"] == "budget:llm_calls"


def test_two_level_acceptance_prevents_ratchet(tmp_path):
    """A candidate may beat its sampled (weak) parent - entering the archive
    as a stepping stone - without being allowed to replace the better ACTIVE
    agent. Deployed fitness can never ratchet down."""
    cfg = RunConfig(generations=1, proposals_per_generation=2,
                    screen_tasks=2, seed=0)
    p = ScriptedProvider()
    # baseline: train 0/2, canary 1/1, val 0/2 -> val 0.0
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    # p1 candidate: everything correct -> val 1.0, promoted
    for _ in range(5):
        p.add("agent", "", text_result(_CORRECT))
    # p2 candidate: train + canary correct, val 1/2 -> 0.5
    for _ in range(2):
        p.add("agent", "", text_result(_CORRECT))
    p.add("agent", "", text_result(_CORRECT))
    p.add("agent", "", text_result(_CORRECT))
    p.add("agent", "", text_result(_WRONG))
    p.add("improver", "", _improver("better prompt v2"))
    p.add("improver", "", _improver("mediocre prompt v3"))

    ws, summary = _run("ratchet", cfg, p, root=tmp_path)
    assert summary.accepted == 2 and summary.rejected == 0

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    accepts = [e for e in events if e.kind == "accept"]
    assert accepts[0].payload["promoted"] is True
    assert accepts[1].payload["promoted"] is False

    # the active checkout kept the STRONG candidate (v2), not the newer v3
    store = ArtifactStore(ws)
    assert store.active_version("prompt/system") == 2
    assert store.latest_version("prompt/system") == 3  # v3 exists, dormant
    archive = json.loads((ws.root / "archive.json").read_text())
    assert len(archive["cells"]) == 3  # seed + strong + stepping stone
    # drift check at generation end: active == best -> no alarm
    assert not [e for e in events if e.kind == "rollback"
                and e.payload.get("action") == "auto_rollback"]


def test_stagnation_alarm_stops_without_approval(tmp_path):
    cfg = RunConfig(generations=3, proposals_per_generation=1, screen_tasks=2,
                    seed=0)
    cfg.extra["stagnation_threshold"] = 2
    p = ScriptedProvider()
    # baseline: train 0, canary 1, val 0
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    # each generation's candidate: train ok, canary REGRESSES -> rejected
    for _ in range(3):
        p.add("agent", "", text_result(_CORRECT))
        p.add("agent", "", text_result(_CORRECT))
        p.add("agent", "", text_result(_WRONG))
        p.add("improver", "", _improver("yet another prompt"))
        p.add("reflect", "", text_result("canary regressed"))

    ws, summary = _run("stagnation_deny", cfg, p, approver=FakeApprover(False),
                       root=tmp_path)
    assert summary.stop_reason == "drift"
    assert summary.rejected == 2  # stopped after generation 2, gen 3 never ran

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    assert not [e for e in events if e.generation == 3 and e.kind == "proposal"]
    drift_approval = [e for e in events if e.kind == "approval"
                      and e.payload.get("action") == "drift"]
    assert drift_approval and drift_approval[0].payload["approved"] is False
    assert drift_approval[0].payload["alarms"] == ["stagnation"]


def test_stagnation_approval_continues(tmp_path):
    cfg = RunConfig(generations=3, proposals_per_generation=1, screen_tasks=2,
                    seed=0)
    cfg.extra["stagnation_threshold"] = 2
    p = ScriptedProvider()
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    for _ in range(3):
        p.add("agent", "", text_result(_CORRECT))
        p.add("agent", "", text_result(_CORRECT))
        p.add("agent", "", text_result(_WRONG))
        p.add("improver", "", _improver("yet another prompt"))
        p.add("reflect", "", text_result("canary regressed"))

    ws, summary = _run("stagnation_allow", cfg, p, approver=FakeApprover(True),
                       root=tmp_path)
    assert summary.stop_reason is None
    assert summary.rejected == 3  # all generations ran
