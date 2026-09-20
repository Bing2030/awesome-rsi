"""Provider factory: turn a RunConfig into a (possibly cached) LLMProvider."""

from __future__ import annotations

import os

from rsif.config import RunConfig
from rsif.llm.base import LLMProvider
from rsif.llm.mock import ScriptedProvider


class ProviderError(Exception):
    pass


def provider_from_config(
    cfg: RunConfig,
    scripts: dict[str, list] | None = None,
    cache=None,
) -> LLMProvider:
    """Build the provider for a run.

    `scripts` is a ScriptedProvider script (test/offline mode).
    `cache` is an optional ResponseCache directory path.
    """
    provider_name = os.environ.get("RSIF_PROVIDER", cfg.provider)

    if provider_name == "scripted":
        provider: LLMProvider = ScriptedProvider(scripts)
    elif provider_name == "anthropic":
        provider = _anthropic(cfg)
    elif provider_name == "openai":
        provider = _openai(cfg)
    elif provider_name == "litellm":
        provider = _litellm(cfg)
    else:
        raise ProviderError(f"unknown provider: {provider_name!r}")

    if cache is not None:
        from rsif.llm.cache import CachedProvider, ResponseCache

        provider = CachedProvider(provider, ResponseCache(cache), name=provider_name)
    return provider


def _anthropic(cfg: RunConfig) -> LLMProvider:
    from rsif.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider(model=cfg.resolved_model(), temperature=cfg.temperature,
                             seed=cfg.seed, max_tokens=cfg.max_output_tokens)


def _openai(cfg: RunConfig) -> LLMProvider:
    from rsif.llm.openai_provider import OpenAIProvider

    return OpenAIProvider(model=cfg.resolved_model(), temperature=cfg.temperature,
                          seed=cfg.seed, max_tokens=cfg.max_output_tokens)


def _litellm(cfg: RunConfig) -> LLMProvider:
    from rsif.llm.litellm_provider import LiteLLMProvider

    return LiteLLMProvider(model=cfg.resolved_model(), temperature=cfg.temperature,
                           seed=cfg.seed, max_tokens=cfg.max_output_tokens)
