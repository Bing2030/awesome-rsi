"""OpenAI chat-completions adapter (optional extra: rsif[openai])."""

from __future__ import annotations

from rsif.llm.base import (
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    ToolCall,
    Usage,
)


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str, temperature: float = 0.7, seed: int = 0,
                 max_tokens: int = 4096, client=None):
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.max_tokens = max_tokens
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        import openai  # deferred import

        self._client = openai.OpenAI()
        return self._client

    def complete(self, req: CompletionRequest) -> CompletionResult:
        client = self._get_client()
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens or self.max_tokens,
        )
        tools = _openai_tools(req)
        if tools:
            kwargs["tools"] = tools
        if req.tools:
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        tool_calls = tuple(
            ToolCall(id=t.id, name=t.function.name, arguments=t.function.arguments)
            for t in (msg.tool_calls or [])
        )
        stop = resp.choices[0].finish_reason or "stop"
        stop = "tool_use" if tool_calls else stop
        usage = Usage(getattr(resp.usage, "prompt_tokens", 0) or 0,
                      getattr(resp.usage, "completion_tokens", 0) or 0)
        return CompletionResult(text=msg.content or "", tool_calls=tool_calls,
                                stop_reason=stop, usage=usage, model=resp.model)


def _openai_tools(req: CompletionRequest) -> list[dict]:
    return [{
        "type": "function",
        "function": {"name": t.name, "description": t.description,
                     "parameters": t.parameters()},
    } for t in req.tools]
