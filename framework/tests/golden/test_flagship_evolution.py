"""M6 flagship verification: a deterministic full-loop evolution run.

Proposal A (prompt refine) improves val -> accepted, promoted, archived.
Proposal B regresses on val -> rejected, candidate discarded (rollback event),
reflected into episodic memory; checkout keeps A.

The entire run is byte-reproducible from the seed: rerunning into a fresh
workspace yields identical events.jsonl / archive.json / checkout.json /
lineage.jsonl bytes, equal to the committed golden events log.

Regenerate the golden with: RSIF_UPDATE_GOLDEN=1 pytest tests/golden -k flagship
"""

import json
import os
from pathlib import Path

from rsif.artifacts.store import ArtifactStore
from rsif.artifacts.workspace import RunWorkspace
from rsif.config import RunConfig
from rsif.evolve.engine import EvolutionEngine
from rsif.llm.mock import ScriptedProvider, text_result
from rsif.objectives.base import Split
from rsif.objectives.code_tasks import CodeTasksObjective

GOLDEN = Path(__file__).parent / "golden_events.jsonl"

A_PROMPT = (
    "You are a careful Python-solving agent. Read the task, think, and answer "
    "with a single ```python code block implementing the requested function "
    "exactly (signature and name as specified). Prefer simple, correct, "
    "dependency-free code. The block must be self-contained: only stdlib "
    "imports.\nBefore answering, check boundary conditions: empty inputs, "
    "zero, single elements, and negatives."
)
B_PROMPT = (
    "You are a fast Python-solving agent. Answer immediately with a "
    "```python code block; speed matters more than edge cases."
)

_SOLUTIONS = {
    "add": "def add(a, b):\n    return a + b\n",
    "is_even": "def is_even(n):\n    return n % 2 == 0\n",
    "reverse": "def reverse(s):\n    return s[::-1]\n",
    "max_of": "def max_of(a, b):\n    return a if a >= b else b\n",
    "factorial": ("def factorial(n):\n    r = 1\n"
                  "    for i in range(1, n + 1):\n        r *= i\n    return r\n"),
    "count_vowels": ("def count_vowels(s):\n"
                     "    return sum(1 for c in s.lower() if c in 'aeiou')\n"),
    "is_palindrome": ("def is_palindrome(s):\n    t = s.replace(' ', '').lower()\n"
                      "    return t == t[::-1]\n"),
    "fib": ("def fib(n):\n    a, b = 0, 1\n"
            "    for _ in range(n):\n        a, b = b, a + b\n    return a\n"),
    "sum_list": "def sum_list(xs):\n    return sum(xs)\n",
    "gcd": ("def gcd(a, b):\n    while b:\n        a, b = b, a % b\n"
            "    return a\n"),
    "flatten": "def flatten(xs):\n    return [x for sub in xs for x in sub]\n",
    "is_prime": ("def is_prime(n):\n    if n < 2:\n        return False\n"
                 "    i = 2\n    while i * i <= n:\n"
                 "        if n % i == 0:\n            return False\n"
                 "        i += 1\n    return True\n"),
    "longest": "def longest(words):\n    return max(words, key=len)\n",
}


def _answer(task, ok: bool):
    fn = task.meta["function_name"]
    if ok:
        code = _SOLUTIONS[fn]
    else:
        code = f"def {fn}(*args):\n    return None\n"
    return text_result(f"```python\n{code}\n```")


def _improver_json(operator: str, hypothesis: str, prompt: str) -> str:
    return json.dumps({
        "surface": "prompt", "operator": operator,
        "hypothesis": hypothesis,
        "rationale": "observed failures concentrate on boundary conditions",
        "ops": [{"op": "update", "artifact_id": "prompt/system",
                 "payload": {"system.md": prompt}, "edit_kind": "replace"}],
    })


def _scripted_provider(obj: CodeTasksObjective) -> ScriptedProvider:
    """Strict-FIFO script: the engine's evaluation order is deterministic,
    so per-role queues (matched by the empty substring = always) encode
    exactly which answers each candidate gets."""
    p = ScriptedProvider()
    suites = obj.suites()
    train = suites[Split.TRAIN].tasks      # 8 tasks, sorted-file order
    canary = suites[Split.CANARY].tasks    # 3 tasks
    val = suites[Split.VAL].tasks          # 5 tasks

    def block(tasks, n_correct):
        for i, t in enumerate(tasks):
            p.add("agent", "", _answer(t, i < n_correct))

    # baseline: train 3/8, canary 3/3, val 2/5 -> val fitness 0.40
    block(train, 3)
    block(canary, 3)
    block(val, 2)
    # candidate A: train 5/8 (screen pass), canary 3/3, val 4/5 -> 0.80 ACCEPT
    block(train, 5)
    block(canary, 3)
    block(val, 4)
    # candidate B: train 4/8 (screen pass), canary 3/3, val 2/5 -> REJECT on val
    block(train, 4)
    block(canary, 3)
    block(val, 2)

    # improver: A then B (FIFO)
    p.add("improver", "", text_result(_improver_json(
        "prompt/refine",
        "Adding an edge-case checklist to the system prompt improves "
        "boundary-condition correctness", A_PROMPT)))
    p.add("improver", "", text_result(_improver_json(
        "prompt/refine",
        "A shorter, speed-first prompt reduces overthinking", B_PROMPT)))
    # reflection on B's rejection
    p.add("reflect", "", text_result(
        "B regressed on val: shorter prompt lost boundary-condition checks. "
        "Next time keep the checklist and refine wording instead."))
    return p


