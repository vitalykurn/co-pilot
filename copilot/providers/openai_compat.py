"""Any OpenAI-compatible chat endpoint: OpenAI, Google Gemini, Alibaba DashScope (Qwen),
DeepSeek, Groq, OpenRouter, a local server.

Which endpoint is decided by `base_url` and `api_key_env`, both settable per
eval configuration. Defaults come from OPENAI_BASE_URL / OPENAI_API_KEY.
"""

from __future__ import annotations

import os
import time

from .base import LLMResponse, Provider


class OpenAICompatProvider(Provider):
    def __init__(self, model: str, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY"):
        from openai import OpenAI  # imported lazily so the mock path has no dependency on it

        self.model = model
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(f"{api_key_env} is not set; put it in the environment or in api_key.env")
        self._client = OpenAI(api_key=api_key, base_url=base_url or os.environ.get("OPENAI_BASE_URL"), max_retries=2, timeout=90)

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        from openai import APIStatusError, RateLimitError

        t0 = time.perf_counter()
        attempts, delay = 5, 2.0
        for attempt in range(1, attempts + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                )
                break
            except RateLimitError:
                if attempt == attempts:
                    raise
            except APIStatusError as exc:
                # 5xx and gateway hiccups are worth a retry; 4xx other than 429 are not.
                if attempt == attempts or exc.status_code < 500:
                    raise
            time.sleep(delay)
            delay = min(delay * 2, 30)
        usage = resp.usage
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=resp.model or self.model,
        )
