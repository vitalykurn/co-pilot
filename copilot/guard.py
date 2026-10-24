"""Rules that run after the model, in code.

The model proposes; these functions decide what reaches the agent:

1. Hard rules from the brief. Trading advice is declined with a fixed text.
   Complaints and KYC/AML cases always go to a person.
2. Grounding. Every citation must be a literal substring of a KB page. Every
   number in the draft must appear in a valid citation or in the ticket itself.
   A draft that fails either check is dropped and the ticket goes to a person.
3. Routing. Negative + high urgency, account lookups and unsupported languages
   go to a person even when the draft is fine.

A dropped draft is a soft failure: the ticket is not lost, the agent gets the
classification, the reasons, and whatever the model said in `kb_gap`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .kb import KnowledgeBase, normalize
from .schema import Citation, Decision, ModelOutput, Ticket

# --- hard rule: trading advice -------------------------------------------------

TRADING_ADVICE = re.compile(
    r"\b("
    r"signals?|buy or sell|should i (buy|sell|trade|open|close|enter|exit|hold|short|long)|"
    r"which (pair|instrument|stock|asset|coin|currency) (should|to) (i )?(buy|sell|trade)|"
    r"what (pair|instrument) (should|to) (i )?(buy|sell|trade)|"
    r"price target|where (is|will) .{0,30}(price|market) (go|head)|"
    r"(what|which) leverage (should|do you recommend|is best)|best leverage|"
    r"recommend (a |me |any )?(strategy|pair|leverage|trade|setup)|"
    r"double my (deposit|money|account)|guaranteed profit"
    r")\b"
    # Russian
    r"|\b(сигнал\w*|стоит ли (сейчас )?(покупать|продавать|заходить|входить|открывать|закрывать)|куда пойд[её]т (цена|курс|рынок)|"
    r"како[ей] плечо (лучше|выбрать|посоветуете)|что (купить|продать)|посоветуй\w* (пару|стратегию|плечо))"
    # Spanish
    r"|\b(señal(es)?|qué par (debo|debería) (comprar|vender|operar)|debo (comprar|vender)|precio objetivo|qué apalancamiento (debo|me recomienda))"
    # Indonesian
    r"|\b(sinyal|sebaiknya (saya )?(beli|jual|masuk|keluar)|leverage (apa|mana) yang (sebaiknya|terbaik)|target harga)",
    re.I | re.S,
)

# Advice-like language that must not appear in a draft the agent could send as-is.
ADVICE_IN_DRAFT = re.compile(
    r"\b(we recommend (that )?you (choose|use|select|buy|sell|trade|open)|you should (buy|sell|trade|choose|select|use) |"
    r"i (would )?(recommend|suggest) (buying|selling|trading|using|choosing|a leverage|1:)|"
    r"(buy|sell) (now|today|before)|will (rise|fall|go up|go down)|price target|"
    r"рекоменду\w* (вам )?(купить|продать|выбрать плечо|открыть)|советую (купить|продать)|"
    r"le recomendamos (comprar|vender|usar un apalancamiento))\b",
    re.I,
)

DECLINE_TEXT = {
    "en": (
        "Thank you for reaching out. We are not able to provide trading advice, recommendations, signals "
        "or forecasts, including suggestions on leverage or which instruments to trade. We are happy to help "
        "with any question about your account, deposits, withdrawals or verification."
    ),
    "ru": (
        "Спасибо за обращение. Мы не предоставляем торговых рекомендаций, сигналов и прогнозов, в том числе "
        "советов по выбору плеча или инструментов. Будем рады помочь с любым вопросом по счёту, пополнению, "
        "выводу средств или верификации."
    ),
    "es": (
        "Gracias por contactarnos. No podemos ofrecer asesoramiento de trading, recomendaciones, señales ni "
        "pronósticos, incluidas sugerencias sobre apalancamiento o qué instrumentos operar. Con gusto le "
        "ayudamos con cualquier consulta sobre su cuenta, depósitos, retiros o verificación."
    ),
    "id": (
        "Terima kasih telah menghubungi kami. Kami tidak dapat memberikan saran trading, rekomendasi, sinyal "
        "atau prediksi, termasuk saran mengenai leverage atau instrumen yang diperdagangkan. Kami siap membantu "
        "pertanyaan apa pun tentang akun, deposit, penarikan, atau verifikasi Anda."
    ),
}

HUMAN_ONLY_CATEGORIES = {"complaint", "kyc_aml"}

# Languages the agents can review a draft in. Anything else goes to a person untouched.
SUPPORTED_LANGUAGES = {"en", "ru", "es", "id", "ar", "pt", "zh", "vi", "th", "ms", "tr", "fr", "de", "hi", "ur"}

_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")


@dataclass
class GuardConfig:
    verify_citations: bool = True
    verify_numbers: bool = True
    escalate_negative_high: bool = True


@dataclass
class GuardOutcome:
    decision: Decision
    reasons: list[str] = field(default_factory=list)
    draft: str | None = None
    citations: list[Citation] = field(default_factory=list)


def is_trading_advice_request(text: str) -> bool:
    return bool(TRADING_ADVICE.search(text))


def verify_citations(citations: list[Citation], kb: KnowledgeBase) -> tuple[list[Citation], list[str]]:
    """Keep citations whose quote is literally in the KB. Fix the page slug if the model named the wrong page."""
    valid: list[Citation] = []
    reasons: list[str] = []
    for c in citations:
        found = kb.find_quote(c.quote, c.page)
        if found is None:
            found = kb.find_quote(c.quote)
            if found is not None:
                reasons.append(f"citation_page_corrected:{c.page}->{found}")
        if found is None:
            reasons.append("citation_not_in_kb")
            continue
        valid.append(Citation(page=found, quote=c.quote, url=kb.url_for(found)))
    return valid, reasons


def uncited_numbers(draft: str, citations: list[Citation], ticket_text: str) -> list[str]:
    """Numbers in the draft that appear neither in a citation nor in the ticket."""
    allowed = normalize(" ".join(c.quote for c in citations) + " " + ticket_text)
    allowed_numbers = set(_NUMBER.findall(allowed))
    missing = []
    for n in _NUMBER.findall(draft):
        if n not in allowed_numbers and n.replace(",", ".") not in allowed_numbers:
            missing.append(n)
    return missing


def apply(ticket: Ticket, out: ModelOutput | None, kb: KnowledgeBase, cfg: GuardConfig | None = None) -> GuardOutcome:
    cfg = cfg or GuardConfig()
    reasons: list[str] = []

    if out is None:
        return GuardOutcome("needs_human", ["model_output_invalid"])

    cls = out.classification
    lang = cls.language.lower()[:2]

    # 1. Hard rule: trading advice. Classifier OR regex, either is enough.
    if cls.category == "trading_advice" or is_trading_advice_request(ticket.text):
        reasons.append("hard_rule:trading_advice")
        if cls.category != "trading_advice":
            reasons.append("trading_advice_regex_override")
        return GuardOutcome("declined", reasons, DECLINE_TEXT.get(lang, DECLINE_TEXT["en"]), [])

    # 2. Grounding of whatever the model drafted.
    draft = out.draft
    citations = list(out.citations)
    if draft is not None:
        failures: list[str] = []
        if cfg.verify_citations:
            citations, cit_reasons = verify_citations(citations, kb)
            reasons.extend(cit_reasons)
            if not citations:
                failures.append("draft_dropped:no_valid_citation")
        if cfg.verify_numbers:
            missing = uncited_numbers(draft, citations, ticket.text)
            if missing:
                failures.append("draft_dropped:uncited_numbers:" + ",".join(missing))
        if ADVICE_IN_DRAFT.search(draft):
            failures.append("draft_dropped:advice_language")
        if failures:  # all checks run so the log shows every problem, not just the first
            reasons.extend(failures)
            draft = None
    else:
        citations = []
        reasons.append("kb_gap")

    # 3. Hard rule: a person decides complaints and KYC/AML. Draft, if any, stays as a hint.
    if cls.category in HUMAN_ONLY_CATEGORIES:
        reasons.append(f"hard_rule:human_decides:{cls.category}")
        return GuardOutcome("needs_human", reasons, draft, citations)

    # 4. Routing.
    if draft is None:
        return GuardOutcome("needs_human", reasons, None, [])
    if out.requires_account_lookup:
        reasons.append("account_lookup_required")
        return GuardOutcome("needs_human", reasons, draft, citations)
    if cfg.escalate_negative_high and cls.sentiment == "negative" and cls.urgency == "high":
        reasons.append("escalation:negative_high_urgency")
        return GuardOutcome("needs_human", reasons, draft, citations)
    if lang not in SUPPORTED_LANGUAGES:
        reasons.append(f"unsupported_language:{lang}")
        return GuardOutcome("needs_human", reasons, draft, citations)

    return GuardOutcome("draft_ready", reasons, draft, citations)
