"""LiteLLM adapter for the long tail of providers (Ollama, vLLM, etc.).

Optional extra: rsif[litellm]. Quarantined here so the core abstraction
stays thin and the rest of the package never imports litellm directly.
"""

from __future__ import annotations

from rsif.llm.base import (
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    ToolCall,
    Usage,
)


class LiteLLMProvider(LLMProvider):
    def __init__(self, model: str, temperature: float = 0.7, seed: int = 0,
                 max_tokens: int = 4096):
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.max_tokens = max_tokens

    def complete(self, req: CompletionRequest) -> CompletionResult:
        import litellm  # deferred import

        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        resp = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens or self.max_tokens,
        )
        msg = resp["choices"][0]["message"]
        tool_calls = tuple(
            ToolCall(id=t.get("id", ""), name=t["function"]["name"],
                     arguments=t["function"]["arguments"])
            for t in (msg.get("tool_calls") or [])
        )
        finish = resp["choices"][0].get("finish_reason", "stop")
        stop = "tool_use" if tool_calls else finish
        u = resp.get("usage", {}) or {}
        return CompletionResult(
            text=msg.get("content") or "", tool_calls=tool_calls, stop_reason=stop,
            usage=Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)),
            model=resp.get("model", ""))
