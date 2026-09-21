"""Artifact data model: types, versions, patches.

Everything improvable is the same `Artifact` type with a different payload
convention. Versions are immutable once written; lineage is append-only; a
`Patch` is a bounded set of operations with a rationale and a falsifiable
hypothesis.

Grounding: Gödel Agent [arXiv 2410.04444]; bounded incremental edits
[arXiv 2510.04618, 2605.23904]; improver templates as evolvable artifacts
[arXiv 2310.02304, 2309.16797, 2607.05297].
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArtifactType(str, Enum):
    SKILL = "skill"      # executable tool code + manifest [2305.16291]
    PROMPT = "prompt"    # prompt / strategy text [2309.03409, 2309.16797]
    MEMORY = "memory"    # structured playbook sections [2510.04618]
    MODULE = "module"    # agent architecture code (module ABI) [2408.08435]
    META = "meta"        # the improver's own templates / operator catalog [2310.02304]
    POLICY = "policy"    # runtime context-assembly bounds (context compaction) [2609.20519]

    @classmethod
    def parse(cls, value: str) -> "ArtifactType":
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"unknown artifact type: {value!r}") from None


def content_hash(payload: dict[str, str]) -> str:
    """Deterministic hash of a payload (filename -> content)."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


# -- patch operations ------------------------------------------------------


@dataclass(frozen=True)
class CreateOp:
    artifact_id: str
    type: ArtifactType
    payload: dict[str, str]

    op: str = "create"


@dataclass(frozen=True)
class UpdateOp:
    artifact_id: str
    payload: dict[str, str]
    edit_kind: str = "replace"  # replace | append_section | edit_section | refine

    op: str = "update"


@dataclass(frozen=True)
class DeleteOp:
    artifact_id: str

    op: str = "delete"


@dataclass(frozen=True)
class RestoreOp:
    artifact_id: str
    version: int

    op: str = "restore"


PatchOp = CreateOp | UpdateOp | DeleteOp | RestoreOp


@dataclass(frozen=True)
class Patch:
    """A proposed, bounded modification of the agent.

    Grounding: bounded add/delete/replace edits accepted only on held-out
    gain [arXiv 2605.23904]; incremental structured edits avoid context
    collapse [arXiv 2510.04618].
    """

    ops: tuple[PatchOp, ...]
    rationale: str = ""
    hypothesis: str = ""

    def op_types(self) -> set[ArtifactType]:
        return {o.type for o in self.ops if isinstance(o, CreateOp)}


def op_to_json(op: PatchOp) -> dict[str, Any]:
    if isinstance(op, CreateOp):
        return {"op": "create", "artifact_id": op.artifact_id, "type": op.type.value,
                "payload": op.payload}
    if isinstance(op, UpdateOp):
        return {"op": "update", "artifact_id": op.artifact_id, "payload": op.payload,
                "edit_kind": op.edit_kind}
    if isinstance(op, DeleteOp):
        return {"op": "delete", "artifact_id": op.artifact_id}
    if isinstance(op, RestoreOp):
        return {"op": "restore", "artifact_id": op.artifact_id, "version": op.version}
    raise TypeError(f"unknown patch op: {op!r}")


def op_from_json(data: dict[str, Any]) -> PatchOp:
    kind = data.get("op")
    if kind == "create":
        return CreateOp(data["artifact_id"], ArtifactType.parse(data["type"]),
                        {k: str(v) for k, v in data["payload"].items()})
    if kind == "update":
        return UpdateOp(data["artifact_id"],
                        {k: str(v) for k, v in data["payload"].items()},
                        data.get("edit_kind", "replace"))
    if kind == "delete":
        return DeleteOp(data["artifact_id"])
    if kind == "restore":
        return RestoreOp(data["artifact_id"], int(data["version"]))
    raise ValueError(f"unknown op kind: {kind!r}")


def patch_to_json(patch: Patch) -> str:
    return json.dumps(
        {"ops": [op_to_json(o) for o in patch.ops],
         "rationale": patch.rationale, "hypothesis": patch.hypothesis},
        sort_keys=True, separators=(",", ":"))


def patch_from_json(text: str) -> Patch:
    data = json.loads(text)
    return Patch(tuple(op_from_json(o) for o in data["ops"]),
                 data.get("rationale", ""), data.get("hypothesis", ""))


@dataclass(frozen=True)
class LineageEntry:
    seq: int
    artifact_id: str
    op: str  # create | update | delete | restore
    from_v: int  # 0 for create
    to_v: int  # 0 for delete
    proposal_id: str
    generation: int
    content_hash: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "seq": self.seq, "artifact_id": self.artifact_id, "op": self.op,
            "from_v": self.from_v, "to_v": self.to_v,
            "proposal_id": self.proposal_id, "generation": self.generation,
            "content_hash": self.content_hash,
        }, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "LineageEntry":
        return cls(**json.loads(line))
