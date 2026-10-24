import json

from copilot.kb import KnowledgeBase
from copilot.providers import get_provider
from copilot.schema import ModelOutput


def _run(text: str) -> ModelOutput:
    out = get_provider("mock").complete("system", text)
    return ModelOutput.model_validate(json.loads(out.text))


def test_mock_output_matches_schema_and_kb():
    kb = KnowledgeBase.load()
    for text in [
        "What is the minimum deposit?",
        "My withdrawal is pending for two days",
        "Which documents do I need for verification?",
        "How do I open an account?",
    ]:
        out = _run(text)
        assert out.draft
        for c in out.citations:
            assert kb.find_quote(c.quote, c.page) == c.page


def test_mock_abstains_on_kb_gap():
    out = _run("How long does a withdrawal take?")
    assert out.draft is None
    assert out.kb_gap


def test_mock_flags_trading_advice_and_complaints():
    assert _run("Which pair should I buy today? Give me a signal").classification.category == "trading_advice"
    assert _run("You stole my money, I will go to the regulator").classification.category == "complaint"
