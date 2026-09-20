"""Runtime attempt types shared by the runtime and the objectives."""

from __future__ import annotations

from dataclasses import dataclass, field

from rsif.llm.base import Usage


@dataclass
class TraceStep:
    """One observable step in an agent attempt (for reflections + logs)."""

    kind: str  # llm_call | tool_call | tool_result | submit
    text: str
    meta: dict = field(default_factory=dict)


@dataclass
class Attempt:
    """The outcome of one agent run on one task."""

    task_id: str
    result: str  # the agent's submitted answer
    ok: bool = True
    usage: Usage = field(default_factory=Usage)
    steps: int = 0
    wall_s: float = 0.0
    trace: list[TraceStep] = field(default_factory=list)
    error: str = ""
