"""Insight distillation: ExpeL-style rules over verified trajectories only.

Insights are distilled from *verified* (successful) trajectories and retired
when they correlate with failures - provenance and usage counters make the
collapse guard concrete: self-generated feedback is only trusted when it is
grounded in execution outcomes.

Grounding: ExpeL [arXiv 2308.10144]; model-collapse guard [arXiv 2510.16657].
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Insight:
    text: str
    provenance: list[str] = field(default_factory=list)  # trajectory ids
    uses: int = 0
    failures_after_use: int = 0
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"text": self.text, "provenance": self.provenance,
                "uses": self.uses, "failures_after_use": self.failures_after_use,
                "ts": self.ts}


class InsightStore:
    def __init__(self, path: Path, retriever=None, max_entries: int = 100,
                 clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.max_entries = max_entries
        self._insights: list[Insight] = []
        if retriever is None:
            from rsif.memory.retrieve import TfidfRetriever

            retriever = TfidfRetriever()
        self.retriever = retriever
        self._load()

    def distill(self, trajectories: list[tuple[str, str]]) -> list[Insight]:
        """Add one insight per successful trajectory (id, summary)."""
        added = []
        for traj_id, summary in trajectories:
            ins = Insight(text=summary, provenance=[traj_id], ts=self.clock())
            self._insights.append(ins)
            added.append(ins)
        if len(self._insights) > self.max_entries:
            self._insights = self._insights[-self.max_entries:]
        self._save()
        return added

    def retrieve(self, query: str, top_k: int = 3) -> list[Insight]:
        docs = [i.text for i in self._insights]
        ranked = self.retriever.retrieve(query, docs, top_k=top_k)
        for idx, _ in ranked:
            self._insights[idx].uses += 1
        self._save()
        return [self._insights[i] for i, _ in ranked]

    def record_failure(self, insight_indices: list[int]) -> None:
        for idx in insight_indices:
            if 0 <= idx < len(self._insights):
                self._insights[idx].failures_after_use += 1

    def retire_correlated(self, threshold: int = 2) -> list[Insight]:
        """Retire insights that correlated with failures too often."""
        keep, retired = [], []
        for ins in self._insights:
            if ins.failures_after_use >= threshold:
                retired.append(ins)
            else:
                keep.append(ins)
        self._insights = keep
        self._save()
        return retired

    def render_for_context(self, query: str, top_k: int = 3) -> str:
        ins = self.retrieve(query, top_k)
        if not ins:
            return ""
        return "\n".join(f"- {i.text}" for i in ins)

    def all(self) -> list[Insight]:
        return list(self._insights)

    def __len__(self) -> int:
        return len(self._insights)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "\n".join(json.dumps(i.to_dict()) for i in self._insights) + "\n",
            encoding="utf-8")

    def _load(self) -> None:
        if not self.path.exists():
            return
        self._insights = [Insight(**json.loads(line))
                          for line in self.path.read_text(encoding="utf-8").splitlines()
                          if line.strip()]
