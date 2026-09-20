"""MAP-Elites archive with backtracking.

A quality-diversity grid keyed by behavior descriptors: keep the best
individual found in every niche, so search illuminates the space instead of
collapsing to one lineage. Individuals carry ancestor pointers for
backtracking when a lineage regresses.

Grounding: MAP-Elites [arXiv 1504.04909]; QD objective
[frontiers-quality-diversity-2016]; DGM archive + backtracking [2505.22954].
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Individual:
    descriptor: tuple
    fitness: float
    val_score: float
    spec_snapshot: dict  # artifact_id -> version
    generation: int
    proposal_id: str = ""
    parent_ref: tuple | None = None
    cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "descriptor": list(self.descriptor),
            "fitness": self.fitness,
            "val_score": self.val_score,
            "spec_snapshot": self.spec_snapshot,
            "generation": self.generation,
            "proposal_id": self.proposal_id,
            "parent_ref": list(self.parent_ref) if self.parent_ref else None,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Individual":
        return cls(
            descriptor=tuple(d["descriptor"]),
            fitness=d["fitness"], val_score=d["val_score"],
            spec_snapshot=d["spec_snapshot"], generation=d["generation"],
            proposal_id=d.get("proposal_id", ""),
            parent_ref=tuple(d["parent_ref"]) if d.get("parent_ref") else None,
            cost=d.get("cost", 0.0),
        )


class Archive:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self._cells: dict[tuple, Individual] = {}
        self._history: list[Individual] = []
        if self.path and self.path.exists():
            self._load()

    # -- insert ---------------------------------------------------------------

    def add(self, ind: Individual) -> bool:
        """Elitist replacement: keep `ind` iff it improves its niche.

        Returns True if it was stored (new niche or better fitness; ties
        broken by lower cost [AlphaEvolve 2506.13131]).
        """
        existing = self._cells.get(ind.descriptor)
        if existing is None:
            self._cells[ind.descriptor] = ind
            self._history.append(ind)
            return True
        if (ind.fitness, -ind.cost) > (existing.fitness, -existing.cost):
            self._cells[ind.descriptor] = ind
            self._history.append(ind)
            return True
        return False

    def best(self) -> Individual | None:
        if not self._cells:
            return None
        return max(self._cells.values(),
                   key=lambda i: (i.fitness, -i.cost))

    def frontier(self) -> list[Individual]:
        """The Pareto-ish frontier: cells sorted by fitness descending."""
        return sorted(self._cells.values(),
                      key=lambda i: (i.fitness, -i.cost), reverse=True)

    def underfilled_descriptors(self) -> list[tuple]:
        """Descriptors present in history but not currently held (exploration
        pressure toward rare niches)."""
        seen = set(self._cells)
        return [d for d in {i.descriptor for i in self._history} if d not in seen]

    def cells(self) -> dict[tuple, Individual]:
        return dict(self._cells)

    def __len__(self) -> int:
        return len(self._cells)

    # -- sampling -------------------------------------------------------------

    def sample_parent(self, rng, epsilon: float = 0.2) -> Individual | None:
        """Rank-biased over the frontier, with epsilon to underfilled niches.

        Every elite stays selectable (quality-diversity keeps rare niches in
        play); fitter ones are likelier parents via harmonic weights
        1/(rank+1) [1504.04909 + DGM-style exploitation 2505.22954].
        """
        if not self._cells:
            return None
        underfilled = self.underfilled_descriptors()
        if underfilled and rng.random() < epsilon:
            # re-seed from a niche we've seen but lost (backtracking pressure)
            hist = [i for i in self._history if i.descriptor in underfilled]
            if hist:
                return hist[-1]
        frontier = self.frontier()
        weights = [1.0 / (i + 1) for i in range(len(frontier))]
        r = rng.random() * sum(weights)
        acc = 0.0
        for ind, w in zip(frontier, weights):
            acc += w
            if r <= acc:
                return ind
        return frontier[-1]

    # -- persistence ------------------------------------------------------------

    def save(self, generation: int | None = None) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"cells": [i.to_dict() for i in self._cells.values()],
                "history": [i.to_dict() for i in self._history]}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._cells = {tuple(i["descriptor"]): Individual.from_dict(i)
                       for i in data.get("cells", [])}
        self._history = [Individual.from_dict(i) for i in data.get("history", [])]
