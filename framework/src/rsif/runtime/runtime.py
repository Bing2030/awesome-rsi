"""AgentRuntime: run an AgentSpec against a task via its architecture module.

The runtime is deliberately boring - it interprets the spec, whose module
(code), prompts, skills, and memory all evolve. It dispatches actions the
module returns (LLM call, tool call, reflection note, submit) and enforces
budget. Tool calls (skills) execute in the sandbox; results are appended as
tool messages so the agent can iterate [Voyager 2305.16291 execution feedback].
"""

from __future__ import annotations

import json
import time

from rsif.llm.base import (
    CompletionRequest,
    LLMProvider,
    Message,
    ProviderError,
    ToolSpec,
)
from rsif.runtime.module_api import (
    LLMAction,
    ModuleContext,
    ReflectAction,
    Session,
    SubmitAction,
    ToolAction,
)
from rsif.runtime.types import Attempt, TraceStep
from rsif.spec import AgentSpec, SkillSpec


class AgentRuntime:
    def __init__(self, provider: LLMProvider, sandbox=None, default_max_steps: int = 8,
                 max_output_tokens: int = 4096, temperature: float = 0.7,
                 seed: int = 0):
        self.provider = provider
        self.sandbox = sandbox
        self.default_max_steps = default_max_steps
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.seed = seed

    # -- entry ----------------------------------------------------------------

    def run(self, task_prompt: str, spec: AgentSpec,
            max_steps: int | None = None, role: str = "agent") -> Attempt:
        max_steps = max_steps or self.default_max_steps
        start = time.monotonic()

        session = Session(system=spec.compose_system())
        module_cls = self._load_module(spec)
        module = module_cls()
        ctx = ModuleContext(
            task_prompt=task_prompt, session=session,
            tools=self._tool_specs(spec.skills),
            max_steps=max_steps,
        )
        module.setup(ctx)
        trace: list[TraceStep] = []

        try:
            for _ in range(max_steps):
                ctx.steps_used += 1
                action = module.step(ctx)
                if isinstance(action, SubmitAction):
                    result = action.result or session.last_assistant_text()
                    trace.append(TraceStep("submit", result))
                    return Attempt(
                        task_id="", result=result, ok=True, usage=session.usage,
                        steps=ctx.steps_used, wall_s=time.monotonic() - start,
                        trace=trace,
                    )
                if isinstance(action, LLMAction):
                    result = self._llm(ctx, action, spec, role)
                    ctx.last_completion = result
                    trace.append(TraceStep("llm_call", result.text,
                                           {"tool_calls": len(result.tool_calls),
                                            "stop_reason": result.stop_reason}))
                elif isinstance(action, ToolAction):
                    observation = self._tool(ctx, action, spec)
                    trace.append(TraceStep("tool_result", observation))
                elif isinstance(action, ReflectAction):
                    session.add(Message("assistant", f"[self-critique] {action.text}"))
                    trace.append(TraceStep("reflect", action.text))
                else:
                    raise RuntimeError(f"unknown action: {action!r}")

            # budget exhausted without submission
            return Attempt(
                task_id="", result=session.last_assistant_text(), ok=False,
                usage=session.usage, steps=ctx.steps_used,
                wall_s=time.monotonic() - start, trace=trace,
                error="max_steps exhausted",
            )
        except ProviderError:
            # a provider/connection failure means no evaluation is trustworthy:
            # propagate so the engine aborts cleanly rather than scoring 0.
            raise
        except Exception as e:  # noqa: BLE001 - capture, don't crash the loop
            return Attempt(
                task_id="", result=session.last_assistant_text(), ok=False,
                usage=session.usage, steps=ctx.steps_used,
                wall_s=time.monotonic() - start, trace=trace, error=str(e),
            )

    # -- internals --------------------------------------------------------------

    def _load_module(self, spec: AgentSpec):
        from rsif.runtime.loader import load_module_source

        source = spec.module_source or _DEFAULT_MODULE
        return load_module_source(source)

    def _tool_specs(self, skills: list[SkillSpec]) -> list[ToolSpec]:
        return [ToolSpec(name=s.name, description=s.description,
                         parameters_json='{"type": "object", "properties": {}}')
                for s in skills]

    def _llm(self, ctx: ModuleContext, action: LLMAction, spec: AgentSpec,
             role: str):
        history = list(ctx.session.messages)
        if action.user:
            history = [Message("user", action.user)] + history
        elif not history:
            history = [Message("user", ctx.task_prompt)]
        # the evolved system prompt is real request context: always present
        system = action.system or ctx.session.system
        messages = ([Message("system", system)] if system else []) + history

        req = CompletionRequest(
            messages=tuple(messages),
            tools=tuple(ctx.tools),
            temperature=self.temperature,
            seed=self.seed,
            max_tokens=self.max_output_tokens,
            role=role,
        )
        result = self.provider.complete(req)
        ctx.session.record_usage(result)
        ctx.session.add(Message("assistant", result.text, tool_calls=result.tool_calls))
        return result

    def _tool(self, ctx: ModuleContext, action: ToolAction, spec: AgentSpec) -> str:
        skill = {s.name: s for s in spec.skills}.get(action.name)
        if skill is None:
            obs = f"error: unknown skill {action.name!r}"
        else:
            obs = self._run_skill(skill, action.arguments)
        ctx.session.add(Message("tool", obs, tool_call_id=action.name))
        ctx.session.add(Message("user", f"Tool {action.name} returned:\n{obs}"))
        return obs

    def _run_skill(self, skill: SkillSpec, args_json: str) -> str:
        from rsif.sandbox.exec import run_python

        runner = _SKILL_RUNNER.format(skill_code=skill.code, args=args_json)
        outcome = run_python(runner)
        if outcome.ok:
            return outcome.stdout.strip() or "(no output)"
        return f"error: {outcome.error_text}"


_SKILL_RUNNER = """\
{skill_code}

import json as _json
_args = _json.loads({args!r})
_result = main(**_args)
print(_result)
"""


_DEFAULT_MODULE = '''\
from rsif.runtime.module_api import (
    AgentModule, LLMAction, ModuleContext, SubmitAction, Action)


class Module(AgentModule):
    name = "default"

    def step(self, ctx: ModuleContext) -> Action:
        if not ctx.session.messages:
            return LLMAction()
        return SubmitAction()
'''
