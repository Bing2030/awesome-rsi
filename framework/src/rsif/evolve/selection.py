"""Acceptance rules: the empirical validation gate.

The only evidence that counts is held-out execution. A candidate is accepted
iff it improves the *validation* split above a threshold [SkillOpt 2605.23904,
DGM 2505.22954]; the cheap train-split screen is a cascade that merely decides
whether the full (expensive) validation is worth running [AlphaEvolve 2506.13131].

Grounding: execution-grounded, never intrinsic self-judgment [2310.01798].
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str  # "accepted" | "screen" | "val" | "canary" | "scan" | "apply"
    detail: str = ""


def pass_screen(child_score: float, parent_score: float, epsilon: float) -> bool:
    """Cheap cascade: continue only if the candidate is within epsilon of the
    parent on the probe split (usually epsilon is loose, e.g. 0.30)."""
    return child_score >= parent_score - epsilon


def accept_val(child_val: float, parent_val: float, threshold: float) -> bool:
    """Strict gate: accept only a held-out validation gain above threshold."""
    return child_val > parent_val + threshold


def pass_canary(child_score: float, parent_score: float) -> bool:
    """Canaries must never regress: any drop is a hard reject."""
    return child_score >= parent_score
