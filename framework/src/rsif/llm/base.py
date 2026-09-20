"""Provider-agnostic LLM interface.

A deliberately thin Protocol (three concepts: messages, tools, completion) so
the core stays stdlib-only, tests get a first-class scripted seam, and each
adapter stays ~100 LOC. Grounding: provider-agnostic requirement; the
model/evaluator split of FunSearch [nature-funsearch-2024] keeps the model
frozen while everything around it evolves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """A provider-level failure (rate limit, connection, auth, timeout).

    Distinct from an agent's own action failing: a provider error means *no*
    evaluation is trustworthy right now, so the runtime lets it propagate to
    abort the run cleanly rather than silently scoring the attempt 0.
    """

    def __init__(self, message: str, origin: str | None = None):
        super().__init__(message)
        # the underlying SDK/connection error's type name, preserved so the
        # run's stop_reason stays diagnostic (e.g. "error:RateLimitError").
        self.origin = origin or type(self).__name__


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_call_id: str = ""  # for role="tool"
    tool_calls: tuple["ToolCall", ...] = ()  # for role="assistant"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters_json: str = '{"type": "object", "properties": {}}'

    def parameters(self) -> dict:
        return json.loads(self.parameters_json)


@dataclass(frozen=True)
class CompletionRequest:
    messages: tuple[Message, ...]
    model: str = ""
    tools: tuple[ToolSpec, ...] = ()
    temperature: float = 0.7
    seed: int = 0
    max_tokens: int = 4096
    # routing hint so one ScriptedProvider can serve agent + improver roles
    role: str = "agent"


@dataclass(frozen=True)
class Usage:
    in_tokens: int = 0
    out_tokens: int = 0

    def add(self, other: "Usage") -> "Usage":
        return Usage(self.in_tokens + other.in_tokens, self.out_tokens + other.out_tokens)

    @property
    def total(self) -> int:
        return self.in_tokens + self.out_tokens


@dataclass(frozen=True)
class CompletionResult:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: str = "end_turn"  # end_turn | tool_use | max_tokens
    usage: Usage = field(default_factory=Usage)
    model: str = ""

    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMProvider(Protocol):
    """The single method every provider must implement."""

    def complete(self, req: CompletionRequest) -> CompletionResult: ...


def extract_code_fence(text: str, language: str = "python") -> str:
    """Return the contents of the first ```<language> fence, or the whole text."""
    marker = f"```{language}"
    if marker not in text:
        return text.strip()
    rest = text.split(marker, 1)[1]
    if rest.startswith("\n"):
        rest = rest[1:]
    if "```" in rest:
        rest = rest.split("```", 1)[0]
    return rest.strip()


def canonical_request_key(req: CompletionRequest, provider: str) -> str:
    """Stable cache key for a request (provider, model, messages, tools, params)."""
    payload = {
        "provider": provider,
        "model": req.model,
        "messages": [
            {"role": m.role, "content": m.content,
             "tool_call_id": m.tool_call_id,
             "tool_calls": [{"id": t.id, "name": t.name, "arguments": t.arguments}
                            for t in m.tool_calls]}
            for m in req.messages
        ],
        "tools": [{"name": t.name, "description": t.description,
                   "parameters": t.parameters()} for t in req.tools],
        "temperature": req.temperature,
        "seed": req.seed,
        "max_tokens": req.max_tokens,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
