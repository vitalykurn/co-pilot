import json

from copilot.pipeline import Copilot, parse_model_output
from copilot.pii import mask
from copilot.providers import get_provider
from copilot.providers.base import LLMResponse, Provider
from copilot.schema import Ticket


class BrokenProvider(Provider):
    model = "broken"

    def complete(self, system, user, *, max_tokens=1024):
        return LLMResponse(text="Sorry, I cannot help with that.", tokens_in=1, tokens_out=1, latency_ms=1, model=self.model)


class ExplodingProvider(Provider):
    model = "exploding"

    def complete(self, system, user, *, max_tokens=1024):
        raise ConnectionError("boom")


def test_parse_handles_fences_and_garbage():
    assert parse_model_output('```json\n{"classification": {"category": "deposit", "urgency": "low", "language": "en", "sentiment": "neutral"}}\n```') is not None
    assert parse_model_output("not json") is None
    assert parse_model_output('{"classification": {"category": "nope"}}') is None


def test_non_json_model_answer_is_needs_human_not_crash():
    res = Copilot(BrokenProvider()).process(Ticket(ticket_id="x", text="hello"))
    assert res.decision == "needs_human"
    assert res.reasons == ["model_output_invalid"]
    assert res.classification is None


def test_provider_exception_is_needs_human_not_crash():
    res = Copilot(ExplodingProvider()).process(Ticket(ticket_id="x", text="hello"))
    assert res.decision == "needs_human"
    assert res.reasons[0] == "provider_error:ConnectionError"


def test_end_to_end_on_mock_writes_log(tmp_path):
    log = tmp_path / "run.jsonl"
    cp = Copilot(get_provider("mock"), log_path=log)
    res = cp.process(Ticket(ticket_id="T1", text="What is the minimum deposit? my email is bob@example.com"))
    assert res.decision == "draft_ready"
    line = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert line["ticket_id"] == "T1"
    assert "bob@example.com" not in line["ticket_text_masked"]
    assert line["usage"]["kb_version"] == cp.kb.version
    assert "raw_model_output" not in line


def test_mask():
    s = mask("call +65 6931 5022, card 4111 1111 1111 1111, acc 1234567890, 8 USD in 60 minutes, bob@x.io")
    assert "[PHONE]" in s and "[CARD]" in s and "[EMAIL]" in s
    assert "6931" not in s and "4111" not in s and "1234567890" not in s and "bob@" not in s
    assert "8 USD" in s and "60 minutes" in s