def _run_once(root: Path, tag: str):
    cfg = RunConfig(generations=1, proposals_per_generation=2,
                    screen_tasks=8, seed=0)
    ws = RunWorkspace.init(root / tag, cfg.to_dict(), cfg.seed)
    store = ArtifactStore(ws, clock=lambda: 0.0)
    store.seed_defaults(cfg)
    obj = CodeTasksObjective()
    engine = EvolutionEngine(store=store, provider=_scripted_provider(obj),
                             objective=obj, cfg=cfg, clock=lambda: 0.0)
    summary = engine.run()
    return ws, summary


def test_flagship_loop(tmp_path):
    ws, summary = _run_once(tmp_path, "run")

    # -- outcomes: A accepted, B rejected ------------------------------------
    assert summary.accepted == 1 and summary.rejected == 1
    assert summary.best_fitness == 0.8
    assert summary.best_descriptor == ("prompt", 3, 0)
    assert len(summary.best_snapshot) == 5  # all seed artifacts

    # checkout: A promoted (v2); B's v3 exists but stays dormant
    checkout = json.loads(ws.checkout_path.read_text())
    assert checkout["prompt/system"] == 2
    store = ArtifactStore(ws)
    assert store.read_active("prompt/system")["system.md"] == A_PROMPT
    assert store.latest_version("prompt/system") == 3  # B's candidate exists
    assert [e.op for e in store.lineage("prompt/system")] == \
        ["create", "update", "update"]

    # -- memory: rejection -> reflection; acceptance -> insight ---------------
    from rsif.memory.episodic import ReflectionStore
    from rsif.memory.insights import InsightStore

    reflections = ReflectionStore(ws.memory_dir / "reflections.jsonl")
    assert len(reflections) == 1
    assert reflections.all()[0].source == "g1p2"
    assert "regressed" in reflections.all()[0].text
    insights = InsightStore(ws.memory_dir / "insights.jsonl")
    assert len(insights) == 1
    assert insights.all()[0].provenance == ["g1p1"]

    # -- archive: root + A, A best --------------------------------------------
    archive = json.loads((ws.root / "archive.json").read_text())
    assert len(archive["cells"]) == 2
    assert max(c["fitness"] for c in archive["cells"]) == 0.8

    # -- events: structure of the five phases ---------------------------------
    from rsif.observe.events import EventLog

    events = EventLog(ws.events_path, clock=lambda: 0.0).read()
    kinds = [e.kind for e in events]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"

    accepts = [e for e in events if e.kind == "accept"]
    rejects = [e for e in events if e.kind == "reject"]
    rollbacks = [e for e in events if e.kind == "rollback"]
    assert len(accepts) == 1 and accepts[0].payload["proposal_id"] == "g1p1"
    assert len(rejects) == 1
    assert rejects[0].payload["proposal_id"] == "g1p2"
    assert rejects[0].payload["reason"] == "val"
    assert len(rollbacks) == 1
    assert rollbacks[0].payload["action"] == "discard_candidate"

    phases = {e.phase for e in events if e.phase}
    assert phases == {"proposal", "exploration", "design",
                      "verification", "correction"}

    # per-proposal phase ordering is monotone through the loop
    for pid in ("g1p1", "g1p2"):
        order = [e.phase for e in events
                 if e.phase and e.payload.get("proposal_id") == pid]
        rank = {"proposal": 0, "design": 1, "exploration": 2,
                "verification": 3, "correction": 4}
        ranks = [rank[p] for p in order]
        assert ranks == sorted(ranks), (pid, order)

    # gates all ran in order for the accepted proposal
    gates = [e.payload["gate"] for e in events
             if e.kind == "gate" and e.payload["proposal_id"] == "g1p1"]
    assert gates == ["scan", "canary", "val"]
    val_gate = [e for e in events if e.kind == "gate"
                and e.payload["gate"] == "val"]
    assert val_gate[0].payload["passed"] is True
    assert val_gate[1].payload["passed"] is False

    run_end = events[-1]
    assert run_end.payload["best_fitness"] == 0.8

    # -- determinism: rerun in a fresh workspace -> byte-identical artifacts --
    ws2, summary2 = _run_once(tmp_path, "run2")
    assert summary2.to_dict() == summary.to_dict()
    for name in ("events.jsonl", "archive.json", "checkout.json",
                 "lineage.jsonl"):
        assert (ws.root / name).read_bytes() == (ws2.root / name).read_bytes(), name

    # -- golden events log -----------------------------------------------------
    events_bytes = ws.events_path.read_bytes()
    if not GOLDEN.exists() or os.environ.get("RSIF_UPDATE_GOLDEN"):
        GOLDEN.write_bytes(events_bytes)
    assert events_bytes == GOLDEN.read_bytes()
