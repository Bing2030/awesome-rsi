"""Structured event log - the observability backbone.

Every engine action (proposal, patch, screen, eval, gate, accept, reject,
reflect, archive_update, rollback, budget, llm_call, approval) appends an
event. The log is what `rsif status/inspect` render, what the reflection
subsystem reads, and - together with seed.json and the LLM response cache -
the replay source for deterministic reproduction.

Grounding: observability with edit attribution is a prerequisite for
automated harness evolution [arXiv 2604.25850, three observability pillars].
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PROPOSAL = "proposal"
PATCH = "patch"
SCREEN = "screen"
EVAL = "eval"
GATE = "gate"
ACCEPT = "accept"
REJECT = "reject"
REFLECT = "reflect"
ARCHIVE_UPDATE = "archive_update"
ROLLBACK = "rollback"
BUDGET = "budget"
LLM_CALL = "llm_call"
APPROVAL = "approval"
RUN_START = "run_start"
RUN_END = "run_end"
ERROR = "error"
META_CONFIRM = "meta_confirm"
META_REVERT = "meta_revert"

KINDS = (
    PROPOSAL, PATCH, SCREEN, EVAL, GATE, ACCEPT, REJECT, REFLECT,
    ARCHIVE_UPDATE, ROLLBACK, BUDGET, LLM_CALL, APPROVAL, RUN_START, RUN_END,
    ERROR, META_CONFIRM, META_REVERT,
)

# Loop phases, matching the framework's design loop.
PHASE_PROPOSE = "proposal"
PHASE_EXPLORE = "exploration"
PHASE_DESIGN = "design"
PHASE_VERIFY = "verification"
PHASE_CORRECT = "correction"


@dataclass(frozen=True)
class Event:
    seq: int
    ts: float
    kind: str
    phase: str = ""
    generation: int = -1
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "Event":
        return cls(**json.loads(line))


class EventLog:
    """Append-only JSONL event log.

    The clock is injectable so deterministic tests can pin timestamps
    (byte-identical golden logs).
    """

    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self._seq = 0
        if self.path.exists():
            self._seq = max((e.seq for e in self.read()), default=0)

    def append(
        self,
        kind: str,
        phase: str = "",
        generation: int = -1,
        **payload: Any,
    ) -> Event:
        if kind not in KINDS:
            raise ValueError(f"unknown event kind: {kind!r}")
        self._seq += 1
        event = Event(self._seq, self.clock(), kind, phase, generation, payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_json() + "\n")
        return event

    def read(self) -> list[Event]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(Event.from_json(line))
        return events

    def tail(self, n: int = 20) -> list[Event]:
        return self.read()[-n:]

    def filter(self, kind: str | None = None, generation: int | None = None) -> list[Event]:
        out = []
        for e in self.read():
            if kind is not None and e.kind != kind:
                continue
            if generation is not None and e.generation != generation:
                continue
            out.append(e)
        return out
