"""Deterministic in-memory providers for tests and offline demo runs.

- ScriptedProvider: pops responses from per-role queues, matched by a
  substring of the request text. Deterministic given the script.
- EchoProvider: returns a code-fence extraction of the request's own
  last user message - lets tests exercise "the agent writes Python"
  paths without a model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rsif.llm.base import (
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    Message,
    Usage,
    extract_code_fence,
)


def _request_text(req: CompletionRequest) -> str:
    return "\n".join(m.content for m in req.messages if m.role in ("system", "user"))


class ScriptedProvider(LLMProvider):
    """Returns responses from queues keyed by `role`, matched by a substring.

    A script entry is (match_substring, CompletionResult). The first entry
    whose `match` appears in the request text is consumed (popped), so a
    single script can drive a whole multi-generation evolution deterministically.
    """

    def __init__(self, scripts: dict[str, list[tuple[str, CompletionResult]]] | None = None):
        self.scripts: dict[str, list[tuple[str, CompletionResult]]] = scripts or {}
        self.calls: list[CompletionRequest] = []

    def add(self, role: str, match: str, result: CompletionResult) -> "ScriptedProvider":
        self.scripts.setdefault(role, []).append((match, result))
        return self

    def complete(self, req: CompletionRequest) -> CompletionResult:
        self.calls.append(req)
        queue = self.scripts.get(req.role, [])
        if not queue:
            raise AssertionError(f"no scripted response for role={req.role!r}")
        text = _request_text(req)
        for i, (match, result) in enumerate(queue):
            if match in text:
                queue.pop(i)
                return result
        raise AssertionError(
            f"no scripted response matches request (role={req.role!r}); "
            f"first 120 chars: {text[:120]!r}"
        )


def text_result(text: str, model: str = "scripted") -> CompletionResult:
    return CompletionResult(text=text, stop_reason="end_turn",
                            usage=Usage(1, len(text) // 4), model=model)


def tool_result(name: str, arguments: str, model: str = "scripted") -> CompletionResult:
    from rsif.llm.base import ToolCall

    return CompletionResult(
        text="", stop_reason="tool_use",
        tool_calls=(ToolCall(id="call_1", name=name, arguments=arguments),),
        usage=Usage(1, 1), model=model,
    )


class EchoProvider(LLMProvider):
    """Deterministically echoes back code blocks from the request.

    Useful for integration tests where the agent must produce runnable code:
    the test crafts a user message whose ```python fence IS the solution.
    """

    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.calls: list[CompletionRequest] = []

    def complete(self, req: CompletionRequest) -> CompletionResult:
        self.calls.append(req)
        last_user = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), "")
        code = extract_code_fence(last_user)
        return text_result(self.prefix + "```python\n" + code + "\n```"
                           if code else self.prefix + last_user)
