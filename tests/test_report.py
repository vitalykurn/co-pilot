import json
import re

from copilot.kb import KnowledgeBase
from evals import report


def test_locate_ignores_whitespace_case_and_quote_style():
    body = "Once completed,  you\u2019re ready to make\nyour first deposit ."
    span = report.locate(body, "you're READY to make your first deposit")
    assert span is not None
    assert body[span[0] : span[1]] == "you\u2019re ready to make\nyour first deposit"


def test_locate_rejects_text_not_in_body():
    assert report.locate("Deposits are instant!", "Withdrawals are instant!") is None
    assert report.locate("anything", "") is None


def test_locate_agrees_with_find_quote_on_the_real_kb():
    kb = KnowledgeBase.load()
    q = "Account opening and document verification will be completed within 48 hours."
    page = kb.find_quote(q)
    start, end = report.locate(kb.pages[page].body, q)
    assert kb.pages[page].body[start:end] == q


def test_build_writes_a_self_contained_page(tmp_path):
    out = report.build(tmp_path / "index.html")
    html = out.read_text(encoding="utf-8")

    m = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "data block missing or cut short"
    data = json.loads(m.group(1))
    assert "<" not in m.group(1)  # nothing in the data can close the script tag

    assert data["default_ticket"] == "T025"
    assert {t["ticket_id"] for t in data["tickets"]} >= {"T025", "T047", "T053"}
    names = [c["name"] for c in data["configs"]]
    assert "mock" not in names and names
    for name in names:
        assert set(data["runs"][name]) == {t["ticket_id"] for t in data["tickets"]}
    assert data["recommendation"]
