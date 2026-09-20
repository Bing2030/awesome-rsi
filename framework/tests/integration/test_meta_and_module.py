"""M7 verification: architecture surface (MODULE) + META recursion + scheduler.

- A module edit (reflect-then-retry) passes the full gate chain, actually
  changes the execution path (self-critique visible in the retry request),
  and lands in a distinct archive niche.
- A META edit (mutating the improver's own template) is gated behind an
  approver: denied -> fail-closed rejection; approved -> applied, and the
  NEXT generation's improver demonstrably runs the evolved template
  (self-reference proven).
"""

import io
import json

from rsif.artifacts.store import ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.engine import EvolutionEngine
from rsif.llm.base import extract_code_fence
from rsif.llm.mock import ScriptedProvider, text_result
from rsif.safety.approvers import CLIApprover, FakeApprover

from helpers import CORRECT as _CORRECT
from helpers import WRONG as _WRONG
from helpers import TinyObjective

RETRY_MODULE = '''\
"""Evolved architecture: attempt, self-critique, retry once, submit."""

from rsif.runtime.module_api import (
    Action,
    AgentModule,
    LLMAction,
    ModuleContext,
    ReflectAction,
    SubmitAction,
)


class Module(AgentModule):
    name = "retry-reflect"

    def step(self, ctx: ModuleContext) -> Action:
        if ctx.steps_used == 1:
            return LLMAction()
        if ctx.steps_used == 2:
            return ReflectAction("check boundary conditions")
        if ctx.steps_used == 3:
            return LLMAction()  # retry with the critique in context
        return SubmitAction()
'''

EVOLVED_TEMPLATE = """\
You are the EVOLVED-TEMPLATE-42 Improver. Propose ONE bounded change.

## Current agent
{checkout_summary}

## Archive frontier
{archive_summary}

## Recent lessons (reflections & insights)
{lessons}

## Available operators
{operators}

## Rules
- At most {max_ops} operations; prefer the smallest sufficient change.
- Cite the failure your change addresses.
- Answer with a single JSON object:
{{"surface": "...", "operator": "...", "hypothesis": "...",
  "rationale": "...", "ops": [ {op_schema} ]}}
"""


def _run(root, tag, cfg, provider, approver=None):
    ws = RunWorkspace.init(root / tag, cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    engine = EvolutionEngine(store=store, provider=provider,
                             objective=TinyObjective(), cfg=cfg,
                             clock=lambda: 0.0, approver=approver)
    return ws, engine.run(), provider


# -- module surface --------------------------------------------------------------


def test_module_edit_passes_gates_and_changes_execution(tmp_path):
    cfg = RunConfig(generations=1, proposals_per_generation=1,
                    screen_tasks=2, seed=0)
    p = ScriptedProvider()
    # baseline (default module, 1 call/task): train 0/2, canary 1/1, val 0/2
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    # candidate (retry module, 2 calls/task): first attempt wrong, retry right
    for _ in range(2):  # train
        p.add("agent", "", text_result(_WRONG))
        p.add("agent", "", text_result(_CORRECT))
    p.add("agent", "", text_result(_CORRECT))  # canary both calls correct
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):  # val: wrong then correct -> val 1.0
        p.add("agent", "", text_result(_WRONG))
        p.add("agent", "", text_result(_CORRECT))
    p.add("improver", "", text_result(json.dumps({
        "surface": "module", "operator": "module/edit",
        "hypothesis": "a reflect-then-retry step catches boundary mistakes",
        "rationale": "single-shot answers failed every boundary test",
        "ops": [{"op": "update", "artifact_id": "module/default",
                 "payload": {"module.py": RETRY_MODULE},
                 "edit_kind": "replace"}],
    })))

    ws, summary, _p = _run(tmp_path, "module", cfg, p)
    assert summary.accepted == 1 and summary.rejected == 0
    assert summary.best_descriptor == ("module", 4, 0)
    assert summary.best_fitness == 1.0

    # the evolved module is active and really drove the loop: every retry
    # request carries the self-critique message
    store = ArtifactStore(ws)
    assert store.active_version("module/default") == 2
    agent_calls = [c for c in p.calls if c.role == "agent"]
    retry_calls = [c for c in agent_calls
                   if any("[self-critique]" in m.content for m in c.messages)]
    assert len(retry_calls) == 5  # 2 train + 1 canary + 2 val retries
    # and the system prompt (evolvable PROMPT surface) is real request context
    assert all(c.messages[0].role == "system" for c in agent_calls)

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    gates = [e.payload["gate"] for e in events
             if e.kind == "gate" and e.payload["proposal_id"] == "g1p1"]
    assert gates == ["scan", "load", "canary", "val"]


def test_module_edit_rejected_when_new_code_does_not_load(tmp_path):
    cfg = RunConfig(generations=1, proposals_per_generation=1,
                    screen_tasks=2, seed=0)
    p = ScriptedProvider()
    for _ in range(2):
        p.add("agent", "", text_result(_CORRECT))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_CORRECT))
    p.add("improver", "", text_result(json.dumps({
        "surface": "module", "operator": "module/edit",
        "hypothesis": "broken module",
        "rationale": "n/a",
        "ops": [{"op": "update", "artifact_id": "module/default",
                 "payload": {"module.py": "import os\n"},  # forbidden import
                 "edit_kind": "replace"}],
    })))
    p.add("reflect", "", text_result("broken module rejected"))

    ws, summary, _p = _run(tmp_path, "broken", cfg, p)
    assert summary.accepted == 0 and summary.rejected == 1
    store = ArtifactStore(ws)
    assert store.active_version("module/default") == 1  # unchanged

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    rejects = [e for e in events if e.kind == "reject"]
    assert rejects[0].payload["reason"] in ("scan", "load")


