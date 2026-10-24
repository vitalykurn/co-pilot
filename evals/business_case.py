"""Turn eval metrics + assumptions into the one-page numbers.

Reads evals/results/<config>.metrics.json for every configuration that has
been run and evals/assumptions.yaml. Writes evals/results/business_case.md.

Usage: python -m evals.business_case [--configs A_cheap_noguard B_cheap_guard C_strong_guard]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
ASSUMPTIONS = HERE / "assumptions.yaml"


def compute(metrics: dict, a: dict) -> dict:
    tickets = a["tickets_per_month"]
    in_scope = tickets * a["share_in_scope"]
    coverage = metrics.get("coverage_in_scope") or 0.0
    drafted = in_scope * coverage
    classified_only = tickets - drafted

    minutes_saved = drafted * (a["agent_minutes_without_copilot"] - a["agent_minutes_with_draft"]) + classified_only * (
        a["agent_minutes_without_copilot"] - a["agent_minutes_classified_only"]
    )
    hours_saved = minutes_saved / 60
    savings = hours_saved * a["agent_hourly_cost_usd"]
    llm_cost = tickets * metrics["cost_usd_per_ticket"]

    n_eval = metrics["tickets"]
    violation_rate = metrics["violations_total"] / n_eval if n_eval else 0.0
    expected_bad_drafts = violation_rate * tickets  # upper bound: a reviewer still sits between draft and customer

    return {
        "coverage_in_scope": coverage,
        "drafts_per_month": round(drafted),
        "hours_saved_per_month": round(hours_saved),
        "agent_savings_usd": round(savings),
        "llm_cost_usd": round(llm_cost, 2),
        "net_usd": round(savings - llm_cost),
        "violations_in_eval": metrics["violations_total"],
        "violation_rate": round(violation_rate, 3),
        "bad_drafts_per_month_upper": round(expected_bad_drafts),
        "incident_exposure_usd": round(expected_bad_drafts * a["incident_cost_usd"]),
        "cost_per_ticket_usd": metrics["cost_usd_per_ticket"],
    }


def render(rows: dict[str, dict], a: dict) -> str:
    lines = [
        f"Volume {a['tickets_per_month']:,} tickets/month, {a['share_in_scope']:.0%} on KB topics. "
        f"Agent {a['agent_minutes_without_copilot']:.0f} min/ticket today, {a['agent_minutes_with_draft']:.0f} min with a draft, "
        f"{a['agent_minutes_classified_only']:.0f} min classified-only, ${a['agent_hourly_cost_usd']:.0f}/h.",
        "",
        "| Config | Coverage in scope | Drafts / mo | Hours saved / mo | Agent savings | LLM cost / mo | Net / mo | Violations in eval | Bad drafts / mo (upper) | Exposure at $%d/incident |" % a["incident_cost_usd"],
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in rows.items():
        lines.append(
            f"| {name} | {r['coverage_in_scope']:.0%} | {r['drafts_per_month']:,} | {r['hours_saved_per_month']:,} | "
            f"${r['agent_savings_usd']:,} | ${r['llm_cost_usd']:,.2f} | ${r['net_usd']:,} | {r['violations_in_eval']} | "
            f"{r['bad_drafts_per_month_upper']:,} | ${r['incident_exposure_usd']:,} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="*")
    args = ap.parse_args()
    a = yaml.safe_load(ASSUMPTIONS.read_text(encoding="utf-8"))

    files = sorted(RESULTS.glob("*.metrics.json"))
    names = args.configs or [f.name.replace(".metrics.json", "") for f in files]
    rows = {}
    for name in names:
        path = RESULTS / f"{name}.metrics.json"
        if not path.exists():
            print(f"skip {name}: no results yet (run: python cli.py eval --config {name})", file=sys.stderr)
            continue
        rows[name] = compute(json.loads(path.read_text(encoding="utf-8")), a)
    if not rows:
        return 1
    md = render(rows, a)
    (RESULTS / "business_case.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
