"""Harness-efficiency verification (offline, deterministic): the
harness_efficiency project improves through the identical engine with zero
engine changes, and the cost-aware objective makes the gates prefer a
*concise* correct answer over an equally-correct verbose one — while still
rejecting a concise wrong answer.

This is the proof that a token-efficiency objective needs no new gate: the
scalar quality-first floor rides the existing threshold + paired net-gain
floor (M13), because cost is folded into the per-task score.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from projects.harness_efficiency.objective import (
    EfficiencyObjective,
    _TASKS,
    extract_answer,
)
from rsif.artifacts.model import ArtifactType
from rsif.artifacts.store import ApplyResult, ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.assembler import build_spec
from rsif.evolve.engine import EvolutionEngine
from rsif.llm.mock import ScriptedProvider, text_result
from rsif.objectives.base import Split

_TARGET = {key: target for key, target in _TASKS}

# ~1170 chars -> out_tokens = 292, total = 293 -> normalized cost clamps to 1.0
_VERBOSE = "Let me think through this step by step. " * 30


def _verbose(key: str) -> str:
    return _VERBOSE + f"ANSWER: {_TARGET[key]}"


def _concise(key: str) -> str:
    return f"ANSWER: {_TARGET[key]}"


def _wrong(key: str) -> str:
    return "ANSWER: zzz"


def test_extract_answer_marker_and_fallback():
    assert extract_answer("ANSWER: 42") == "42"
    assert extract_answer("reasoning\nANSWER: 42") == "42"
    assert extract_answer("ANSWER: 42\nmore") == "42"
    assert extract_answer("no marker here") == "no marker here"
    assert extract_answer("") == ""


def test_task_pack_answers_are_extractable():
    # the echo pack's solvability invariant: both answer styles must extract
    # to the target (a bad task/marker could otherwise silently poison scores).
    for key in _TARGET:
        assert extract_answer(_concise(key)) == _TARGET[key]
        assert extract_answer(_verbose(key)) == _TARGET[key]


def test_efficiency_objective_prefers_concise_over_verbose(tmp_path):
    cfg = RunConfig(generations=2, proposals_per_generation=1,
                    screen_tasks=4, seed=0)
    p = ScriptedProvider()

    keys = {s: [t.id for t in EfficiencyObjective().suites()[Split(s)].tasks]
            for s in ("train", "canary", "val")}

    def block(suite, make):
        for key in keys[suite]:
            p.add("agent", "", text_result(make(key)))

    # baseline (verbose correct) -> candidate 1 (concise correct) ->
    # candidate 2 (concise wrong), in exact consumption order.
    for make in (_verbose, _concise, _wrong):
        block("train", make)
        block("canary", make)
        block("val", make)

    # two improver proposals (the behavior is driven by the scripted agent
    # answers above; these only have to parse into valid prompt patches).
    p.add("improver", "", text_result(json.dumps({
        "surface": "prompt", "operator": "prompt/refine",
        "hypothesis": "answer concisely",
        "rationale": "cost-aware fitness rewards shorter answers",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": "STRATEGY: concise"},
                 "edit_kind": "replace"}],
    })))
    p.add("improver", "", text_result(json.dumps({
        "surface": "prompt", "operator": "prompt/refine",
        "hypothesis": "emit a wrong answer",
        "rationale": "experiment",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": "STRATEGY: wrong"},
                 "edit_kind": "replace"}],
    })))

    ws = RunWorkspace.init(tmp_path / "eff", cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    engine = EvolutionEngine(store=store, provider=p,
                             objective=EfficiencyObjective(), cfg=cfg,
                             clock=lambda: 0.0)
    summary = engine.run()

    # concise-correct accepted + promoted; concise-wrong rejected at the
    # cheap cascade screen (its train score is ~-0.01, far below any parent).
    assert summary.accepted == 1 and summary.rejected == 1
    assert summary.best_fitness > 0.95  # the concise candidate (~0.97)

    events = engine.events.read()
    val_scores = [e.payload["score"] for e in events
                  if e.kind == "eval" and e.payload.get("suite") == "val"]
    # baseline + the one accepted candidate (the wrong one never reached val)
    assert len(val_scores) == 2
    # cost = (input context + output tokens)/budget. The two candidates share
    # the same context, so the only difference is output length: verbose
    # (~1200 chars) is cost-heavy (~0.91), concise (~11 chars) is near-free
    # (~0.97). Bounds are wide so unrelated prompt/memory edits don't break
    # the test; the *relative* claim is the point.
    assert 0.85 < val_scores[0] < 0.95
    assert val_scores[1] > 0.95
    assert val_scores[1] - val_scores[0] > 0.02  # cleared the val threshold

    accepts = [e for e in events if e.kind == "accept"]
    assert len(accepts) == 1
    assert accepts[0].payload["promoted"] is True


def test_context_policy_bounds_injected_memory(tmp_path):
    """The evolvable POLICY artifact actually truncates the injected memory."""
    cfg = RunConfig(objective="efficiency")
    ws = RunWorkspace.init(tmp_path / "polunit", cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    store.create("memory/big", ArtifactType.MEMORY, {"lessons.md": "x" * 2000})
    store.promote(ApplyResult({"memory/big": 1}))

    # the generous default cap (4000) leaves the big memory intact
    spec_full = build_spec(store, store.snapshot())
    assert len(spec_full.memory) > 1000

    # tightening the policy truncates the assembled memory
    store.update("policy/context", {"policy.json": '{"max_memory_chars": 120}'})
    store.promote(ApplyResult({"policy/context": 2}))
    spec_tight = build_spec(store, store.snapshot())
    assert 0 < len(spec_tight.memory) <= 120


def test_context_policy_tightening_is_accepted(tmp_path):
    """A POLICY edit that cuts context (same correctness) is accepted by the
    cost-aware objective — the same scalar floor rewards context compaction."""
    cfg = RunConfig(generations=1, proposals_per_generation=1,
                    screen_tasks=4, seed=0)
    ws = RunWorkspace.init(tmp_path / "pol", cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    # baseline carries a large, non-load-bearing memory: context is expensive
    store.create("memory/big", ArtifactType.MEMORY, {"lessons.md": "x" * 2000})
    store.promote(ApplyResult({"memory/big": 1}))

    p = ScriptedProvider()
    keys = {s: [t.id for t in EfficiencyObjective().suites()[Split(s)].tasks]
            for s in ("train", "canary", "val")}

    def block(suite):
        for key in keys[suite]:
            p.add("agent", "", text_result(_concise(key)))

    # baseline + one candidate, both concise-correct: only the context differs
    for _ in (0, 1):
        block("train")
        block("canary")
        block("val")

    p.add("improver", "", text_result(json.dumps({
        "surface": "policy", "operator": "policy/bound-context",
        "hypothesis": "inject less memory, cut context cost",
        "rationale": "memory is not load-bearing for this echo task",
        "ops": [{"op": "update", "artifact_id": "policy/context",
                 "payload": {"policy.json": '{"max_memory_chars": 100}'},
                 "edit_kind": "replace"}],
    })))

    engine = EvolutionEngine(store=store, provider=p,
                             objective=EfficiencyObjective(), cfg=cfg,
                             clock=lambda: 0.0)
    summary = engine.run()

    assert summary.accepted == 1 and summary.rejected == 0
    assert store.active_version("policy/context") == 2  # the policy advanced

    events = engine.events.read()
    val_scores = [e.payload["score"] for e in events
                  if e.kind == "eval" and e.payload.get("suite") == "val"]
    assert len(val_scores) == 2
    # context compaction raised the score past the val threshold
    assert val_scores[1] - val_scores[0] > 0.02

