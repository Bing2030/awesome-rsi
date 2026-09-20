"""Proposal: the improver's single bounded, testable change.

A proposal names the surface it targets, the operator it uses, a falsifiable
hypothesis, and the concrete Patch to apply. The patch is bounded (<= k ops).

Grounding: Promptbreeder/OPRO proposal-as-search-step [arXiv 2309.16797,
2309.03409]; STOP improver [2310.02304]; bounded edits [2605.23904, 2510.04618].
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from rsif.artifacts.model import ArtifactType, Patch, op_from_json


class ProposalError(Exception):
    pass


@dataclass
class Proposal:
    surface: ArtifactType
    operator: str
    hypothesis: str
    rationale: str
    patch: Patch

    def describe(self) -> str:
        return f"[{self.surface.value}/{self.operator}] {self.hypothesis}"


def parse_proposal(text: str) -> Proposal:
    """Parse an improver's JSON response into a Proposal.

    Tolerates a leading ```json fence and surrounding prose.
    """
    obj = _extract_json(text)
    try:
        surface = ArtifactType.parse(obj["surface"])
        ops_raw = obj.get("ops", [])
        if not ops_raw:
            raise ProposalError("proposal has no ops")
        ops = tuple(op_from_json(o) for o in ops_raw)
        patch = Patch(
            ops=ops,
            rationale=obj.get("rationale", ""),
            hypothesis=obj.get("hypothesis", ""),
        )
        return Proposal(
            surface=surface,
            operator=obj.get("operator", ""),
            hypothesis=obj.get("hypothesis", ""),
            rationale=obj.get("rationale", ""),
            patch=patch,
        )
    except (KeyError, ValueError) as e:
        raise ProposalError(f"invalid proposal: {e}") from e


def _extract_json(text: str) -> dict:
    text = text.strip()
    # strip code fences
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # find the first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ProposalError("no JSON object found in proposal")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ProposalError(f"bad JSON: {e}") from e
