"""Minimal CLI.

  python cli.py process --text "How long does a withdrawal take?"
  python cli.py process tickets.jsonl --provider openai --model gpt-4o-mini
  python cli.py eval --config mock
  python cli.py kb
  python cli.py report          # static page from saved results -> docs/index.html
  python cli.py serve --open    # local agent-desk page on http://127.0.0.1:8000/

Each ticket result is printed as JSON and appended to logs/<date>.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from copilot.env import load_env
from copilot.kb import KnowledgeBase, ROOT
from copilot.pipeline import Copilot
from copilot.providers import get_provider
from copilot.schema import Ticket


def cmd_process(args: argparse.Namespace) -> int:
    load_env()
    kb = KnowledgeBase.load()
    extra = {}
    if args.base_url:
        extra["base_url"] = args.base_url
    if args.api_key_env:
        extra["api_key_env"] = args.api_key_env
    provider = get_provider(args.provider, args.model, **extra)
    log = None if args.no_log else ROOT / "logs" / f"{date.today().isoformat()}.jsonl"
    copilot = Copilot(provider, kb, prompt_version=args.prompt, log_path=log)

    tickets: list[Ticket] = []
    if args.text:
        tickets.append(Ticket(ticket_id="cli", text=args.text))
    if args.file:
        for i, line in enumerate(Path(args.file).read_text(encoding="utf-8").splitlines()):
            if line.strip():
                row = json.loads(line)
                tickets.append(Ticket(ticket_id=row.get("ticket_id", f"L{i+1}"), text=row["text"], subject=row.get("subject")))
    if not tickets:
        print("nothing to process: pass --text or a JSONL file", file=sys.stderr)
        return 2

    for t in tickets:
        res = copilot.process(t)
        if args.brief:
            cls = res.classification
            head = f"{t.ticket_id}: {res.decision}"
            if cls:
                head += f"  [{cls.category}/{cls.urgency}/{cls.language}/{cls.sentiment}]"
            print(head)
            print("  reasons:", ", ".join(res.reasons) or "-")
            if res.draft:
                print("  draft:", res.draft)
            for c in res.citations:
                print(f"  cite [{c.page}]: \"{c.quote}\"")
            if res.kb_gap:
                print("  kb_gap:", res.kb_gap)
            print()
        else:
            print(json.dumps(res.model_dump(mode="json", exclude={"raw_model_output"}), ensure_ascii=False, indent=2))
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from evals.run_eval import run

    run(args.config, args.limit)
    return 0


def cmd_kb(args: argparse.Namespace) -> int:
    kb = KnowledgeBase.load()
    print(f"KB version {kb.version}")
    for p in kb.pages.values():
        print(f"  {p.slug:24s} {p.sha256[:12]}  {len(p.body):5d} chars  {p.url}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from copilot.web import make_server

    load_env()
    server = make_server(args.host, args.port)
    url = f"http://{args.host}:{server.server_address[1]}/"
    for p in server.app.providers()["providers"]:
        state = "ok" if p["available"] else f"off ({p['reason']})"
        print(f"  {p['label']:36s} {state}")
    print(f"agent desk on {url}  (Ctrl+C to stop)", flush=True)
    if args.open:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from evals.report import DEFAULT_OUT, build

    out = build(args.out or DEFAULT_OUT)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cli.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("process", help="process one ticket (--text) or a JSONL file of tickets")
    p.add_argument("file", nargs="?")
    p.add_argument("--text")
    p.add_argument("--provider", default="mock", choices=["mock", "openai", "anthropic"])
    p.add_argument("--model")
    p.add_argument("--base-url", help="OpenAI-compatible endpoint, e.g. https://dashscope.aliyuncs.com/compatible-mode/v1")
    p.add_argument("--api-key-env", help="env var holding the key for that endpoint (default OPENAI_API_KEY)")
    p.add_argument("--prompt", default="draft_v3")
    p.add_argument("--brief", action="store_true", help="human-readable output instead of JSON")
    p.add_argument("--no-log", action="store_true")
    p.set_defaults(func=cmd_process)

    e = sub.add_parser("eval", help="run the labelled eval set through a configuration from evals/configs.yaml")
    e.add_argument("--config", default="mock")
    e.add_argument("--limit", type=int)
    e.set_defaults(func=cmd_eval)

    k = sub.add_parser("kb", help="show KB snapshot versions")
    k.set_defaults(func=cmd_kb)

    s = sub.add_parser("serve", help="local agent-desk page: type a ticket, see the decision, draft and citations")
    s.add_argument("--host", default="127.0.0.1", help="interface to bind (default 127.0.0.1, local only)")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--open", action="store_true", help="open the page in the default browser")
    s.set_defaults(func=cmd_serve)

    r = sub.add_parser("report", help="build the static eval explorer page from saved results")
    r.add_argument("--out", type=Path, help="output file (default docs/index.html)")
    r.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
