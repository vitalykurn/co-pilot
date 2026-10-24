"""Anthropic Claude. Env: ANTHROPIC_API_KEY."""

from __future__ import annotations

import os
import time

from .base import LLMResponse, Provider


class AnthropicProvider(Provider):
    def __init__(self, model: str):
        from anthropic import Anthropic

        self.model = model
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set; put it in the environment or in api_key.env")
        # Retries are handled here so a 429 waits instead of failing the ticket immediately.
        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=0, timeout=90)

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        from anthropic import APIStatusError, RateLimitError

        # Current models reject `temperature` and reject an assistant prefill.
        # JSON is extracted from the text by the pipeline, fences included.
        t0 = time.perf_counter()
        attempts, delay = 5, 2.0
        for attempt in range(1, attempts + 1):
            try:
                resp = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                break
            except RateLimitError:
                if attempt == attempts:
                    raise
            except APIStatusError as exc:
                if attempt == attempts or exc.status_code < 500:
                    raise
            time.sleep(delay)
            delay = min(delay * 2, 30)
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return LLMResponse(
            text=text,
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=resp.model or self.model,
        )