# -- META surface: gated, recursive ------------------------------------------------


def _meta_run(tmp_path, tag, approver):
    cfg = RunConfig(generations=2, proposals_per_generation=1,
                    screen_tasks=2, meta_every_k=1, seed=0)
    p = ScriptedProvider()
    # baseline: train 0, canary 1, val 0
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    # gen1 candidate (template edit; default module): all correct -> accepted
    for _ in range(5):
        p.add("agent", "", text_result(_CORRECT))
    # gen2 candidate: all wrong -> rejected on val
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))  # canary held
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    # improver proposals: gen1 = META template mutation, gen2 = prompt tweak
    p.add("improver", "", text_result(json.dumps({
        "surface": "meta", "operator": "meta/mutate-improver",
        "hypothesis": "a terser improver template proposes smaller patches",
        "rationale": "recent patches were too broad",
        "ops": [{"op": "update", "artifact_id": "meta/improver-template",
                 "payload": {"template.md": EVOLVED_TEMPLATE},
                 "edit_kind": "replace"}],
    })))
    p.add("improver", "", text_result(json.dumps({
        "surface": "prompt", "operator": "prompt/refine",
        "hypothesis": "minor wording",
        "rationale": "n/a",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": "x"}, "edit_kind": "replace"}],
    })))
    p.add("reflect", "", text_result("gen2 candidate regressed"))
    return _run(tmp_path, tag, cfg, p, approver)  # (ws, summary, provider)


def test_meta_edit_approved_applies_and_next_gen_uses_it(tmp_path):
    approver = FakeApprover(allowed=True)
    ws, summary, p = _meta_run(tmp_path, "meta_ok", approver)

    assert approver.requests and approver.requests[0][0] == "g1p1"
    assert summary.accepted == 1  # the META edit itself
    store = ArtifactStore(ws)
    assert store.active_version("meta/improver-template") == 2

    # recursion: generation 2's improver call was formatted with the EVOLVED
    # template (the artifact the improver itself wrote in generation 1)
    improver_texts = ["".join(m.content for m in c.messages)
                      for c in p.calls if c.role == "improver"]
    assert "EVOLVED-TEMPLATE-42" not in improver_texts[0]
    assert "EVOLVED-TEMPLATE-42" in improver_texts[1]

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    approvals = [e for e in events if e.kind == "approval"]
    assert len(approvals) == 1 and approvals[0].payload["approved"] is True


def test_meta_edit_denied_fails_closed(tmp_path):
    approver = FakeApprover(allowed=False)
    cfg = RunConfig(generations=1, proposals_per_generation=1,
                    screen_tasks=2, meta_every_k=1, seed=0)
    p = ScriptedProvider()
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("improver", "", text_result(json.dumps({
        "surface": "meta", "operator": "meta/mutate-improver",
        "hypothesis": "unapproved self-edit",
        "rationale": "n/a",
        "ops": [{"op": "update", "artifact_id": "meta/improver-template",
                 "payload": {"template.md": EVOLVED_TEMPLATE},
                 "edit_kind": "replace"}],
    })))
    p.add("reflect", "", text_result("denied"))

    ws, summary, _p = _run(tmp_path, "meta_deny", cfg, p, approver)
    assert summary.accepted == 0 and summary.rejected == 1
    store = ArtifactStore(ws)
    assert store.active_version("meta/improver-template") == 1  # untouched
    assert json.loads(ws.checkout_path.read_text())["meta/improver-template"] == 1

    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    approvals = [e for e in events if e.kind == "approval"]
    assert approvals[0].payload["approved"] is False
    assert [e.payload["reason"] for e in events if e.kind == "reject"] == ["approval"]


def test_meta_surface_closed_outside_slow_loop(tmp_path):
    cfg = RunConfig(generations=1, proposals_per_generation=1,
                    screen_tasks=2, meta_every_k=3, seed=0)  # gen 1: META closed
    p = ScriptedProvider()
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("agent", "", text_result(_CORRECT))
    for _ in range(2):
        p.add("agent", "", text_result(_WRONG))
    p.add("improver", "", text_result(json.dumps({
        "surface": "meta", "operator": "meta/mutate-improver",
        "hypothesis": "out of cadence",
        "rationale": "n/a",
        "ops": [{"op": "update", "artifact_id": "meta/improver-template",
                 "payload": {"template.md": EVOLVED_TEMPLATE},
                 "edit_kind": "replace"}],
    })))
    p.add("reflect", "", text_result("wrong cadence"))

    ws, summary, _p = _run(tmp_path, "closed", cfg, p, FakeApprover(True))
    assert summary.rejected == 1
    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    assert [e.payload["reason"] for e in events if e.kind == "reject"] == ["surface"]
    # no approval was even requested: the scheduler closed the surface first
    assert not [e for e in events if e.kind == "approval"]


def test_cli_approver_interactive():
    a = CLIApprover(stream_in=io.StringIO("y\n"), stream_out=io.StringIO())
    assert a.approve("p1", "meta edit") is True
    b = CLIApprover(stream_in=io.StringIO("n\n"), stream_out=io.StringIO())
    assert b.approve("p2", "meta edit") is False
    c = CLIApprover(stream_in=io.StringIO(""), stream_out=io.StringIO())
    assert c.approve("p3", "meta edit") is False  # EOF denies
