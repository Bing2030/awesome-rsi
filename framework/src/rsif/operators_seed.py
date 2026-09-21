"""Seed operator catalog: the typed mutation vocabulary per surface.

Operators are the improver's action vocabulary. The catalog itself is a META
artifact, so the vocabulary can evolve - including mutations of the mutation
operators (self-referential two-level evolution).

Grounding: Promptbreeder evolves task prompts AND mutation prompts
[arXiv 2309.16797]; MetaSkill-Evolve separates fast task-skill edits from
slow meta-skill edits [arXiv 2607.05297]; higher-order self-referential
evolution [openreview 3tk6AES1Aj].
"""

from __future__ import annotations

OP_SCHEMA_HINT = (
    '{"op": "create", "artifact_id": "skill/<name>", "type": "skill", '
    '"payload": {"module.py": "<code>", "manifest.json": "{\\"name\\": ...}"}}'
)


def seed_operator_catalog() -> list[dict]:
    return [
        # -- prompt surface [2309.03409, 2309.16797] ------------------------
        {
            "id": "prompt/refine",
            "surface": "prompt",
            "description": "Refine the system prompt with one targeted guideline, "
                           "example, or wording change grounded in observed failures.",
        },
        # -- skill surface [2305.16291, 2603.18000] --------------------------
        {
            "id": "skill/add",
            "surface": "skill",
            "description": "Add a new executable skill (code + manifest) that must "
                           "pass its self-tests in the sandbox before activation.",
        },
        {
            "id": "skill/refine",
            "surface": "skill",
            "description": "Refine an existing skill using its execution feedback "
                           "(fix bugs, broaden inputs, speed up).",
        },
        # -- memory surface [2510.04618, 2308.10144] -------------------------
        {
            "id": "memory/add-rule",
            "surface": "memory",
            "description": "Add one playbook rule distilled from verified experience.",
        },
        {
            "id": "memory/revise-rule",
            "surface": "memory",
            "description": "Revise or delete a playbook rule that correlated with "
                           "failures; keep edits bounded.",
        },
        # -- policy surface [2609.20519] -------------------------------------
        {
            "id": "policy/bound-context",
            "surface": "policy",
            "description": "Tighten or loosen the context-assembly bound (max injected "
                           "memory characters), trading context cost against recall.",
        },
        # -- architecture surface [2408.08435, 2410.04444, 2505.22954] -------
        {
            "id": "module/edit",
            "surface": "module",
            "description": "Edit the agent's architecture module (retry policies, "
                           "self-critique passes, tool chaining) within the module ABI.",
        },
        # -- meta surface: the improver improving itself [2310.02304, -------
        #    2309.16797, 2607.05297]                                         -------
        {
            "id": "meta/mutate-improver",
            "surface": "meta",
            "description": "Mutate the improver's own prompt template (how proposals "
                           "are made). Slow loop; requires approval.",
        },
        {
            "id": "meta/mutate-operators",
            "surface": "meta",
            "description": "Add/revise an operator in the mutation vocabulary itself. "
                           "Slow loop; requires approval.",
        },
    ]
