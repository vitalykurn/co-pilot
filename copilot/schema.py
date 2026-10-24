"""Data contract for one ticket in, one result out.

Everything the model returns is validated against `ModelOutput`. Everything the
pipeline emits is a `Result`. A `Result` never has a "sent" state: the co-pilot
drafts, a person sends.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "deposit",
    "withdrawal",
    "account_opening",
    "verification",
    "trading_advice",
    "complaint",
    "kyc_aml",
    "other",
]
Urgency = Literal["low", "medium", "high"]
Sentiment = Literal["negative", "neutral", "positive"]
Decision = Literal["draft_ready", "needs_human", "declined"]


class Ticket(BaseModel):
    """Incoming support ticket. No real customer data is ever stored here."""

    ticket_id: str
    text: str
    subject: str | None = None
    channel: str | None = None  # e.g. "app", "email", "chat"


class Citation(BaseModel):
    page: str = Field(description="KB page slug, e.g. 'how-to-withdraw'")
    quote: str = Field(description="Exact substring of the KB page that supports the draft")
    url: str | None = None  # filled in by the pipeline from the KB manifest


class Classification(BaseModel):
    category: Category
    urgency: Urgency
    language: str = Field(description="ISO 639-1 code of the ticket language, e.g. 'en', 'ru'")
    sentiment: Sentiment


class ModelOutput(BaseModel):
    """What the LLM must return. Parsed with pydantic; anything else is a soft failure."""

    classification: Classification
    draft: str | None = Field(
        default=None,
        description="Reply draft in the ticket language, grounded only in the cited KB text. "
        "null when the KB does not cover the question.",
    )
    citations: list[Citation] = Field(default_factory=list)
    kb_gap: str | None = Field(
        default=None,
        description="One sentence on what the KB is missing: when draft is null, or next to a draft that "
        "answers only part of the question.",
    )
    requires_account_lookup: bool = Field(
        default=False,
        description="True when a correct answer depends on this customer's account or transaction state.",
    )


class Usage(BaseModel):
    model: str
    prompt_version: str
    kb_version: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class Result(BaseModel):
    """Final pipeline output for one ticket. Serialised to JSON and to the JSONL log."""

    ticket_id: str
    classification: Classification | None = None
    decision: Decision
    reasons: list[str] = Field(
        default_factory=list,
        description="Machine-readable reasons for the decision, e.g. 'kb_gap', 'citation_not_in_kb', 'hard_rule:trading_advice'",
    )
    draft: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    kb_gap: str | None = None
    requires_account_lookup: bool = False
    raw_model_output: ModelOutput | None = Field(
        default=None,
        description="What the model returned before the guards ran. Kept for eval and audit, not shown to agents.",
    )
    usage: Usage
