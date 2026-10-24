"""Anthropic Claude. Env: ANTHROPIC_API_KEY."""

from __future__ import annotations

import os
import time

from .base import LLMResponse, Provider


class AnthropicProvider(Provider):
    def __init__(self, model: str):
        from anthropic import Anthropic

        self.model = model
        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        t0 = time.perf_counter()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[
                {"role": "user", "content": user},
                # Prefill forces a JSON object; the pipeline re-attaches the brace.
                {"role": "assistant", "content": "{"},
            ],
        )
        text = "{" + "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return LLMResponse(
            text=text,
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=resp.model or self.model,
        )
