"""LLM providers behind one small interface.

`mock` is deterministic and needs no network or keys: CI and the eval harness
run on it. `openai_compat` covers OpenAI and any OpenAI-compatible endpoint.
`anthropic` is the native Claude client. Picked by name in `get_provider()`.
"""

from __future__ import annotations

from .base import LLMResponse, Provider


def get_provider(name: str, model: str | None = None, **kwargs) -> Provider:
    """kwargs are passed to the provider: `base_url`, `api_key_env` for OpenAI-compatible endpoints."""
    if name == "mock":
        from .mock import MockProvider

        return MockProvider(model=model or "mock-1")
    if name == "openai":
        from .openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(model=model or "gpt-4o-mini", **kwargs)
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=model or "claude-3-5-haiku-latest")
    raise ValueError(f"unknown provider {name!r}; use mock | openai | anthropic")


__all__ = ["Provider", "LLMResponse", "get_provider"]
