"""M10 live smoke: the full loop against a real LLM (opt-in, ~$1 cap).

Run with:  ANTHROPIC_API_KEY=sk-...  uv run --extra anthropic pytest -m live

The point is *machinery under real-model noise*, not a guaranteed
improvement: we assert the loop drives a real provider through every phase,
stays inside its budget, and ends in a coherent state (an accepted+verified
change, or a correctly-rejected one — both are the system working).
"""

import os
import tempfile
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (os.environ.get("ANTHROPIC_API_KEY")
             or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
        reason="no Anthropic credentials (ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN)"),
]

MODEL = os.environ.get("RSIF_LIVE_MODEL", "claude-haiku-4-5-20251001")


def test_live_smoke_full_loop():
    pytest.importorskip("anthropic")

    from rsif.artifacts.store import ArtifactStore
    from rsif.artifacts.workspace import RunWorkspace
    from rsif.config import RunConfig
    from rsif.evolve.engine import EvolutionEngine
    from rsif.llm.factory import provider_from_config
    from rsif.objectives import objective_from_config
    from rsif.observe.events import EventLog

    with tempfile.TemporaryDirectory(prefix="rsif-live-") as td:
        root = Path(td)
        # hard caps: 1 generation x 1 proposal, <= 60 LLM calls, <= $1
        cfg = RunConfig(provider="anthropic", model=MODEL,
                        generations=1, proposals_per_generation=1,
                        screen_tasks=2, budget_llm_calls=60,
                        budget_usd=float(os.environ.get("RSIF_LIVE_USD", "1.0")),
                        seed=7)
        ws = RunWorkspace.init(root / "live", cfg.to_dict(), cfg.seed)
        store = ArtifactStore(ws, clock=lambda: 0.0)
        store.seed_defaults(cfg)
        provider = provider_from_config(cfg, cache=ws.cache_dir / "llm")
        engine = EvolutionEngine(store=store, provider=provider,
                                 objective=objective_from_config(cfg), cfg=cfg,
                                 clock=lambda: 0.0, approver=None)  # META fail-closed
        summary = engine.run()

        # the loop ran the real provider through every phase
        events = EventLog(ws.events_path, clock=lambda: 0.0).read()
        kinds = {e.kind for e in events}
        assert "run_start" in kinds and "run_end" in kinds
        assert "llm_call" in kinds
        assert "proposal" in kinds or summary.stop_reason == "budget:llm_calls"
        llm_calls = [e for e in events if e.kind == "llm_call"]
        assert len(llm_calls) <= 60  # budget held even if stop_reason is None

        # coherent end state: every proposal has a verdict
        accepts = sum(1 for e in events if e.kind == "accept")
        rejects = sum(1 for e in events if e.kind == "reject")
        assert accepts + rejects >= 1
        if accepts:
            # anything accepted passed the canary+val gates in order
            for pid in {e.payload["proposal_id"] for e in events
                        if e.kind == "accept"}:
                gates = [e.payload["gate"] for e in events
                         if e.kind == "gate" and e.payload["proposal_id"] == pid]
                assert "canary" in gates and "val" in gates
        # the archive best is a real, on-disk agent configuration
        assert summary.best_snapshot is not None
        for aid, version in store.checkout().items():
            assert store.version_dir(aid, version).exists()
