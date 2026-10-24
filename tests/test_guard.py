"""The guards are the product. Each hard rule and each grounding check has a test."""

from copilot import guard
from copilot.kb import KnowledgeBase
from copilot.schema import Citation, Classification, ModelOutput, Ticket

KB = KnowledgeBase.load()
MIN_DEPOSIT = "The minimum deposit starts from 8 USD, depending on the account type."


def _out(category="deposit", draft=None, citations=(), lang="en", sentiment="neutral", urgency="low", lookup=False):
    return ModelOutput(
        classification=Classification(category=category, urgency=urgency, language=lang, sentiment=sentiment),
        draft=draft,
        citations=list(citations),
        requires_account_lookup=lookup,
    )


def _ticket(text="What is the minimum deposit?"):
    return Ticket(ticket_id="t", text=text)


def test_grounded_draft_is_ready():
    out = _out(draft="The minimum deposit starts from 8 USD.", citations=[Citation(page="how-to-deposit", quote=MIN_DEPOSIT)])
    v = guard.apply(_ticket(), out, KB)
    assert v.decision == "draft_ready"
    assert v.citations[0].url == "https://valetax.com/how-to-deposit/"


def test_trading_advice_declined_even_if_model_missed_it():
    out = _out(category="other", draft="Sure, EURUSD looks strong.", citations=[])
    v = guard.apply(_ticket("Which pair should I buy today? Give me a signal"), out, KB)
    assert v.decision == "declined"
    assert "hard_rule:trading_advice" in v.reasons
    assert "trading_advice_regex_override" in v.reasons
    assert v.draft == guard.DECLINE_TEXT["en"]


def test_trading_advice_declined_in_russian():
    out = _out(category="trading_advice", lang="ru")
    v = guard.apply(_ticket("Стоит ли сейчас покупать золото?"), out, KB)
    assert v.decision == "declined"
    assert v.draft == guard.DECLINE_TEXT["ru"]


def test_invented_citation_drops_draft():
    out = _out(
        category="withdrawal",
        draft="Withdrawals are processed within 3 business days.",
        citations=[Citation(page="how-to-withdraw", quote="Withdrawals are processed within 3 business days.")],
    )
    v = guard.apply(_ticket("How long does a withdrawal take?"), out, KB)
    assert v.decision == "needs_human"
    assert v.draft is None
    assert "citation_not_in_kb" in v.reasons
    assert "draft_dropped:no_valid_citation" in v.reasons


def test_uncited_number_drops_draft():
    out = _out(
        category="withdrawal",
        draft="A pending withdrawal is in the queue and usually clears within 24 hours.",
        citations=[
            Citation(
                page="how-to-withdraw",
                quote="This means your request in in queue and in the midst of getting processed.",
            )
        ],
    )
    v = guard.apply(_ticket("My withdrawal is pending, what does that mean?"), out, KB)
    assert v.decision == "needs_human"
    assert any(r.startswith("draft_dropped:uncited_numbers:24") for r in v.reasons)


def test_number_from_ticket_is_allowed():
    out = _out(
        draft="You mentioned 40 minutes; balances update within 60 minutes.",
        citations=[
            Citation(
                page="how-to-deposit",
                quote="Deposits are instant! You will be able to view your updated account balance within 60 minutes.",
            )
        ],
    )
    v = guard.apply(_ticket("I deposited 40 minutes ago and nothing yet"), out, KB)
    assert v.decision == "draft_ready"


def test_list_numbering_is_not_an_uncited_number():
    draft = "To deposit:\n1. Log in to your Member Area.\n2. Click Deposit and select a payment channel.\n3. Enter the amount."
    cit = [Citation(page="how-to-deposit", quote="Click on the Deposit button and select your preferred payment channel")]
    assert guard.uncited_numbers(draft, cit, "how do I deposit") == []
    assert guard.uncited_numbers(draft + " It takes 3 days.", cit, "how do I deposit") == ["3"]
    # literal backslash-n and parenthesised numbering, as some models emit them
    assert guard.uncited_numbers("Steps:\\n1. Log in.\\n2. Click Deposit. \\(3) Enter the amount. (4) Done.", cit, "") == []


def test_wrong_page_slug_is_corrected_not_dropped():
    out = _out(category="verification", draft="Verification is completed within 48 hours.", citations=[
        Citation(page="how-to-verify-account", quote="Account opening and document verification will be completed within 48 hours.")
    ])
    v = guard.apply(_ticket("How long does verification take?"), out, KB)
    assert v.decision == "draft_ready"
    assert v.citations[0].page == "how-to-open-an-account"
    assert any(r.startswith("citation_page_corrected") for r in v.reasons)


def test_complaint_always_goes_to_human_even_with_grounded_draft():
    out = _out(category="complaint", sentiment="negative", urgency="high", draft="The minimum deposit starts from 8 USD.",
               citations=[Citation(page="how-to-deposit", quote=MIN_DEPOSIT)])
    v = guard.apply(_ticket("You stole my money, I'll report you"), out, KB)
    assert v.decision == "needs_human"
    assert "hard_rule:human_decides:complaint" in v.reasons
    assert v.draft is not None  # kept as a hint for the agent


def test_kyc_outcome_goes_to_human():
    out = _out(category="kyc_aml", draft=None)
    v = guard.apply(_ticket("My verification was rejected, approve it please"), out, KB)
    assert v.decision == "needs_human"
    assert "hard_rule:human_decides:kyc_aml" in v.reasons


def test_kb_gap_abstains():
    out = _out(category="withdrawal", draft=None)
    out.kb_gap = "No withdrawal fee information."
    v = guard.apply(_ticket("Is there a withdrawal fee?"), out, KB)
    assert v.decision == "needs_human"
    assert "kb_gap" in v.reasons


def test_account_lookup_routes_to_human_but_keeps_draft():
    out = _out(draft="Balances update within 60 minutes.", lookup=True,
               citations=[Citation(page="how-to-deposit", quote="You will be able to view your updated account balance within 60 minutes.")])
    v = guard.apply(_ticket("My deposit from 3 hours ago has not arrived"), out, KB)
    assert v.decision == "needs_human"
    assert "account_lookup_required" in v.reasons
    assert v.draft


def test_negative_high_urgency_escalates():
    out = _out(draft="The minimum deposit starts from 8 USD.", sentiment="negative", urgency="high",
               citations=[Citation(page="how-to-deposit", quote=MIN_DEPOSIT)])
    v = guard.apply(_ticket("URGENT!! what is the minimum deposit"), out, KB)
    assert v.decision == "needs_human"
    assert "escalation:negative_high_urgency" in v.reasons


def test_advice_language_in_draft_is_dropped():
    out = _out(category="account_opening", draft="We offer up to 1:2000. We recommend you choose 1:500 as a beginner.",
               citations=[Citation(page="how-to-open-an-account", quote="At Valetax, we offer up to 1:2000 depending on account types.")])
    v = guard.apply(_ticket("What leverage do you offer?"), out, KB)
    assert v.decision == "needs_human"
    assert "draft_dropped:advice_language" in v.reasons


def test_invalid_model_output_is_soft_failure():
    v = guard.apply(_ticket(), None, KB)
    assert v.decision == "needs_human"
    assert v.reasons == ["model_output_invalid"]


def test_guard_can_be_switched_off_for_eval_baseline():
    out = _out(draft="Withdrawals take 3 days.", citations=[Citation(page="how-to-withdraw", quote="invented text here")])
    v = guard.apply(_ticket("how long"), out, KB, guard.GuardConfig(verify_citations=False, verify_numbers=False))
    assert v.decision == "draft_ready"
