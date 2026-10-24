"""OpenAI and OpenAI-compatible endpoints (set OPENAI_BASE_URL for others).

Env: OPENAI_API_KEY, optional OPENAI_BASE_URL.
"""

from __future__ import annotations

import os
import time

from .base import LLMResponse, Provider


class OpenAICompatProvider(Provider):
    def __init__(self, model: str):
        from openai import OpenAI  # imported lazily so the mock path has no dependency on it

        self.model = model
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ.get("OPENAI_BASE_URL"))

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        t0 = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        usage = resp.usage
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=resp.model or self.model,
        )
