from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str  # raw model text; the pipeline parses it as JSON
    tokens_in: int
    tokens_out: int
    latency_ms: int
    model: str


class Provider(ABC):
    """One call: system + user text in, raw text out. JSON parsing and schema
    validation happen in the pipeline, not here, so a malformed answer is a
    soft failure of one ticket rather than an exception in the provider."""

    model: str

    @abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse: ...

    def cost_usd(self, tokens_in: int, tokens_out: int) -> float:
        """Price per 1M tokens comes from `pricing.yaml`; unknown models cost 0 and are flagged in the log."""
        from .pricing import price_for

        p_in, p_out = price_for(self.model)
        return (tokens_in * p_in + tokens_out * p_out) / 1_000_000
