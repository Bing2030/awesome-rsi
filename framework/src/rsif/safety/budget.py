"""Hard budget: the cost blowout guard.

Every LLM completion is recorded; the run aborts cleanly when any dimension
(llm calls, estimated USD, wall clock) is exhausted. Cheap cascade screening
plus caching keeps runs under budget; the budget makes overrun impossible.

Grounding: hard budget as first-class harness guard [AlphaEvolve 2506.13131;
misevolution guards 2509.26354, 2603.06333].
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


class BudgetExhausted(Exception):
    """Raised mid-flight when a call pushes the run strictly past a limit.

    Distinct from the pre-work `exhausted()` check (which fires at the limit):
    this bounds overshoot to a single call instead of a whole proposal.
    """

    def __init__(self, dimension: str):
        super().__init__(dimension)
        self.dimension = dimension


@dataclass
class Budget:
    max_llm_calls: int = 2000
    max_usd: float = 1.0
    max_wall_s: float = 3600.0
    price_per_mtok_in: float = 0.0
    price_per_mtok_out: float = 0.0
    clock: Callable[[], float] = time.monotonic

    llm_calls: int = field(default=0)
    tokens_in: int = field(default=0)
    tokens_out: int = field(default=0)
    usd: float = field(default=0.0)
    _start: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self._start = self.clock()

    def record(self, tokens_in: int, tokens_out: int) -> None:
        self.llm_calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.usd += (tokens_in * self.price_per_mtok_in
                     + tokens_out * self.price_per_mtok_out) / 1_000_000

    def wall_s(self) -> float:
        return self.clock() - self._start

    def exhausted(self) -> str | None:
        """The violated dimension's name, or None if budget remains.

        Checked before starting new work: fires AT the limit.
        """
        if self.max_llm_calls >= 0 and self.llm_calls >= self.max_llm_calls:
            return "llm_calls"
        if self.max_usd >= 0 and self.usd >= self.max_usd:
            return "usd"
        if self.max_wall_s >= 0 and self.wall_s() >= self.max_wall_s:
            return "wall_clock"
        return None

    def overshot(self) -> str | None:
        """The dimension a completed call has pushed strictly PAST the limit.

        Checked after every recorded call: bounds overshoot to one call
        instead of one proposal (~20-30 calls).
        """
        if self.max_llm_calls >= 0 and self.llm_calls > self.max_llm_calls:
            return "llm_calls"
        if self.max_usd >= 0 and self.usd > self.max_usd:
            return "usd"
        if self.max_wall_s >= 0 and self.wall_s() > self.max_wall_s:
            return "wall_clock"
        return None

    def snapshot(self) -> dict:
        return {"llm_calls": self.llm_calls, "usd": round(self.usd, 6),
                "wall_s": round(self.wall_s(), 3),
                "tokens": self.tokens_in + self.tokens_out}
