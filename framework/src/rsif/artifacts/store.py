"""ArtifactStore: immutable version dirs + append-only lineage + active checkout.

Semantics:
- `apply_patch` writes NEW immutable versions and lineage entries, but does
  NOT activate them - candidates are evaluated first (empirical validation
  gate [arXiv 2505.22954, 2605.23904]).
- `promote` moves the active checkout to a candidate mapping after
  acceptance. Rejected versions simply stay unaccepted.
- `rollback` (= promote to an older version) appends a `restore` lineage
  entry - history is never rewritten (DGM backtracking [arXiv 2505.22954]).

Checkout is a manifest (artifact_id -> version in checkout.json), not file
copies: immutable version dirs are read by reference.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rsif.artifacts.model import (
    ArtifactType,
    CreateOp,
    DeleteOp,
    LineageEntry,
    Patch,
    PatchOp,
    RestoreOp,
    UpdateOp,
    content_hash,
    op_to_json,
)
from rsif.artifacts.workspace import RunWorkspace


class ArtifactError(Exception):
    pass


@dataclass
class ApplyResult:
    """Mapping produced by apply_patch: artifact_id -> candidate version.

    Version 0 for DeleteOp means 'gone if promoted'.
    """

    versions: dict[str, int]

    def deletions(self) -> list[str]:
        return [aid for aid, v in self.versions.items() if v == 0]


class ArtifactStore:
    def __init__(self, workspace: RunWorkspace, clock: Callable[[], float] = time.time):
        self.ws = workspace
        self.clock = clock
        self._lineage_seq = 0
        if self.ws.lineage_path.exists():
            self._lineage_seq = max(
                (e.seq for e in self.lineage()), default=0
            )

    # -- construction ------------------------------------------------------

    @classmethod
    def open(cls, workspace: RunWorkspace) -> "ArtifactStore":
        return cls(workspace)

    # -- checkout (active agent) -------------------------------------------

    def checkout(self) -> dict[str, int]:
        if not self.ws.checkout_path.exists():
            return {}
        return json.loads(self.ws.checkout_path.read_text(encoding="utf-8"))

    def _write_checkout(self, mapping: dict[str, int]) -> None:
        self.ws.checkout_path.write_text(
            json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8"
        )

    def promote(self, result: ApplyResult, proposal_id: str = "", generation: int = -1) -> None:
        mapping = self.checkout()
        for artifact_id, version in result.versions.items():
            if version == 0:
                mapping.pop(artifact_id, None)
            else:
                mapping[artifact_id] = version
            self._set_accepted(artifact_id, version)
        self._write_checkout(mapping)

    # -- core writes ---------------------------------------------------------

    def create(self, artifact_id: str, type: ArtifactType, payload: dict[str, str],
               proposal_id: str = "", generation: int = -1) -> int:
        if self._artifact_dir(artifact_id).exists():
            raise ArtifactError(f"artifact already exists: {artifact_id}")
        return self._write_version(artifact_id, 1, type, payload, proposal_id, generation)

    def update(self, artifact_id: str, payload: dict[str, str],
               edit_kind: str = "replace", proposal_id: str = "", generation: int = -1) -> int:
        current = self.latest_version(artifact_id)
        return self._write_version(artifact_id, current + 1, self.type_of(artifact_id),
                                   payload, proposal_id, generation, edit_kind=edit_kind)

    def delete(self, artifact_id: str, proposal_id: str = "", generation: int = -1) -> None:
        self._require(artifact_id)
        self._append_lineage(artifact_id, "delete", self.latest_version(artifact_id), 0,
                             proposal_id, generation)

    def restore(self, artifact_id: str, version: int,
                proposal_id: str = "", generation: int = -1) -> None:
        self._require(artifact_id)
        if not self.version_dir(artifact_id, version).exists():
            raise ArtifactError(f"version not found: {artifact_id} v{version}")
        mapping = self.checkout()
        mapping[artifact_id] = version
        self._write_checkout(mapping)
        self._append_lineage(artifact_id, "restore", self.latest_version(artifact_id), version,
                             proposal_id, generation)

    def apply_patch(self, patch: Patch, proposal_id: str = "",
                    generation: int = -1) -> ApplyResult:
        """Materialize a candidate. Writes versions + lineage; no activation."""
        versions: dict[str, int] = {}
        for op in patch.ops:
            if isinstance(op, CreateOp):
                versions[op.artifact_id] = self.create(
                    op.artifact_id, op.type, op.payload, proposal_id, generation)
            elif isinstance(op, UpdateOp):
                versions[op.artifact_id] = self.update(
                    op.artifact_id, op.payload, op.edit_kind, proposal_id, generation)
            elif isinstance(op, DeleteOp):
                self.delete(op.artifact_id, proposal_id, generation)
                versions[op.artifact_id] = 0
            elif isinstance(op, RestoreOp):
                self.restore(op.artifact_id, op.version, proposal_id, generation)
                versions[op.artifact_id] = op.version
            else:
                raise ArtifactError(f"unknown op: {op!r}")
        return ApplyResult(versions)

    # -- reads ---------------------------------------------------------------

    def version_dir(self, artifact_id: str, version: int) -> Path:
        return self._artifact_dir(artifact_id) / f"v{version}"

    def read_version(self, artifact_id: str, version: int) -> dict[str, str]:
        d = self.version_dir(artifact_id, version)
        if not d.exists():
            raise ArtifactError(f"version not found: {artifact_id} v{version}")
        return {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(d.iterdir())
            if p.is_file() and p.name != "meta.json"
        }

    def read_active(self, artifact_id: str) -> dict[str, str]:
        version = self.checkout().get(artifact_id)
        if version is None:
            raise ArtifactError(f"artifact not active: {artifact_id}")
        return self.read_version(artifact_id, version)

    def active_version(self, artifact_id: str) -> int | None:
        return self.checkout().get(artifact_id)

    def active_ids(self, type: ArtifactType | None = None) -> list[str]:
        out = []
        for artifact_id, version in sorted(self.checkout().items()):
            if version == 0:
                continue
            if type is None or self.type_of(artifact_id) == type:
                out.append(artifact_id)
        return out

    def latest_version(self, artifact_id: str) -> int:
        self._require(artifact_id)
        versions = [
            int(p.name[1:]) for p in self._artifact_dir(artifact_id).iterdir()
            if p.is_dir() and p.name.startswith("v")
        ]
        return max(versions)

    def list_versions(self, artifact_id: str) -> list[int]:
        self._require(artifact_id)
        return sorted(
            int(p.name[1:]) for p in self._artifact_dir(artifact_id).iterdir()
            if p.is_dir() and p.name.startswith("v")
        )

    def type_of(self, artifact_id: str) -> ArtifactType:
        self._require(artifact_id)
        meta = self._read_meta(artifact_id, self.latest_version(artifact_id))
        return ArtifactType.parse(meta["type"])

    def lineage(self, artifact_id: str | None = None) -> list[LineageEntry]:
        if not self.ws.lineage_path.exists():
            return []
        out = []
        for line in self.ws.lineage_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            entry = LineageEntry.from_json(line)
            if artifact_id is None or entry.artifact_id == artifact_id:
                out.append(entry)
        return out

    def snapshot(self) -> dict[str, int]:
        """A copy of the active checkout (used by the archive)."""
        return dict(self.checkout())

    # -- seeding --------------------------------------------------------------

    def seed_defaults(self, cfg) -> None:
        """Create the canonical seed artifacts and activate them."""
        from rsif.constants import (
            DEFAULT_IMPROVER_TEMPLATE,
            DEFAULT_SYSTEM_PROMPT,
            DEFAULT_MODULE_ID,
            IMPROVER_TEMPLATE_ID,
            OPERATOR_CATALOG_ID,
            PLAYBOOK_ID,
            SYSTEM_PROMPT_ID,
        )
        from rsif.operators_seed import seed_operator_catalog

        self.create(SYSTEM_PROMPT_ID, ArtifactType.PROMPT,
                    {"system.md": DEFAULT_SYSTEM_PROMPT}, proposal_id="seed")
        self.create(PLAYBOOK_ID, ArtifactType.MEMORY,
                    {"playbook.json": json.dumps(
                        [{"id": "s1", "title": "General strategy",
                          "body": "Read the task carefully; implement exactly the "
                                  "requested signature; keep code simple and stdlib-only."}],
                        indent=2)}, proposal_id="seed")
        self.create(IMPROVER_TEMPLATE_ID, ArtifactType.META,
                    {"template.md": DEFAULT_IMPROVER_TEMPLATE}, proposal_id="seed")
        self.create(OPERATOR_CATALOG_ID, ArtifactType.META,
                    {"operators.json": json.dumps(
                        seed_operator_catalog(), indent=2)}, proposal_id="seed")

        default_module = _default_module_source()
        self.create(DEFAULT_MODULE_ID, ArtifactType.MODULE,
                    {"module.py": default_module}, proposal_id="seed")

        self.promote(ApplyResult({
            SYSTEM_PROMPT_ID: 1, PLAYBOOK_ID: 1, IMPROVER_TEMPLATE_ID: 1,
            OPERATOR_CATALOG_ID: 1, DEFAULT_MODULE_ID: 1,
        }), proposal_id="seed")

    # -- internals --------------------------------------------------------------

    def _artifact_dir(self, artifact_id: str) -> Path:
        if "/" not in artifact_id:
            raise ArtifactError("artifact ids must be namespaced, e.g. 'prompt/system'")
        return self.ws.artifacts_dir / artifact_id

    def _require(self, artifact_id: str) -> None:
        if not self._artifact_dir(artifact_id).exists():
            raise ArtifactError(f"unknown artifact: {artifact_id}")

    def _write_version(self, artifact_id: str, version: int, type: ArtifactType,
                       payload: dict[str, str], proposal_id: str, generation: int,
                       edit_kind: str = "replace") -> int:
        d = self.version_dir(artifact_id, version)
        if d.exists():
            raise ArtifactError(
                f"version immutable: {artifact_id} v{version} already exists")
        d.mkdir(parents=True)
        for name, content in sorted(payload.items()):
            (d / name).write_text(content, encoding="utf-8")
        digest = content_hash(payload)
        meta = {
            "artifact_id": artifact_id, "version": version, "type": type.value,
            "content_hash": digest, "proposal_id": proposal_id,
            "generation": generation, "accepted": False, "edit_kind": edit_kind,
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True),
                                     encoding="utf-8")
        self._append_lineage(artifact_id, "create" if version == 1 else "update",
                             version - 1, version, proposal_id, generation,
                             content_hash=digest)
        return version

    def _read_meta(self, artifact_id: str, version: int) -> dict:
        p = self.version_dir(artifact_id, version) / "meta.json"
        if not p.exists():
            raise ArtifactError(f"missing meta for {artifact_id} v{version}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _set_accepted(self, artifact_id: str, version: int) -> None:
        if version == 0:
            return
        p = self.version_dir(artifact_id, version) / "meta.json"
        meta = json.loads(p.read_text(encoding="utf-8"))
        meta["accepted"] = True
        # meta.json is metadata, not payload; mutation here does not break
        # payload immutability guarantees (content_hash covers payload only).
        p.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

    def _append_lineage(self, artifact_id: str, op: str, from_v: int, to_v: int,
                        proposal_id: str, generation: int,
                        content_hash: str = "") -> LineageEntry:
        self._lineage_seq += 1
        entry = LineageEntry(self._lineage_seq, artifact_id, op, from_v, to_v,
                             proposal_id, generation, content_hash)
        with self.ws.lineage_path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")
        return entry


def _default_module_source() -> str:
    """Source of the default architecture module (module ABI implementer)."""
    from rsif.constants import DEFAULT_MODULE_CODE

    return DEFAULT_MODULE_CODE
