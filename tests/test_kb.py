from copilot.kb import KnowledgeBase, normalize


def test_kb_loads_four_pages():
    kb = KnowledgeBase.load()
    assert set(kb.pages) == {
        "how-to-deposit",
        "how-to-withdraw",
        "how-to-open-an-account",
        "how-to-verify-account",
    }
    assert len(kb.version) == 12


def test_find_quote_exact_and_normalized():
    kb = KnowledgeBase.load()
    assert kb.find_quote("The minimum deposit starts from 8 USD, depending on the account type.") == "how-to-deposit"
    # whitespace and curly quotes do not matter
    assert kb.find_quote("you’re   ready to make your first deposit") == "how-to-open-an-account"
    assert kb.find_quote("you're ready to make your first deposit") == "how-to-open-an-account"


def test_find_quote_rejects_invented_text():
    kb = KnowledgeBase.load()
    assert kb.find_quote("Withdrawals are processed within 3 business days.") is None
    assert kb.find_quote("The withdrawal fee is 2%.") is None
    assert kb.find_quote("8 USD") is None  # too short to count as grounding


def test_find_quote_scoped_to_page():
    kb = KnowledgeBase.load()
    q = "Account opening and document verification will be completed within 48 hours."
    assert kb.find_quote(q, page="how-to-open-an-account") == "how-to-open-an-account"
    assert kb.find_quote(q, page="how-to-verify-account") is None


def test_normalize():
    assert normalize("  A\u00a0b\n\nC ") == "a b c"
