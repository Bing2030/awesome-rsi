"""M8 unit verification: budget, drift monitor, auto-rollback."""

from rsif.artifacts.model import ArtifactType
from rsif.artifacts.store import ApplyResult, ArtifactStore
from rsif.config import RunConfig
from rsif.evolve.archive import Archive, Individual
from rsif.observe.events import EventLog
from rsif.safety.budget import Budget
from rsif.safety.drift import DriftMonitor
from rsif.safety.rollback import auto_rollback


def test_budget_llm_calls_dimension():
    b = Budget(max_llm_calls=3, max_usd=100.0, max_wall_s=100.0,
               clock=lambda: 0.0)
    assert b.exhausted() is None
    b.record(10, 10)
    b.record(10, 10)
    assert b.exhausted() is None
    b.record(10, 10)
    assert b.exhausted() == "llm_calls"
    assert b.snapshot()["llm_calls"] == 3


def test_budget_usd_estimated_from_prices():
    b = Budget(max_llm_calls=100, max_usd=0.001, max_wall_s=100.0,
               price_per_mtok_in=3.0, price_per_mtok_out=15.0,
               clock=lambda: 0.0)
    # 1k in + 1k out = 3e-3 + 15e-3 = 0.018 USD -> over
    b.record(1000, 1000)
    assert b.exhausted() == "usd"


def test_budget_wall_clock():
    t = [0.0]
    b = Budget(max_llm_calls=100, max_usd=1.0, max_wall_s=10.0,
               clock=lambda: t[0])
    t[0] = 5.0
    assert b.exhausted() is None
    t[0] = 11.0
    assert b.exhausted() == "wall_clock"


def test_drift_monitor_alarms():
    m = DriftMonitor(baseline_canary=1.0, stagnation_threshold=3)
    ok = m.check(active_val=0.8, active_canary=1.0, best_val=0.8,
                 consecutive_rejections=1)
    assert ok.alarms == []
    regressed = m.check(active_val=0.5, active_canary=0.5, best_val=0.8,
                        consecutive_rejections=1)
    assert regressed.rollback_alarm
    assert set(regressed.alarms) == {"active_regression", "canary_regression"}
    stuck = m.check(active_val=0.8, active_canary=1.0, best_val=0.8,
                    consecutive_rejections=3)
    assert stuck.alarms == ["stagnation"] and not stuck.rollback_alarm


def test_auto_rollback_restores_best_snapshot(ws, store, fixed_clock):
    store.seed_defaults(RunConfig())
    root_snapshot = store.snapshot()

    archive = Archive()
    archive.add(Individual(descriptor=("seed",), fitness=0.4, val_score=0.4,
                           spec_snapshot=dict(root_snapshot), generation=0))
    # the active agent drifted: prompt updated to a worse v2 + promoted
    store.update("prompt/system", {"system.md": "drifted"}, proposal_id="p1")
    store.promote(ApplyResult({"prompt/system": 2}), proposal_id="p1")
    assert store.active_version("prompt/system") == 2

    events = EventLog(ws.events_path, clock=fixed_clock)
    auto_rollback(store, archive, events, generation=3, reason="canary_regression")

    assert store.active_version("prompt/system") == 1  # restored
    assert store.checkout() == root_snapshot
    # history is append-only: restore is a NEW lineage entry, v2 still exists
    ops = [e.op for e in store.lineage("prompt/system")]
    assert ops == ["create", "update", "restore"]
    assert store.version_dir("prompt/system", 2).exists()
    # and the rollback was logged
    rollbacks = [e for e in events.read() if e.kind == "rollback"]
    assert rollbacks[0].payload["action"] == "auto_rollback"
    assert rollbacks[0].payload["restored"] == {"prompt/system": 1}


def test_auto_rollback_deactivates_extra_artifacts(ws, store, fixed_clock):
    from rsif.config import RunConfig

    store.seed_defaults(RunConfig())
    root_snapshot = store.snapshot()
    archive = Archive()
    archive.add(Individual(descriptor=("seed",), fitness=0.4, val_score=0.4,
                           spec_snapshot=dict(root_snapshot), generation=0))

    # an artifact created after the target snapshot is active now
    store.create("skill/extra", ArtifactType.SKILL,
                 {"module.py": "def main():\n    return 1\n"}, proposal_id="p2")
    store.promote(ApplyResult({"skill/extra": 1}), proposal_id="p2")
    assert "skill/extra" in store.checkout()

    events = EventLog(ws.events_path, clock=fixed_clock)
    auto_rollback(store, archive, events, generation=4, reason="active_regression")

    assert "skill/extra" not in store.checkout()  # deactivated
    assert store.version_dir("skill/extra", 1).exists()  # files kept
    assert store.lineage("skill/extra")[-1].op == "delete"
