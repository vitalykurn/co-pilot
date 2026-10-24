"""Build a self-contained HTML page from the saved eval results.

No server, no keys, no network: the page embeds the labelled tickets, the KB
snapshots and every live configuration's per-ticket output, and renders them
in the browser. Rebuild after any eval run or rescore.

Usage: python -m evals.report [--out docs/index.html]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from copilot.kb import ROOT, KnowledgeBase, locate
from evals.business_case import ASSUMPTIONS, compute

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
CONFIGS = HERE / "configs.yaml"
TICKETS = HERE / "tickets.jsonl"
TEMPLATE = HERE / "report_template.html"
BUSINESS_CASE = ROOT / "BUSINESS_CASE.md"
DEFAULT_OUT = ROOT / "docs" / "index.html"
DEFAULT_REPO_URL = "https://github.com/vitalykurn/co-pilot"

_DATA_SLOT = "/*__REPORT_DATA__*/null"


def _citation(kb: KnowledgeBase, c: dict) -> dict:
    quote = c.get("quote") or ""
    found = kb.find_quote(quote, c.get("page")) or kb.find_quote(quote)
    span = locate(kb.pages[found].body, quote) if found else None
    return {
        "page": c.get("page"),
        "found_page": found,
        "quote": quote,
        "url": kb.url_for(found) if found else c.get("url"),
        "span": list(span) if span else None,
    }


def _recommendation() -> str:
    for line in BUSINESS_CASE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("**") and s.endswith("**"):
            return s.strip("*").strip()
    return ""


def collect(repo_url: str = DEFAULT_REPO_URL) -> dict:
    kb = KnowledgeBase.load()
    cfgs = yaml.safe_load(CONFIGS.read_text(encoding="utf-8"))
    assumptions = yaml.safe_load(ASSUMPTIONS.read_text(encoding="utf-8"))
    tickets = [json.loads(l) for l in TICKETS.read_text(encoding="utf-8").splitlines() if l.strip()]

    configs: list[dict] = []
    runs: dict[str, dict] = {}
    for name, cfg in cfgs.items():
        path = RESULTS / f"{name}.json"
        if name == "mock" or not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        scores = {s["ticket_id"]: s for s in data["scores"]}
        per: dict[str, dict] = {}
        for r in data["results"]:
            s = scores.get(r["ticket_id"], {})
            raw = r.get("raw_model_output") or {}
            per[r["ticket_id"]] = {
                "decision": r["decision"],
                "reasons": r.get("reasons") or [],
                "classification": r.get("classification"),
                "draft": r.get("draft"),
                "citations": [_citation(kb, c) for c in r.get("citations") or []],
                "kb_gap": r.get("kb_gap"),
                "model_draft": raw.get("draft"),
                "model_citations": [_citation(kb, c) for c in raw.get("citations") or []],
                "violations": s.get("violations") or [],
                "decision_ok": s.get("decision_ok"),
                "cost_usd": r["usage"]["cost_usd"],
                "latency_ms": r["usage"]["latency_ms"],
            }
        metrics = data["summary"]["metrics"]
        configs.append(
            {
                "name": name,
                "description": cfg.get("description", ""),
                "model": cfg.get("model"),
                "verifier_model": (cfg.get("verifier") or {}).get("model") if cfg.get("verify_claims") else None,
                "code_guard": bool(cfg.get("verify_citations") and cfg.get("verify_numbers")),
                "claim_check": bool(cfg.get("verify_claims")),
                "prompt_version": data["summary"].get("prompt_version"),
                "metrics": metrics,
                "business": compute(metrics, assumptions),
            }
        )
        runs[name] = per

    names = [c["name"] for c in configs]
    # Configurations are compared on the same tickets; labels added after a live run wait for the next one.
    covered = set.intersection(*(set(p) for p in runs.values())) if runs else set()
    tickets = [t for t in tickets if t["ticket_id"] in covered]
    return {
        "recommendation": _recommendation(),
        "repo_url": repo_url,
        "kb_version": kb.version,
        "kb": [{"slug": p.slug, "title": p.title, "url": p.url, "body": p.body} for p in kb.pages.values()],
        "tickets": [{"ticket_id": t["ticket_id"], "text": t["text"], "expected": t["expected"]} for t in tickets],
        "configs": configs,
        "runs": runs,
        "default_primary": "D_sonnet_guard" if "D_sonnet_guard" in names else (names[0] if names else None),
        "default_compare": "C_strong_guard" if "C_strong_guard" in names else (names[1] if len(names) > 1 else None),
        "default_ticket": "T025",
    }


def render(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # A ticket containing "</script>" or "<!--" must not end the data block early.
    # "<" only occurs inside JSON strings, where \u003c is a valid escape.
    payload = payload.replace("<", "\\u003c")
    template = TEMPLATE.read_text(encoding="utf-8")
    if _DATA_SLOT not in template:
        raise ValueError(f"{TEMPLATE} has no {_DATA_SLOT} slot")
    return template.replace(_DATA_SLOT, payload)


def build(out: Path = DEFAULT_OUT, repo_url: str = DEFAULT_REPO_URL) -> Path:
    data = collect(repo_url)
    if not data["configs"]:
        raise SystemExit("no eval results found; run: python cli.py eval --config <name>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8", newline="\n")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    args = ap.parse_args(argv)
    out = build(args.out, args.repo_url)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
