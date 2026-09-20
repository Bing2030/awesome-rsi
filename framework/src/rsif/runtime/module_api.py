"""The stable module ABI: the architecture surface's fixed envelope.

An agent's architecture is a Python class implementing `AgentModule`. The
runtime drives it: it calls `step()` repeatedly and executes the returned
action (LLM call, tool call, reflection note, or submission). Modules can
restructure the loop (retry policies, self-critique passes, tool chaining)
but only ever see `ModuleContext` - never the store, engine, or sandbox
policy.

Grounding: ADAS "agent designs as executable code" [arXiv 2408.08435] and
Gödel Agent "behavior is code it can inspect and rewrite" [arXiv 2410.04444];
the envelope keeps the trust boundary of DGM [arXiv 2505.22954] intact.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from rsif.llm.base import CompletionResult, Message, ToolSpec, Usage


@dataclass
class LLMAction:
    """Ask the runtime to run one LLM call over the current session.

    `system` and `user` optionally override/seed the session preamble;
    when both are empty the runtime simply continues the existing history.
    """

    system: str = ""
    user: str = ""


@dataclass
class ToolAction:
    name: str
    arguments: str  # JSON string


@dataclass
class SubmitAction:
    result: str = ""  # empty = use the last assistant text


@dataclass
class ReflectAction:
    """Append a self-critique note to the session, then continue.

    Grounding: Self-Refine generator/critic/refiner [arXiv 2303.17651].
    The note is advisory context only - acceptance decisions elsewhere in
    the framework never rest on it [arXiv 2310.01798].
    """

    text: str


Action = LLMAction | ToolAction | SubmitAction | ReflectAction


@dataclass
class Session:
    """Mutable conversation state shared by the runtime and the module."""

    system: str = ""
    messages: list[Message] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def last_assistant_text(self) -> str:
        for m in reversed(self.messages):
            if m.role == "assistant" and m.content:
                return m.content
        return ""

    def add(self, message: Message) -> None:
        self.messages.append(message)

    def record_usage(self, result: CompletionResult) -> None:
        self.usage = self.usage.add(result.usage)


@dataclass
class ModuleContext:
    """Everything a module may see. No store, no engine, no sandbox config."""

    task_prompt: str
    session: Session
    tools: list[ToolSpec]
    steps_used: int = 0
    max_steps: int = 8
    last_completion: CompletionResult | None = None


class AgentModule(ABC):
    """The agent architecture contract. The default implementation is a
    single LLM call followed by submission; evolved modules may do more."""

    name: str = "unnamed-module"

    def setup(self, ctx: ModuleContext) -> None:  # optional hook
        pass

    @abstractmethod
    def step(self, ctx: ModuleContext) -> Action: ...


class DefaultModule(AgentModule):
    """Baseline: build context once, one completion, submit."""

    name = "default"

    def step(self, ctx: ModuleContext) -> Action:
        if not ctx.session.messages:
            return LLMAction()
        return SubmitAction()
