"""Approvers: the human (or policy) in the loop for high-stakes edits.

META artifacts change how the improver itself behaves - a self-referential
surface [2309.16797, 2310.02304]. Such edits require an explicit approval in
addition to the normal gates. Fail-closed: if approval is required but no
approver is wired, the edit is denied.

Grounding: misevolution guards [2509.26354, 2603.06333]; slow-loop human
oversight [2607.05297].
"""

from __future__ import annotations

from typing import Protocol


class Approver(Protocol):
    def approve(self, proposal_id: str, summary: str) -> bool: ...


class FakeApprover:
    """Deterministic approver for tests and scripted demos."""

    def __init__(self, allowed: bool = True):
        self.allowed = allowed
        self.requests: list[tuple[str, str]] = []

    def approve(self, proposal_id: str, summary: str) -> bool:
        self.requests.append((proposal_id, summary))
        return self.allowed


class CLIApprover:
    """Ask a human operator on stdin. Non-interactive stdin denies."""

    def __init__(self, stream_in=None, stream_out=None):
        import sys

        self.stream_in = stream_in if stream_in is not None else sys.stdin
        self.stream_out = stream_out if stream_out is not None else sys.stdout

    def approve(self, proposal_id: str, summary: str) -> bool:
        print(f"\n[approval request] {proposal_id}: {summary}", file=self.stream_out)
        print("approve? [y/N] ", end="", flush=True, file=self.stream_out)
        try:
            answer = self.stream_in.readline()
        except (EOFError, OSError):
            return False
        return answer.strip().lower() in ("y", "yes")
