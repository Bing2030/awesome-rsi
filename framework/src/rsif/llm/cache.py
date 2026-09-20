"""Disk response cache.

Keyed on (provider, model, canonical request, seed, temperature, max_tokens),
so identical calls are not re-sent - the payoff is both deterministic replay
of evolution runs (test goldens) and not re-paying for repeated improver /
agent calls across generations.

Grounding: cost blowout mitigation [AlphaEvolve cascade evals 2506.13131];
the cache is a key ingredient of run reproducibility.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rsif.llm.base import CompletionRequest, CompletionResult, canonical_request_key


class ResponseCache:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _key(self, provider: str, req: CompletionRequest) -> str:
        digest = hashlib.sha256(
            canonical_request_key(req, provider).encode("utf-8")).hexdigest()
        return digest

    def _entry_path(self, key: str) -> Path:
        return self.path / f"{key}.json"

    def get(self, provider: str, req: CompletionRequest) -> CompletionResult | None:
        p = self._entry_path(self._key(provider, req))
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        from rsif.llm.base import ToolCall, Usage

        return CompletionResult(
            text=data["text"],
            tool_calls=tuple(ToolCall(id=t["id"], name=t["name"], arguments=t["arguments"])
                             for t in data["tool_calls"]),
            stop_reason=data.get("stop_reason", "end_turn"),
            usage=Usage(data.get("in_tokens", 0), data.get("out_tokens", 0)),
            model=data.get("model", ""),
        )

    def put(self, provider: str, req: CompletionRequest, result: CompletionResult) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        data = {
            "text": result.text,
            "tool_calls": [{"id": t.id, "name": t.name, "arguments": t.arguments}
                           for t in result.tool_calls],
            "stop_reason": result.stop_reason,
            "in_tokens": result.usage.in_tokens,
            "out_tokens": result.usage.out_tokens,
            "model": result.model,
        }
        self._entry_path(self._key(provider, req)).write_text(
            json.dumps(data, sort_keys=True), encoding="utf-8")


class CachedProvider:
    """Wraps a provider with the disk cache, emitting a cached flag via the
    returned event (the caller records llm_call{cached:true/false})."""

    def __init__(self, provider, cache: ResponseCache, name: str = ""):
        self.provider = provider
        self.cache = cache
        self.name = name
        self.hits = 0
        self.misses = 0

    def complete(self, req: CompletionRequest) -> CompletionResult:
        cached = self.cache.get(self.name, req)
        if cached is not None:
            self.hits += 1
            return cached
        result = self.provider.complete(req)
        self.cache.put(self.name, req, result)
        self.misses += 1
        return result
