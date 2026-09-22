"""Acceptance rules: the empirical validation gate.

The only evidence that counts is held-out execution. A candidate is accepted
iff it improves the *validation* split above a threshold [SkillOpt 2605.23904,
DGM 2505.22954]; the cheap train-split screen is a cascade that merely decides
whether the full (expensive) validation is worth running [AlphaEvolve 2506.13131].

Grounding: execution-grounded, never intrinsic self-judgment [2310.01798].
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rsif.objectives.base import ScoreBook


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str  # "accepted" | "screen" | "val" | "canary" | "scan" | "apply"
    detail: str = ""


def pass_screen(child_score: float, parent_score: float, epsilon: float) -> bool:
    """Cheap cascade: continue only if the candidate is within epsilon of the
    parent on the probe split (usually epsilon is loose, e.g. 0.30)."""
    return child_score >= parent_score - epsilon


def accept_val(child_val: float, parent_val: float, threshold: float,
               child_scores: list[float] | None = None,
               parent_scores: list[float] | None = None) -> bool:
    """Strict gate: accept only a held-out validation gain above threshold.

    With per-task scores, additionally require at least one NET task gain
    (gains - losses >= 1): on small suites the mean can move by threshold
    amounts through reshuffled noise, and a sub-task improvement is not
    evidence of anything. Paired per-task comparison is the cheap, honest
    noise floor at the gate; the bootstrap CI in `rsif report` is the final
    check. [2605.23904 held-out acceptance; 2510.16657 noise guard]
    """
    if not child_val > parent_val + threshold:
        return False
    if child_scores is not None and parent_scores is not None:
        gains = sum(1 for c, p in zip(child_scores, parent_scores) if c > p)
        losses = sum(1 for c, p in zip(child_scores, parent_scores) if c < p)
        if gains - losses < 1:
            return False
    return True


def pass_canary(child_score: float, parent_score: float) -> bool:
    """Canaries must never regress: any drop is a hard reject."""
    return child_score >= parent_score


def paired_scores(child: ScoreBook, parent: ScoreBook,
                  ) -> tuple[list[float], list[float]] | None:
    """Per-task paired scores over tasks BOTH sides actually scored.

    A task that timed out on either side carries no verdict, so it is
    excluded from the paired comparison rather than counted as a loss or a
    win — an infra failure is unscored, not a zero [2609.15364 §4.1].
    Returns None when no task was scored on both sides (no comparable
    evidence at all; the caller must treat the gate as unscored).
    """
    c = {s.task_id: s.score for s in child.scored}
    p = {s.task_id: s.score for s in parent.scored}
    common = [t for t in c if t in p]  # child's order = suite order
    if not common:
        return None
    return [c[t] for t in common], [p[t] for t in common]
