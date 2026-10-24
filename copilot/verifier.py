"""Optional second pass: does each sentence of the draft follow from the quotes?

The code-level guard proves that quotes exist in the KB and that numbers come
from quotes. It cannot tell that a valid quote was misread: "contact support if
not received within 24 hours" turned into "you will receive funds within 24
hours". That needs reading, so this pass asks a model one narrow question with
only the quotes and the draft in front of it, no ticket, no KB, no role-play.

It is a separate call with its own prompt version and cost, switched on per
configuration (`verify_claims`), so the eval shows what it buys.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .kb import ROOT
from .providers import Provider
from .schema import Citation

PROMPT = ROOT / "prompts" / "verify_v1.md"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


@dataclass
class ClaimCheck:
    unsupported: list[str]
    note: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    parse_ok: bool


def check_claims(provider: Provider, draft: str, citations: list[Citation]) -> ClaimCheck:
    quotes = "\n".join(f"- [{c.page}] {c.quote}" for c in citations) or "- (none)"
    user = f"Quotes from the knowledge base:\n{quotes}\n\nDraft reply:\n{draft}"
    resp = provider.complete(PROMPT.read_text(encoding="utf-8"), user, max_tokens=400)
    cleaned = _FENCE.sub("", resp.text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    try:
        data = json.loads(cleaned[start : end + 1])
        unsupported = [str(s) for s in data.get("unsupported", [])]
        return ClaimCheck(unsupported, str(data.get("note", "")), resp.tokens_in, resp.tokens_out, resp.latency_ms, True)
    except (ValueError, AttributeError):
        # Unparseable verdict: fail closed, the draft goes to a person.
        return ClaimCheck(["<verifier output unparseable>"], "", resp.tokens_in, resp.tokens_out, resp.latency_ms, False)
