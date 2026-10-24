"""Run the labelled ticket set through one configuration and score it.

All checks are deterministic: labels compare against gold, citations against
the KB snapshot, numbers against citations, forbidden phrases, follow-up
promises and mentions of the knowledge base against the draft. No LLM judge. Wording quality of drafts is reviewed by hand on a sample
and noted in the results file, not scored here.

Usage: python -m evals.run_eval --config mock [--limit N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from copilot import guard
from copilot.env import load_env
from copilot.kb import KnowledgeBase
from copilot.pipeline import Copilot
from copilot.providers import get_provider
from copilot.schema import Result, Ticket

HERE = Path(__file__).resolve().parent
TICKETS = HERE / "tickets.jsonl"
CONFIGS = HERE / "configs.yaml"
RESULTS = HERE / "results"

HUMAN_GOLD = {"trading_advice", "complaint", "kyc_aml"}


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def load_tickets(limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in TICKETS.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def score_one(row: dict, res: Result, kb: KnowledgeBase) -> dict:
    exp = row["expected"]
    cls = res.classification
    s: dict = {"ticket_id": row["ticket_id"], "group": exp.get("group"), "decision": res.decision}

    s["category_ok"] = cls is not None and cls.category in _as_list(exp["category"])
    s["language_ok"] = cls is not None and cls.language.lower()[:2] == exp["language"]
    s["urgency_ok"] = cls is not None and cls.urgency == exp.get("urgency")
    s["sentiment_ok"] = cls is not None and cls.sentiment == exp.get("sentiment")
    s["decision_ok"] = res.decision in _as_list(exp["decision"])

    # Abstain: did the model (before guards) refuse to draft where the KB is silent?
    raw = res.raw_model_output
    s["gold_abstain"] = bool(exp.get("abstain"))
    s["model_abstained"] = raw is None or raw.draft is None
    s["final_abstained"] = res.draft is None

    # Citations as the model produced them, before the guard touched them.
    raw_cits = raw.citations if raw else []
    s["raw_citations"] = len(raw_cits)
    s["raw_citations_valid"] = sum(1 for c in raw_cits if kb.find_quote(c.quote, c.page) or kb.find_quote(c.quote))

    # Violations are judged on the FINAL output the agent would see.
    v: list[str] = []
    draft = res.draft or ""
    if res.decision == "draft_ready":
        if _as_list(exp["category"])[0] in HUMAN_GOLD or (
            set(_as_list(exp["category"])) & HUMAN_GOLD and not (set(_as_list(exp["category"])) - HUMAN_GOLD)
        ):
            v.append("drafted_for_human_only_case")
        for c in res.citations:
            if not kb.find_quote(c.quote, c.page):
                v.append("invalid_citation")
                break
        missing = guard.uncited_numbers(draft, res.citations, row["text"])
        if missing:
            v.append("uncited_numbers:" + ",".join(missing))
        if guard.ADVICE_IN_DRAFT.search(draft):
            v.append("advice_language")
        if exp.get("pages") and res.citations and not {c.page for c in res.citations} <= set(exp["pages"]):
            v.append("cited_unexpected_page")
    if draft and res.decision != "declined":
        if guard.FOLLOWUP_PROMISE.search(draft):
            v.append("followup_promise")
        if guard.INTERNAL_REF.search(draft):
            v.append("internal_reference")
    if draft:
        low = draft.lower()
        for phrase in exp.get("forbidden_in_draft", []):
            if phrase.lower() in low:
                v.append(f"forbidden_phrase:{phrase}")
    s["violations"] = v
    s["cost_usd"] = res.usage.cost_usd
    s["latency_ms"] = res.usage.latency_ms
    s["tokens_in"] = res.usage.tokens_in
    s["tokens_out"] = res.usage.tokens_out
    s["reasons"] = res.reasons
    return s


def aggregate(scores: list[dict]) -> dict:
    n = len(scores)
    frac = lambda key: round(sum(1 for s in scores if s[key]) / n, 3) if n else 0.0

    gold_abstain = [s for s in scores if s["gold_abstain"]]
    answerable = [s for s in scores if s["group"] == "answerable"]
    # In-scope = the four KB topics as they arrive: answerable, KB gaps and account-specific cases together.
    in_scope = [s for s in scores if s["group"] in ("answerable", "kb_gap", "account_lookup")]
    model_abstained = [s for s in scores if s["model_abstained"] and s["group"] in ("answerable", "kb_gap")]

    abstain_recall = round(sum(1 for s in gold_abstain if s["model_abstained"]) / len(gold_abstain), 3) if gold_abstain else None
    abstain_precision = (
        round(sum(1 for s in model_abstained if s["gold_abstain"]) / len(model_abstained), 3) if model_abstained else None
    )
    raw_cits = sum(s["raw_citations"] for s in scores)
    return {
        "tickets": n,
        "category_acc": frac("category_ok"),
        "language_acc": frac("language_ok"),
        "urgency_acc": frac("urgency_ok"),
        "sentiment_acc": frac("sentiment_ok"),
        "decision_acc": frac("decision_ok"),
        "abstain_recall_on_kb_gaps": abstain_recall,
        "abstain_precision": abstain_precision,
        "raw_citation_validity": round(sum(s["raw_citations_valid"] for s in scores) / raw_cits, 3) if raw_cits else None,
        "coverage_all": round(sum(1 for s in scores if s["decision"] == "draft_ready") / n, 3),
        "coverage_answerable": round(sum(1 for s in answerable if s["decision"] == "draft_ready") / len(answerable), 3) if answerable else None,
        "coverage_in_scope": round(sum(1 for s in in_scope if s["decision"] == "draft_ready") / len(in_scope), 3) if in_scope else None,
        "violations_total": sum(len(s["violations"]) for s in scores),
        "tickets_with_violations": sum(1 for s in scores if s["violations"]),
        "violations_by_type": dict(Counter(v.split(":")[0] for s in scores for v in s["violations"])),
        "decisions": dict(Counter(s["decision"] for s in scores)),
        "cost_usd_total": round(sum(s["cost_usd"] for s in scores), 4),
        "cost_usd_per_ticket": round(sum(s["cost_usd"] for s in scores) / n, 6),
        "tokens_in_avg": round(sum(s["tokens_in"] for s in scores) / n),
        "tokens_out_avg": round(sum(s["tokens_out"] for s in scores) / n),
        "latency_ms_avg": round(sum(s["latency_ms"] for s in scores) / n),
    }


def run(config_name: str, limit: int | None = None, out_dir: Path = RESULTS) -> dict:
    cfgs = yaml.safe_load(CONFIGS.read_text(encoding="utf-8"))
    if config_name not in cfgs:
        raise SystemExit(f"unknown config {config_name!r}; available: {', '.join(cfgs)}")
    cfg = cfgs[config_name]
    load_env()
    kb = KnowledgeBase.load()
    provider_kwargs = {k: cfg[k] for k in ("base_url", "api_key_env") if k in cfg}
    provider = get_provider(cfg["provider"], cfg.get("model"), **provider_kwargs)
    gcfg = guard.GuardConfig(verify_citations=cfg["verify_citations"], verify_numbers=cfg["verify_numbers"])
    verifier = None
    if cfg.get("verify_claims"):
        v = cfg.get("verifier") or {}
        v_extra = {k: v[k] for k in ("base_url", "api_key_env") if k in v}
        verifier = get_provider(v.get("provider", cfg["provider"]), v.get("model", cfg.get("model")), **(v_extra or provider_kwargs))
    copilot = Copilot(provider, kb, prompt_version=cfg.get("prompt_version", "draft_v3"), guard_config=gcfg, verifier=verifier)

    rows = load_tickets(limit)
    scores, results = [], []
    for row in rows:
        res = copilot.process(Ticket(ticket_id=row["ticket_id"], text=row["text"]))
        results.append(res.model_dump(mode="json"))
        scores.append(score_one(row, res, kb))
        flag = "" if not scores[-1]["violations"] else "  !! " + "; ".join(scores[-1]["violations"])
        print(f"{row['ticket_id']} {res.decision:12s} {'ok ' if scores[-1]['decision_ok'] else 'MISS'} {flag}")

    summary = {
        "config": config_name,
        "config_detail": cfg,
        "prompt_version": copilot.prompt_version,
        "kb_version": kb.version,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metrics": aggregate(scores),
    }
    _write(out_dir, config_name, summary, scores, results)
    print(json.dumps(summary["metrics"], indent=2))
    return summary


def _write(out_dir: Path, config_name: str, summary: dict, scores: list[dict], results: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{config_name}.json").write_text(
        json.dumps({"summary": summary, "scores": scores, "results": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Timing-free copy of the metrics: CI diffs this file to catch prompt/guard drift on the mock run.
    stable = {k: v for k, v in summary["metrics"].items() if k != "latency_ms_avg"}
    stable["prompt_version"], stable["kb_version"] = summary["prompt_version"], summary["kb_version"]
    (out_dir / f"{config_name}.metrics.json").write_text(json.dumps(stable, indent=2) + "\n", encoding="utf-8")


def rescore(config_name: str, out_dir: Path = RESULTS) -> dict:
    """Re-score saved model outputs against the current labels and scorer. No API calls.

    Use after fixing a label or the scoring code; the model outputs themselves are unchanged.
    """
    path = out_dir / f"{config_name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    kb = KnowledgeBase.load()
    rows = {r["ticket_id"]: r for r in load_tickets()}
    results = data["results"]
    scores = [score_one(rows[r["ticket_id"]], Result.model_validate(r), kb) for r in results if r["ticket_id"] in rows]
    summary = data["summary"]
    summary["metrics"] = aggregate(scores)
    summary["rescored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(out_dir, config_name, summary, scores, results)
    print(f"{config_name}: rescored {len(scores)} tickets")
    print(json.dumps(summary["metrics"], indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="mock")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--rescore", action="store_true", help="re-score saved outputs with current labels, no API calls")
    args = ap.parse_args()
    if args.rescore:
        rescore(args.config)
    else:
        run(args.config, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
