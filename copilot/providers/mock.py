"""Deterministic stand-in for an LLM.

It does keyword matching against the ticket text and returns a `ModelOutput`
JSON whose citations are real substrings of the KB snapshots. It exists so the
pipeline, the guards and the eval harness can run in CI with no keys. Its
quality numbers are not the point and are reported separately from live runs.
"""

from __future__ import annotations

import json
import re
import time

from .base import LLMResponse, Provider

# (regex on ticket text, category, page, quote, draft)
_RULES: list[tuple[str, str, str | None, str | None, str | None]] = [
    (
        r"\b(signal|buy|sell|which pair|should i (trade|open|enter)|price target|what leverage|best leverage|recommend)\b",
        "trading_advice",
        None,
        None,
        None,
    ),
    (r"\b(stole|scam|fraud|complain|complaint|lawyer|regulator|unacceptable)\b", "complaint", None, None, None),
    (r"\b(rejected|declined|frozen|blocked|suspended|aml|source of funds)\b.*\b(document|verification|kyc|account)\b|\b(document|verification|kyc)\b.*\b(rejected|declined)\b", "kyc_aml", None, None, None),
    (
        r"\b(minimum deposit|min deposit)\b",
        "deposit",
        "how-to-deposit",
        "The minimum deposit starts from 8 USD, depending on the account type.",
        "The minimum deposit starts from 8 USD and depends on your account type.",
    ),
    (
        r"\bdeposit\b.*\b(how long|when|credited|not (showing|arrived))\b|\b(how long|when)\b.*\bdeposit\b",
        "deposit",
        "how-to-deposit",
        "Deposits are instant! You will be able to view your updated account balance within 60 minutes.",
        "Deposits are instant and your updated balance should be visible within 60 minutes.",
    ),
    (
        r"\bwithdraw\w*\b.*\b(pending)\b|\bpending\b.*\bwithdraw",
        "withdrawal",
        "how-to-withdraw",
        "This means your request in in queue and in the midst of getting processed. Once approved, you will be notified.",
        "A 'pending' status means your withdrawal request is in the queue and being processed. You will be notified once it is approved.",
    ),
    (
        r"\bwithdraw\w*\b.*\b(how long|when|days|take|fee|commission|minimum)\b",
        "withdrawal",
        None,
        None,
        None,
    ),
    (
        r"\bwithdraw",
        "withdrawal",
        "how-to-withdraw",
        "Should you not receive your funds within 24 hours, please reach out to our friendly support team for assistance.",
        "If you have not received your funds within 24 hours of your withdrawal request, please contact support.",
    ),
    (
        r"\b(document|documents|proof of|passport|utility bill|bank statement)\b",
        "verification",
        "how-to-open-an-account",
        "we will require a Proof of identification and Proof of address via a bank statement or a utility bill that are not older than 6 months",
        "For a live account we require proof of identification and proof of address (a bank statement or utility bill not older than 6 months), with your name clearly visible.",
    ),
    (
        r"\b(verif\w+|kyc)\b.*\b(how long|when|take|days|hours)\b|\b(how long|when)\b.*\b(verif\w+|kyc)\b",
        "verification",
        "how-to-open-an-account",
        "Account opening and document verification will be completed within 48 hours.",
        "Account opening and document verification are completed within 48 hours.",
    ),
    (r"\b(verif\w+|kyc)\b", "verification", None, None, None),
    (
        r"\b(open|create|register|sign up)\b.*\baccount\b",
        "account_opening",
        "how-to-open-an-account",
        "Visit www.valetax.com and click on ' Create Account ' at the top right of the page",
        "To open an account, visit www.valetax.com and click 'Create Account' at the top right of the page, then enter your details.",
    ),
    (
        r"\b(islamic|swap)\b",
        "account_opening",
        "how-to-open-an-account",
        "All our account are Islamic friendly and there is no swap is credited or withdrawn from all trading account.",
        "All our accounts are Islamic-friendly: no swap is credited or withdrawn on any trading account.",
    ),
]

_NEGATIVE = re.compile(r"\b(angry|stole|scam|unacceptable|still|again|urgent|asap|immediately|!!)\b", re.I)
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_ARABIC = re.compile(r"[\u0600-\u06ff]")


class MockProvider(Provider):
    def __init__(self, model: str = "mock-1"):
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        t0 = time.perf_counter()
        ticket = user.lower()
        category, page, quote, draft = "other", None, None, None
        for pattern, cat, pg, q, d in _RULES:
            if re.search(pattern, ticket, re.I | re.S):
                category, page, quote, draft = cat, pg, q, d
                break
        language = "ru" if _CYRILLIC.search(user) else "ar" if _ARABIC.search(user) else "en"
        negative = bool(_NEGATIVE.search(user)) or category in ("complaint", "kyc_aml")
        out = {
            "classification": {
                "category": category,
                "urgency": "high" if negative else "medium" if category in ("withdrawal", "kyc_aml") else "low",
                "language": language,
                "sentiment": "negative" if negative else "neutral",
            },
            "draft": draft,
            "citations": [{"page": page, "quote": quote}] if quote else [],
            "kb_gap": None if draft or category in ("trading_advice", "complaint", "kyc_aml") else "KB does not cover this question.",
        }
        text = json.dumps(out, ensure_ascii=False)
        return LLMResponse(
            text=text,
            tokens_in=len(system.split()) + len(user.split()),
            tokens_out=len(text.split()),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=self.model,
        )
