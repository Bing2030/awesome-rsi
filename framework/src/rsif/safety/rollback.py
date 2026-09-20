"""Auto-rollback: restore the active agent to a known-good archive snapshot.

Rollback never rewrites history: restoring an artifact appends a `restore`
lineage entry (DGM backtracking semantics [2505.22954]). Artifacts that did
not exist in the target snapshot are deactivated, not deleted.
"""

from __future__ import annotations

from rsif.artifacts.store import ApplyResult, ArtifactStore
from rsif.evolve.archive import Archive
from rsif.observe.events import PHASE_CORRECT, ROLLBACK, EventLog


def auto_rollback(store: ArtifactStore, archive: Archive, events: EventLog,
                  generation: int, reason: str) -> dict[str, int]:
    """Restore the checkout to the archive-best snapshot. Returns the mapping
    that is now active (artifact_id -> version)."""
    best = archive.best()
    if best is None:
        events.append(ROLLBACK, phase=PHASE_CORRECT, generation=generation,
                      action="auto_rollback", reason=reason, restored={},
                      note="archive empty; nothing to restore")
        return dict(store.checkout())

    target = best.spec_snapshot
    current = store.checkout()
    rid = f"rollback:{reason}"

    restored: dict[str, int] = {}
    for aid, version in sorted(target.items()):
        if current.get(aid) != version:
            store.restore(aid, version, proposal_id=rid, generation=generation)
            restored[aid] = version
    # artifacts created after the target snapshot: deactivate (v0), keep files
    extras = [aid for aid in current if aid not in target]
    if extras:
        for aid in extras:
            store.delete(aid, proposal_id=rid, generation=generation)  # lineage
        store.promote(ApplyResult({aid: 0 for aid in extras}),
                      proposal_id=rid, generation=generation)  # checkout
        for aid in extras:
            restored[aid] = 0

    events.append(ROLLBACK, phase=PHASE_CORRECT, generation=generation,
                  action="auto_rollback", reason=reason, restored=restored,
                  target_descriptor=list(best.descriptor),
                  target_fitness=best.fitness)
    return dict(store.checkout())
