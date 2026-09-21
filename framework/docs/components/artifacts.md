# Component guide — the artifact store

*What evolves is data: versioned, hashed, lineage-tracked, and activated
only through an explicit promotion.*

Files: `src/rsif/artifacts/model.py` (types & patches),
`src/rsif/artifacts/store.py` (the store),
`src/rsif/artifacts/workspace.py` (the run layout),
`src/rsif/operators_seed.py` + `src/rsif/evolve/operators.py` (the operator
catalog). Verified by `tests/unit/test_store.py`,
`tests/unit/test_evolve.py`.

## The six artifact types

`ArtifactType` (model.py) — everything improvable is the same `Artifact`
shape with a different payload convention:

| Type | Payload convention | Read by | Seeds |
|---|---|---|---|
| `skill` | `module.py` (a `main(**args)` function) + `manifest.json` (`name`, `description`) | assembler → `SkillSpec` → runtime tools | — |
| `prompt` | `system.md` (first text file wins) | assembler → `system_prompt` | `prompt/system` |
| `memory` | `playbook.json` (list of sections) or free text | assembler → memory text | `memory/playbook` |
| `module` | `module.py` implementing `AgentModule` | assembler → `module_source` | `module/default` |
| `meta` | `template.md` / `operators.json` — the improver's own machinery | proposer & operators readers | `meta/improver-template`, `meta/operator-catalog` |
| `policy` | `policy.json` with `max_memory_chars` | assembler (memory cap) | `policy/context` |

IDs must be namespaced (`prompt/system`, not `system`) — the store rejects
anything without a `/`.

## Versions, hashing, and immutability

Each write creates `artifacts/<id>/vN/` with the payload files plus
`meta.json`:

```json
{"artifact_id": "prompt/system", "version": 2, "type": "prompt",
 "content_hash": "<sha256 of canonical payload, 16 hex>",
 "proposal_id": "g1p1", "generation": 1, "accepted": false,
 "edit_kind": "replace"}
```

- `content_hash` is a deterministic SHA-256 of the canonical payload JSON —
  identical content is detectable across versions.
- Writing an existing version raises (`version immutable`). There is no
  in-place edit anywhere in the framework.
- `accepted` flips to true only in `promote` — and mutating `meta.json`
  does not violate payload immutability (the hash covers payload only).

## Lineage — append-only history

`lineage.jsonl`, one JSON line per write:

```json
{"seq": 7, "artifact_id": "prompt/system", "op": "update",
 "from_v": 1, "to_v": 2, "proposal_id": "g1p1", "generation": 1,
 "content_hash": "…"}
```

Ops: `create | update | delete | restore`. **Rollback appends a `restore`
entry** (from the current version back to the target); `delete` marks
deactivation (version 0 in the checkout) but never removes files. The full
history of every artifact is reconstructible — `rsif inspect --artifact
prompt/system` prints it.

## The checkout — the active agent

`checkout.json` is a plain mapping `artifact_id → version` (version 0 =
deactivated). Three operations write it:

| Op | When | Guarantee |
|---|---|---|
| `promote(ApplyResult)` | engine acceptance (or seeding) | Only post-gate activation path |
| `restore(aid, version)` | `rsif rollback`, auto-rollback, META revert | Appends `restore` lineage |
| (never) apply | — | `apply_patch` is structurally checkout-free |

This is the core safety property of the store: **materializing a candidate
and activating it are different functions**, and only the engine calls the
second, after the gates. Tests assert byte-identical restoration on
rollback.

## Patches and ops

A `Patch` is a tuple of ops + `rationale` + `hypothesis` (falsifiable by
design):

- `CreateOp(artifact_id, type, payload)` — new artifact at v1
- `UpdateOp(artifact_id, payload, edit_kind)` — vN+1; `edit_kind` is
  `replace | append_section | edit_section | refine` (recorded, not
  interpreted by the store)
- `DeleteOp(artifact_id)` — deactivate
- `RestoreOp(artifact_id, version)` — roll back inside a patch

`apply_patch` executes ops in order and returns `ApplyResult({artifact_id:
candidate_version})` — the mapping the engine overlays onto the parent
snapshot to form the candidate. Bounded-edits discipline (`max_patch_ops`,
default 3) is enforced by the engine, not the store.

## The operator catalog — a typed mutation vocabulary

The improver cannot send arbitrary prose ops; it must name an **operator**
from the catalog, and the operator's declared surface must match the
proposal's surface. The catalog lives in the `meta/operator-catalog`
artifact (seeded by `operators_seed.seed_operator_catalog`, 9 operators):

```
prompt/refine          skill/add             skill/refine
memory/add-rule        memory/revise-rule    policy/bound-context
module/edit            meta/mutate-improver  meta/mutate-operators
```

Because the catalog is a META artifact, the vocabulary itself can evolve
(two-level, Promptbreeder-style) — under the slow cadence, approval, and
the META eval window. `evolve/operators.py` only *reads and validates
against* it; `render_operators()` shows the improver only the operators
whose surfaces are open this generation.

## Seeding

`store.seed_defaults(cfg)` creates and promotes the six seed artifacts (see
the table above) — a complete minimal agent: a careful-Python-solver prompt,
a one-section playbook, the improver template, the operator catalog, the
default single-shot module, and a generous context policy
(`max_memory_chars: 4000`). Everything the loop subsequently does is
versioned edits on top of these.

## Invariants (and where they're pinned)

1. Versions are immutable — writing vN twice raises (`test_store.py`).
2. Rollback restores byte-identical content and appends lineage
   (`test_store.py`, `test_safety.py`).
3. Lineage is append-only with parent refs — reconstructible per artifact
   (`test_store.py`).
4. `apply_patch` never touches the checkout — candidates are inert
   (`test_evolve.py::test_build_spec_overlays_candidate` asserts the
   active version is untouched while the candidate assembles differently).
5. Operator-surface mismatch is rejected (`test_evolve.py`,
   `validate_operator`).

## Pitfalls

- `read_version` skips `meta.json` — payload files only.
- `type_of` reads the *latest* version's meta; a candidate's type is the
  artifact's type (types never change across versions).
- Deleting then re-creating an id raises (`artifact already exists`) —
  restore instead.
