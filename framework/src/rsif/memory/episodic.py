"""Episodic memory: Reflexion-style reflections.

On a failed attempt or rejected proposal, the agent reads the trace and
writes a reflection (what went wrong, what to try next). Reflections are
stored with a task signature and retrieved lexically to guide similar future
attempts - improvement lives in context, with no weight updates.

Grounding: Reflexion [arXiv 2303.11366].
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Reflection:
    task_signature: str
    text: str
    source: str = ""  # proposal id / task id
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"task_signature": self.task_signature, "text": self.text,
                "source": self.source, "ts": self.ts}


class ReflectionStore:
    """Persistent, retrieval-backed store of reflections."""

    def __init__(self, path: Path, retriever=None, max_entries: int = 50,
                 clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.max_entries = max_entries
        self._reflections: list[Reflection] = []
        if retriever is None:
            from rsif.memory.retrieve import TfidfRetriever

            retriever = TfidfRetriever()
        self.retriever = retriever
        self._load()

    # -- write ---------------------------------------------------------------

    def add(self, task_signature: str, text: str, source: str = "") -> Reflection:
        r = Reflection(task_signature=task_signature, text=text,
                       source=source, ts=self.clock())
        self._reflections.append(r)
        if len(self._reflections) > self.max_entries:
            self._reflections = self._reflections[-self.max_entries:]
        self._save()
        return r

    def reflect(self, task_signature: str, trace_text: str, llm=None,
                source: str = "") -> Reflection:
        """Produce a reflection from a trace. If `llm` is None, the reflection
        is a verbatim (truncated) trace - used in deterministic tests."""
        if llm is None:
            text = f"trace: {trace_text[:500]}"
        else:
            text = _reflect_via_llm(llm, trace_text)
        return self.add(task_signature, text, source)

    # -- read ----------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 3) -> list[Reflection]:
        docs = [r.text for r in self._reflections]
        ranked = self.retriever.retrieve(query, docs, top_k=top_k)
        return [self._reflections[i] for i, _ in ranked]

    def render_for_context(self, query: str, top_k: int = 3) -> str:
        refs = self.retrieve(query, top_k)
        if not refs:
            return ""
        return "\n".join(f"- {r.text}" for r in refs)

    def all(self) -> list[Reflection]:
        return list(self._reflections)

    def __len__(self) -> int:
        return len(self._reflections)

    # -- persistence -----------------------------------------------------------

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "\n".join(json.dumps(r.to_dict()) for r in self._reflections) + "\n",
            encoding="utf-8")

    def _load(self) -> None:
        if not self.path.exists():
            return
        self._reflections = [
            Reflection(**json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _reflect_via_llm(llm, trace_text: str) -> str:
    from rsif.llm.base import CompletionRequest, Message

    req = CompletionRequest(
        messages=(Message("system", "You are a reflective critic. Read the "
                                   "attempt trace and write a short reflection: what went "
                                   "wrong and what to try next."),
                  Message("user", trace_text[:2000])),
        role="reflect",
    )
    return llm.complete(req).text.strip()
