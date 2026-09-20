"""M1 verification: artifact versioning, immutability, rollback, lineage."""

import pytest

from rsif.artifacts.model import (
    ArtifactType,
    CreateOp,
    DeleteOp,
    Patch,
    RestoreOp,
    UpdateOp,
    content_hash,
    op_from_json,
    op_to_json,
    patch_from_json,
    patch_to_json,
)
from rsif.artifacts.store import ApplyResult, ArtifactError, ArtifactStore


def _seed(store: ArtifactStore) -> None:
    store.create("prompt/system", ArtifactType.PROMPT,
                 {"system.md": "v1 text"}, proposal_id="seed")
    store.promote(ApplyResult({"prompt/system": 1}), proposal_id="seed")


def test_create_and_read(ws, store):
    _seed(store)
    assert store.read_active("prompt/system") == {"system.md": "v1 text"}
    assert store.active_version("prompt/system") == 1


def test_version_immutability(ws, store):
    _seed(store)
    with pytest.raises(ArtifactError):
        store.create("prompt/system", ArtifactType.PROMPT, {"system.md": "dup"})


def test_update_creates_new_version_and_lineage(ws, store):
    _seed(store)
    v2 = store.update("prompt/system", {"system.md": "v2 text"}, proposal_id="p1", generation=1)
    assert v2 == 2
    assert store.latest_version("prompt/system") == 2

    # not yet promoted: active checkout still at v1
    assert store.active_version("prompt/system") == 1

    store.promote(ApplyResult({"prompt/system": 2}), proposal_id="p1", generation=1)
    assert store.read_active("prompt/system") == {"system.md": "v2 text"}


def test_rollback_restores_exact_payload(ws, store):
    _seed(store)
    store.update("prompt/system", {"system.md": "v2"}, proposal_id="p1")
    store.promote(ApplyResult({"prompt/system": 2}))
    store.restore("prompt/system", 1, proposal_id="manual")
    assert store.read_active("prompt/system") == {"system.md": "v1 text"}

    lineage = store.lineage("prompt/system")
    assert [e.op for e in lineage] == ["create", "update", "restore"]
    assert lineage[-1].from_v == 2 and lineage[-1].to_v == 1


def test_lineage_append_only_with_parent_refs(ws, store):
    _seed(store)
    store.update("prompt/system", {"system.md": "b"}, proposal_id="p1")
    entries = store.lineage("prompt/system")
    assert [e.seq for e in entries] == [1, 2]
    assert entries[1].from_v == 1 and entries[1].to_v == 2


def test_apply_patch_with_delete(ws, store):
    _seed(store)
    store.create("skill/add", ArtifactType.SKILL,
                 {"module.py": "x = 1"}, proposal_id="seed")
    store.promote(ApplyResult({"skill/add": 1}))

    patch = Patch(
        ops=(DeleteOp("skill/add"),),
        rationale="skill unused", hypothesis="removal changes nothing",
    )
    result = store.apply_patch(patch, proposal_id="p2", generation=2)
    assert result.versions == {"skill/add": 0}
    # active until promoted
    assert "skill/add" in store.checkout()
    store.promote(result, proposal_id="p2", generation=2)
    assert "skill/add" not in store.checkout()


def test_apply_patch_restore_op(ws, store):
    _seed(store)
    store.update("prompt/system", {"system.md": "v2"}, proposal_id="p1")
    store.promote(ApplyResult({"prompt/system": 2}))
    patch = Patch(ops=(RestoreOp("prompt/system", 1),), rationale="go back")
    result = store.apply_patch(patch, proposal_id="p3")
    assert result.versions == {"prompt/system": 1}
    assert store.read_active("prompt/system") == {"system.md": "v1 text"}


def test_namespaced_ids_required(ws, store):
    with pytest.raises(ArtifactError):
        store.create("bare-name", ArtifactType.PROMPT, {"a": "b"})


def test_patch_json_roundtrip():
    patch = Patch(
        ops=(
            CreateOp("skill/x", ArtifactType.SKILL, {"module.py": "1"}),
            UpdateOp("prompt/system", {"system.md": "z"}, edit_kind="edit_section"),
        ),
        rationale="why", hypothesis="what should improve",
    )
    restored = patch_from_json(patch_to_json(patch))
    assert restored.rationale == "why"
    assert op_to_json(restored.ops[0]) == op_to_json(patch.ops[0])
    assert op_from_json(op_to_json(patch.ops[1])) == patch.ops[1]


def test_content_hash_stable_and_order_insensitive():
    h1 = content_hash({"a": "1", "b": "2"})
    h2 = content_hash({"b": "2", "a": "1"})
    assert h1 == h2
    assert content_hash({"a": "1"}) != h1


def test_seed_defaults_creates_canonical_artifacts(ws, store):
    from rsif.config import RunConfig

    store.seed_defaults(RunConfig())
    active = store.checkout()
    for aid in ("prompt/system", "memory/playbook", "meta/improver-template",
                "meta/operator-catalog", "module/default"):
        assert active.get(aid) == 1, aid
    assert store.type_of("module/default") == ArtifactType.MODULE
    assert store.active_ids(ArtifactType.META) == [
        "meta/improver-template", "meta/operator-catalog"]
