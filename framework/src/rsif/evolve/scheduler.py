"""Fast/slow loop scheduler.

Fast loop: task-surface artifacts (prompt, skill, memory, module) are open
for proposal every generation. Slow loop: META artifacts - the improver's own
templates and operator catalog - open only every k-th generation, under
approval. This two-cadence design keeps meta-changes rare and reviewable
while task-level improvement runs continuously.

Grounding: MetaSkill-Evolve fast/slow loops [arXiv 2607.05297]; Promptbreeder
mutates mutation prompts on a slower, guarded cadence [arXiv 2309.16797].
"""

from __future__ import annotations

from dataclasses import dataclass, field

FAST_SURFACES = frozenset({"prompt", "skill", "memory", "module"})
META_SURFACE = "meta"


@dataclass(frozen=True)
class Schedule:
    generation: int
    open_surfaces: frozenset[str]
    meta_open: bool = field(default=False)

    def is_open(self, surface: str) -> bool:
        return surface in self.open_surfaces


def schedule_for(generation: int, meta_every_k: int) -> Schedule:
    """Schedule for one generation (generation >= 1; 0 is the baseline)."""
    if generation < 1:
        return Schedule(generation, FAST_SURFACES)
    meta_open = meta_every_k > 0 and generation % meta_every_k == 0
    surfaces = FAST_SURFACES | ({META_SURFACE} if meta_open else set())
    return Schedule(generation, frozenset(surfaces), meta_open)
