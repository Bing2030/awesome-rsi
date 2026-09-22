"""Shared constants: seed artifact ids used across the framework."""

from __future__ import annotations

# Canonical artifact ids created at `rsif init`.
SYSTEM_PROMPT_ID = "prompt/system"
PLAYBOOK_ID = "memory/playbook"
IMPROVER_TEMPLATE_ID = "meta/improver-template"
OPERATOR_CATALOG_ID = "meta/operator-catalog"
DEFAULT_MODULE_ID = "module/default"
CONTEXT_POLICY_ID = "policy/context"

DEFAULT_SYSTEM_PROMPT = """\
You are a careful Python-solving agent. Read the task, think, and answer with a
single ```python code block implementing the requested function exactly
(signature and name as specified). Prefer simple, correct, dependency-free
code. The block must be self-contained: only stdlib imports.
"""

DEFAULT_IMPROVER_TEMPLATE = """\
You are the Improver: a meta-agent that makes the agent better by proposing
ONE bounded, testable change (a patch of at most {max_ops} operations).

## Current agent
{checkout_summary}

## Archive frontier
{archive_summary}

## Train-split gaps (where the agent currently fails)
{gaps}

## Recent lessons (reflections & insights)
{lessons}

## Available operators
{operators}

## Guidelines
- Grounded only in the evidence above; cite the observation that motivates the change.
- Bounded edits: modify, add, or delete at most {max_ops} items (never rewrite everything).
- State a falsifiable hypothesis: what should improve and by roughly how much.
- Answer with a single JSON object, no prose outside it:
{{"surface": "prompt"|"skill"|"memory"|"module"|"meta",
  "operator": "<operator id>",
  "hypothesis": "...",
  "rationale": "...",
  "ops": [ {op_schema} ]}}
"""

# Default context-assembly policy: a generous bound on injected memory chars.
# The runtime (assembler) truncates the assembled memory to this cap. A
# cost-aware objective (see projects/harness_efficiency) rewards tightening it
# when memory is not load-bearing, and rejects tightening it past usefulness.
DEFAULT_CONTEXT_POLICY = '{\n  "max_memory_chars": 4000\n}'

# Source of the default architecture module (implements the module ABI).
DEFAULT_MODULE_CODE = '''\
"""Default agent architecture: build context once, one completion, submit."""


from rsif.runtime.module_api import (
    Action,
    AgentModule,
    LLMAction,
    ModuleContext,
    SubmitAction,
)


class Module(AgentModule):
    name = "default"

    def step(self, ctx: ModuleContext) -> Action:
        if not ctx.session.messages:
            return LLMAction()
        return SubmitAction()
'''

