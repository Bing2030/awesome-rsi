"""Drift monitor: misevolution detection.

Misevolution is expected, not exceptional [2509.26354, 2603.06333]. The
monitor checks the ACTIVE agent at every generation end:

- active_regression / canary_regression: the deployed agent got worse than
  the archive best / the baseline canaries -> auto-rollback fires
- stagnation: a long run of rejections without any accepted improvement ->
  continuing requires an explicit approval

All checks are execution-grounded (memoized scores), never self-judged
[2310.01798].
"""

from __future__ import annotations

from dataclasses import dataclass, field

CANARY_REGRESSION = "canary_regression"
ACTIVE_REGRESSION = "active_regression"
STAGNATION = "stagnation"


@dataclass
class DriftReport:
    alarms: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    @property
    def rollback_alarm(self) -> bool:
        return CANARY_REGRESSION in self.alarms or ACTIVE_REGRESSION in self.alarms


class DriftMonitor:
    def __init__(self, baseline_canary: float, stagnation_threshold: int = 4):
        self.baseline_canary = baseline_canary
        self.stagnation_threshold = stagnation_threshold

    def check(self, *, active_val: float, active_canary: float,
              best_val: float, consecutive_rejections: int) -> DriftReport:
        alarms: list[str] = []
        detail: dict = {}
        if active_canary < self.baseline_canary:
            alarms.append(CANARY_REGRESSION)
            detail["canary"] = f"{active_canary:.4f} < {self.baseline_canary:.4f}"
        if best_val > active_val + 1e-9:
            alarms.append(ACTIVE_REGRESSION)
            detail["val"] = f"active {active_val:.4f} < archive best {best_val:.4f}"
        if consecutive_rejections >= self.stagnation_threshold:
            alarms.append(STAGNATION)
            detail["rejections"] = consecutive_rejections
        return DriftReport(alarms, detail)
