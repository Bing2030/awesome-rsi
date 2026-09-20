"""Assembler: resolve a version mapping into a runnable AgentSpec.

The engine evaluates *candidate* checkouts, so the assembler takes an explicit
artifact_id -> version mapping (the parent checkout with a candidate's patch
overlaid) rather than reading the active checkout. This is what keeps apply /
evaluate / accept decoupled: candidates are materialized, assembled, and
scored without disturbing the active agent until acceptance.
"""

from __future__ import annotations

import json

from rsif.artifacts.model import ArtifactType
from rsif.artifacts.store import ArtifactStore
from rsif.memory.playbook import parse_playbook, render as render_playbook
from rsif.spec import AgentSpec, SkillSpec


def build_spec(store: ArtifactStore, mapping: dict[str, int],
               extra_memory: str = "") -> AgentSpec:
    spec = AgentSpec()
    memories: list[str] = []

    for aid in sorted(mapping):
        version = mapping[aid]
        if version == 0:  # deleted in this candidate
            continue
        atype = store.type_of(aid)
        payload = store.read_version(aid, version)

        if atype == ArtifactType.PROMPT:
            spec.system_prompt = _first_text(payload)
        elif atype == ArtifactType.SKILL:
            spec.skills.append(_skill(aid, payload))
        elif atype == ArtifactType.MEMORY:
            memories.append(_memory(payload))
        elif atype == ArtifactType.MODULE:
            spec.module_source = _first_text(payload)
            spec.module_path = str(store.version_dir(aid, version))
        # META artifacts are not part of the agent's runtime spec

    spec.memory = "\n\n".join(m for m in memories if m)
    if extra_memory:
        spec.memory = (spec.memory + "\n\n" + extra_memory).strip()
    return spec


def _first_text(payload: dict[str, str]) -> str:
    for name in ("system.md", "module.py", "prompt.md", "code.py"):
        if name in payload:
            return payload[name]
    return next(iter(payload.values()), "")


def _skill(aid: str, payload: dict[str, str]) -> SkillSpec:
    code = ""
    for name in ("module.py", "code.py"):
        if name in payload:
            code = payload[name]
            break
    if not code:
        code = next((v for k, v in payload.items() if k.endswith(".py")), "")

    manifest: dict = {}
    for name in ("manifest.json", "skill.json"):
        if name in payload:
            try:
                manifest = json.loads(payload[name])
            except json.JSONDecodeError:
                manifest = {}
            break

    name = manifest.get("name") or aid.split("/")[-1]
    description = manifest.get("description", "")
    return SkillSpec(name=name, description=description, code=code)


def _memory(payload: dict[str, str]) -> str:
    if "playbook.json" in payload:
        try:
            return render_playbook(parse_playbook(payload["playbook.json"]))
        except (json.JSONDecodeError, KeyError):
            return payload["playbook.json"]
    return "\n\n".join(payload.values())
