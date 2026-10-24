"""One ticket in, one Result out, one JSONL line in the log."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from pydantic import ValidationError

from . import guard
from .kb import KnowledgeBase, ROOT
from .pii import mask
from .providers import Provider
from .schema import ModelOutput, Result, Ticket, Usage

PROMPTS_DIR = ROOT / "prompts"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def load_prompt(version: str, kb: KnowledgeBase) -> str:
    template = (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")
    return template.replace("{{KB}}", kb.context_for())


def parse_model_output(text: str) -> ModelOutput | None:
    """Lenient JSON parse + strict schema validation. None on any failure."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return ModelOutput.model_validate(json.loads(cleaned[start : end + 1]))
    except (json.JSONDecodeError, ValidationError):
        return None


class Copilot:
    def __init__(
        self,
        provider: Provider,
        kb: KnowledgeBase | None = None,
        prompt_version: str = "draft_v1",
        guard_config: guard.GuardConfig | None = None,
        log_path: Path | None = None,
    ):
        self.provider = provider
        self.kb = kb or KnowledgeBase.load()
        self.prompt_version = prompt_version
        self.system_prompt = load_prompt(prompt_version, self.kb)
        self.guard_config = guard_config or guard.GuardConfig()
        self.log_path = log_path

    def process(self, ticket: Ticket) -> Result:
        t0 = time.perf_counter()
        masked = mask(ticket.text)
        user = f"<ticket id=\"{ticket.ticket_id}\">\n{masked}\n</ticket>"
        if ticket.subject:
            user = f"Subject: {mask(ticket.subject)}\n" + user

        try:
            resp = self.provider.complete(self.system_prompt, user)
            raw_text, tokens_in, tokens_out, model = resp.text, resp.tokens_in, resp.tokens_out, resp.model
        except Exception as exc:  # provider/network failure is a soft failure of this ticket
            raw_text, tokens_in, tokens_out, model = "", 0, 0, self.provider.model
            provider_error = f"provider_error:{type(exc).__name__}"
        else:
            provider_error = None

        out = parse_model_output(raw_text) if raw_text else None
        verdict = guard.apply(ticket.model_copy(update={"text": masked}), out, self.kb, self.guard_config)
        if provider_error:
            verdict.reasons.insert(0, provider_error)

        result = Result(
            ticket_id=ticket.ticket_id,
            classification=out.classification if out else None,
            decision=verdict.decision,
            reasons=verdict.reasons,
            draft=verdict.draft,
            citations=verdict.citations,
            kb_gap=out.kb_gap if out else None,
            requires_account_lookup=out.requires_account_lookup if out else False,
            raw_model_output=out,
            usage=Usage(
                model=model,
                prompt_version=self.prompt_version,
                kb_version=self.kb.version,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=round(self.provider.cost_usd(tokens_in, tokens_out), 6),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            ),
        )
        self._log(result, masked)
        return result

    def _log(self, result: Result, masked_text: str) -> None:
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = result.model_dump(mode="json", exclude={"raw_model_output"})
        line["ticket_text_masked"] = masked_text
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
