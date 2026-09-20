"""Operator catalog: the improver's typed mutation vocabulary.

Operators live in a META artifact (`meta/operator-catalog`) so the vocabulary
can itself evolve - including mutations of the mutation operators (the
self-referential two-level evolution of Promptbreeder [2309.16797] and
MetaSkill-Evolve [2607.05297]).

This module only *reads and validates against* the catalog; the catalog is
edited through the normal patch/accept loop like any other artifact.
"""

from __future__ import annotations

import json

from rsif.artifacts.store import ArtifactStore
from rsif.constants import OPERATOR_CATALOG_ID


def load_catalog(store: ArtifactStore, catalog_id: str = OPERATOR_CATALOG_ID) -> list[dict]:
    """Read the active operator catalog as a list of operator dicts."""
    payload = store.read_active(catalog_id)
    for name in ("operators.json", "catalog.json"):
        if name in payload:
            return json.loads(payload[name])
    # fall back to a single raw-JSON payload value, or join all values
    for value in payload.values():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            continue
    return []


def by_id(catalog: list[dict]) -> dict[str, dict]:
    return {op["id"]: op for op in catalog}


def render_operators(catalog: list[dict],
                     surfaces: set[str] | None = None) -> str:
    """Render the catalog for the improver, optionally filtered to the
    surfaces the scheduler has opened this generation."""
    lines = []
    for op in catalog:
        if surfaces is not None and op.get("surface") not in surfaces:
            continue
        lines.append(f"- {op['id']} ({op.get('surface', '?')}): "
                     f"{op.get('description', '')}")
    return "\n".join(lines)


def validate_operator(catalog: list[dict], operator: str, surface: str) -> bool:
    """A proposal's operator must exist and match the claimed surface."""
    for op in catalog:
        if op["id"] == operator:
            return op.get("surface") == surface
    return False


OP_SCHEMA = (
    '{"op": "create", "artifact_id": "skill/<name>", "type": "skill", '
    '"payload": {"module.py": "<code>", "manifest.json": "{\\"name\\": ...}"}} '
    '| {"op": "update", "artifact_id": "prompt/system", '
    '"payload": {"system.md": "<text>"}, "edit_kind": "replace"} '
    '| {"op": "delete", "artifact_id": "<id>"} '
    '| {"op": "restore", "artifact_id": "<id>", "version": N}'
)
