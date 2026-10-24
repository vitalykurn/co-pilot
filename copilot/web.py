"""Local agent-desk page: type a ticket, get what the support agent would see.

Standard library HTTP server around the same `Copilot.process()` the CLI and
the eval use. Local only: it binds to 127.0.0.1, keys come from the
environment or api_key.env, and nothing is ever sent to a customer.

  GET  /               the page
  GET  /api/providers  which models can run here and which is the default
  GET  /api/examples   a few labelled tickets from the eval set
  GET  /api/kb         the KB snapshot pages, for highlighting citations
  POST /api/process    {"text": "...", "provider": "D_sonnet_guard"} -> result
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

from . import guard
from .kb import ROOT, KnowledgeBase, locate
from .pipeline import Copilot
from .providers import get_provider
from .schema import Result, Ticket

PAGE = Path(__file__).with_name("static") / "agent.html"
CONFIGS = ROOT / "evals" / "configs.yaml"
TICKETS = ROOT / "evals" / "tickets.jsonl"
LOG_DIR = ROOT / "logs"

MAX_BODY = 8 * 1024
EXAMPLE_IDS = ["T025", "T035", "T019", "T043", "T053", "T047"]

# The eval configurations offered on the page, in drop-down order.
OFFERED = {
    "D_sonnet_guard": {"label": "Claude Sonnet 5.5 + code guard", "key": "ANTHROPIC_API_KEY", "sdk": "anthropic"},
    "C_strong_guard": {"label": "Qwen Max + code guard", "key": "ALICLOUD_API_KEY", "sdk": "openai"},
    "mock": {"label": "Mock (offline, keyword matcher)", "key": None, "sdk": None},
}


class App:
    """State shared by request threads: the KB, the configs, one Copilot per provider."""

    def __init__(self, only: list[str] | None = None, log_dir: Path | None = LOG_DIR):
        self.kb = KnowledgeBase.load()
        all_cfgs = yaml.safe_load(CONFIGS.read_text(encoding="utf-8"))
        self.configs = {name: all_cfgs[name] for name in OFFERED if name in all_cfgs and (only is None or name in only)}
        self.log_dir = log_dir
        self._copilots: dict[str, Copilot] = {}
        self._lock = threading.Lock()

    def providers(self) -> dict:
        items = []
        for name, cfg in self.configs.items():
            meta = OFFERED[name]
            reason = None
            if meta["sdk"] and importlib.util.find_spec(meta["sdk"]) is None:
                reason = f"Python package '{meta['sdk']}' is not installed"
            elif meta["key"] and not os.environ.get(meta["key"]):
                reason = f"{meta['key']} is not set"
            items.append({"name": name, "label": meta["label"], "model": cfg.get("model"), "available": reason is None, "reason": reason})
        live = [p["name"] for p in items if p["available"] and p["name"] != "mock"]
        default = live[0] if live else ("mock" if "mock" in self.configs else None)
        return {"providers": items, "default": default, "kb_version": self.kb.version}

    def examples(self) -> list[dict]:
        if not TICKETS.exists():
            return []
        rows = {}
        for line in TICKETS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["ticket_id"]] = row
        return [
            {"ticket_id": tid, "text": rows[tid]["text"], "group": rows[tid]["expected"].get("group")}
            for tid in EXAMPLE_IDS
            if tid in rows
        ]

    def kb_pages(self) -> list[dict]:
        return [{"slug": p.slug, "title": p.title, "url": p.url, "body": p.body} for p in self.kb.pages.values()]

    def copilot(self, name: str) -> Copilot:
        with self._lock:
            if name not in self._copilots:
                cfg = self.configs[name]
                extra = {k: cfg[k] for k in ("base_url", "api_key_env") if k in cfg}
                provider = get_provider(cfg["provider"], cfg.get("model"), **extra)
                gcfg = guard.GuardConfig(verify_citations=cfg["verify_citations"], verify_numbers=cfg["verify_numbers"])
                log = self.log_dir / f"{date.today().isoformat()}.jsonl" if self.log_dir else None
                self._copilots[name] = Copilot(
                    provider, self.kb, prompt_version=cfg.get("prompt_version", "draft_v3"), guard_config=gcfg, log_path=log
                )
            return self._copilots[name]

    def _citation(self, c) -> dict:
        found = self.kb.find_quote(c.quote, c.page) or self.kb.find_quote(c.quote)
        span = locate(self.kb.pages[found].body, c.quote) if found else None
        return {
            "page": c.page,
            "found_page": found,
            "quote": c.quote,
            "url": self.kb.url_for(found) if found else c.url,
            "span": list(span) if span else None,
        }

    def view(self, res: Result) -> dict:
        out = res.model_dump(mode="json", exclude={"raw_model_output", "citations"})
        out["citations"] = [self._citation(c) for c in res.citations]
        raw = res.raw_model_output
        out["model_draft"] = raw.draft if raw else None
        out["model_citations"] = [self._citation(c) for c in raw.citations] if raw else []
        return out

    def process(self, text: str, provider: str, ticket_id: str) -> dict:
        res = self.copilot(provider).process(Ticket(ticket_id=ticket_id, text=text, channel="agent-desk"))
        return self.view(res)


class _BadRequest(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    counter = {"n": 0}
    counter_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "copilot-desk/0.1"

        def log_message(self, fmt, *args):  # ticket text is never in the URL; keep the console quiet
            pass

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, payload) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _local_host(self) -> bool:
            # Refuse requests whose Host is not this machine (DNS rebinding from a web page).
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return host in ("127.0.0.1", "localhost", "::1")

        def do_GET(self):
            if not self._local_host():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "local access only"})
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                return self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/providers":
                return self._json(HTTPStatus.OK, app.providers())
            if path == "/api/examples":
                return self._json(HTTPStatus.OK, app.examples())
            if path == "/api/kb":
                return self._json(HTTPStatus.OK, app.kb_pages())
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            try:
                if not self._local_host():
                    raise _BadRequest(HTTPStatus.FORBIDDEN, "local access only")
                if self.path.split("?", 1)[0] != "/api/process":
                    raise _BadRequest(HTTPStatus.NOT_FOUND, "not found")
                # application/json cannot be sent cross-site without a CORS preflight, which this server never answers.
                if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                    raise _BadRequest(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send application/json")
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    raise _BadRequest(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"ticket is larger than {MAX_BODY // 1024} KB")
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    raise _BadRequest(HTTPStatus.BAD_REQUEST, "body is not JSON")
                text = str(body.get("text") or "").strip()
                provider = str(body.get("provider") or "")
                if not text:
                    raise _BadRequest(HTTPStatus.BAD_REQUEST, "ticket text is empty")
                avail = {p["name"]: p for p in app.providers()["providers"]}
                if provider not in avail:
                    raise _BadRequest(HTTPStatus.BAD_REQUEST, f"unknown provider {provider!r}")
                if not avail[provider]["available"]:
                    raise _BadRequest(HTTPStatus.BAD_REQUEST, avail[provider]["reason"])
            except _BadRequest as exc:
                return self._json(exc.status, {"error": exc.message})

            with counter_lock:
                counter["n"] += 1
                ticket_id = f"desk-{counter['n']}"
            # Copilot.process already turns provider and parsing failures into needs_human;
            # this only catches a provider that cannot even be constructed.
            try:
                result = app.process(text, provider, ticket_id)
            except Exception as exc:
                return self._json(HTTPStatus.BAD_GATEWAY, {"error": f"{type(exc).__name__}: {exc}"[:300]})
            return self._json(HTTPStatus.OK, result)

    return Handler


def make_server(host: str = "127.0.0.1", port: int = 8000, only: list[str] | None = None, log_dir: Path | None = LOG_DIR) -> ThreadingHTTPServer:
    app = App(only=only, log_dir=log_dir)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]
    return server
