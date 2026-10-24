import http.client
import json
import threading

import pytest

from copilot import web


@pytest.fixture()
def server(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    srv = web.make_server("127.0.0.1", 0, log_dir=tmp_path)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _request(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json"} if data is not None else {}
    hdrs.update(headers or {})
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    return resp.status, payload


def test_page_is_served(server):
    status, body = _request(server, "GET", "/")
    assert status == 200
    assert b"agent desk" in body
    # nested child lists must be flattened before replaceChildren, or citations render as "[object HTMLDivElement]"
    assert b"replaceChildren(...parts.flat(Infinity))" in body


def test_providers_mark_missing_key_unavailable(server):
    status, body = _request(server, "GET", "/api/providers")
    data = json.loads(body)
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["mock"]["available"]
    assert not by_name["D_sonnet_guard"]["available"]
    assert data["default"] != "D_sonnet_guard"


def test_process_returns_result_with_citation_span(server, tmp_path):
    status, body = _request(server, "POST", "/api/process", {"text": "What is the minimum deposit?", "provider": "mock"})
    assert status == 200
    res = json.loads(body)
    assert res["decision"] == "draft_ready"
    cite = res["citations"][0]
    assert cite["found_page"] == "how-to-deposit" and cite["span"]
    assert "raw_model_output" not in res
    assert list(tmp_path.glob("*.jsonl")), "request was not logged"


def test_examples_and_kb(server):
    _, ex = _request(server, "GET", "/api/examples")
    assert "T025" in {e["ticket_id"] for e in json.loads(ex)}
    _, kb = _request(server, "GET", "/api/kb")
    assert len(json.loads(kb)) == 4


def test_bad_requests_are_rejected(server):
    assert _request(server, "POST", "/api/process", {"text": "   ", "provider": "mock"})[0] == 400
    assert _request(server, "POST", "/api/process", {"text": "hi", "provider": "nope"})[0] == 400
    assert _request(server, "POST", "/api/process", {"text": "hi", "provider": "D_sonnet_guard"})[0] == 400
    big = {"text": "x" * (web.MAX_BODY + 10), "provider": "mock"}
    assert _request(server, "POST", "/api/process", big)[0] == 413
    assert _request(server, "POST", "/api/process", b"text=hi", {"Content-Type": "text/plain"})[0] == 415


def test_foreign_host_header_is_refused(server):
    assert _request(server, "GET", "/api/kb", headers={"Host": "evil.example"})[0] == 403
