"""Anthropic Messages API adapter (optional extra: rsif[anthropic])."""

from __future__ import annotations

from rsif.llm.base import (
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    ToolCall,
    Usage,
)


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, temperature: float = 0.7, seed: int = 0,
                 max_tokens: int = 4096, client=None):
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.max_tokens = max_tokens
        self._client = client
        self._temp_ok: bool | None = None  # probed on first call

    def _get_client(self):
        if self._client is not None:
            return self._client
        import anthropic  # deferred import; only needed when actually used

        self._client = anthropic.Anthropic()
        return self._client

    def _accepts_temperature(self) -> bool:
        if self._temp_ok is None:
            import inspect

            params = inspect.signature(self._get_client().messages.create).parameters
            self._temp_ok = "temperature" in params
        return self._temp_ok

    def complete(self, req: CompletionRequest) -> CompletionResult:
        client = self._get_client()
        kwargs: dict = dict(
            model=self.model,
            max_tokens=req.max_tokens or self.max_tokens,
            messages=[{"role": m.role, "content": m.content}
                      for m in req.messages if m.role != "system"],
        )
        # newer Messages SDKs / Anthropic-protocol proxies may not accept
        # `temperature`; send it only when the endpoint's signature does.
        if self._accepts_temperature():
            kwargs["temperature"] = req.temperature
        system = "\n\n".join(m.content for m in req.messages if m.role == "system")
        if system:
            kwargs["system"] = system

        tools = _anthropic_tools(req)
        if tools:
            kwargs["tools"] = tools

        resp = client.messages.create(**kwargs)

        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text")
        tool_calls = tuple(
            ToolCall(id=getattr(b, "id", ""), name=b.name,
                     arguments=str(b.input))
            for b in resp.content if getattr(b, "type", "") == "tool_use"
        )
        stop = resp.stop_reason or "end_turn"
        if stop == "tool_use" and tool_calls:
            pass  # keep
        usage = Usage(resp.usage.input_tokens, resp.usage.output_tokens)
        return CompletionResult(text=text, tool_calls=tool_calls, stop_reason=stop,
                                usage=usage, model=resp.model)


def _anthropic_tools(req: CompletionRequest) -> list[dict]:
    out = []
    for t in req.tools:
        out.append({
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters(),
        })
    return out
