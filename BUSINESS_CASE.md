# Business case: is the co-pilot worth running at 10,000 tickets/month, and in which configuration?

**Yes. Run configuration C (strong model + code-level guard) in shadow for one week, then live. Token cost is irrelevant at this volume (under $50/month for any configuration); the decision is about how many wrong statements get past the guard versus how many tickets get a draft.**

## Numbers

Inputs: `evals/assumptions.yaml` (volume and agent-time assumptions) and `evals/results/*.metrics.json` (measured on the 58-ticket eval set). Recompute with `python -m evals.business_case`.

Volume 10,000 tickets/month, 60% on the four KB topics. Agent time 6 min/ticket today, 2 min with a reviewed draft, 5 min when the ticket arrives classified but without a draft. Agent cost $10/hour. All three are placeholders until the shadow week measures them.

| Config | What it is | Coverage in scope | Drafts / mo | Agent hours saved / mo | Agent savings / mo | LLM cost / mo | Tickets with a wrong statement (of 58) | Bad drafts / mo, upper bound |
|---|---|---|---|---|---|---|---|---|
| A | Qwen Flash, no code guard | 67% | 4,002 | 367 | $3,668 | $2 | 4 | 690 |
| B | Qwen Flash + code guard | 69% | 4,140 | 374 | $3,737 | $2 | 4 | 690 |
| **C** | **Qwen Max + code guard** | **62%** | **3,714** | **352** | **$3,524** | **$48** | **1** | **172** |
| E | B + model claim check | 36% | 2,142 | 274 | $2,738 | $3 | 0 | 0 |
| F | C + model claim check | 33% | 1,998 | 267 | $2,666 | $49 | 0 | 0 |

"Coverage in scope" is the share of in-scope eval tickets (answerable + KB gaps + account-specific) that came out as `draft_ready`. "Bad drafts / mo" extrapolates the eval violation rate to the full volume; it is an upper bound twice over, because a quarter of the eval set is deliberately unanswerable and because an agent reviews every draft before a customer sees it.

## Reading the table

1. **LLM cost does not decide anything.** $2 vs $48 a month against $2,600–3,800 of agent time. Every configuration pays for itself in the first day. Choose on quality.
2. **The code guard is free and removes a whole class of errors.** A→B costs nothing and stops invented citations from reaching an agent (one in the eval set at A). What it cannot stop is a real quote misread: "contact support if not received within 24 hours" rewritten as "funds arrive within 24 hours". Every remaining violation in B and C is of that kind.
3. **The stronger model halves the misreads at the same coverage.** C: 1 ticket with a wrong statement out of 58, 62% coverage, $48/month. That is the recommended Phase 1 configuration.
4. **The model claim check gets to zero violations by refusing half the drafts.** E and F flag drafts whose sentences the quotes do not literally state, including correct translations and safe inferences. At today's precision it costs about 1,100 drafts and 80 agent-hours a month relative to C. It is the right tool for a compliance-driven setting, and the right tool for the withdrawal category specifically, where every misread in the eval set lives. Tuning it belongs to Phase 2, with real agent feedback as the training signal.
5. **The biggest lever is not in this table.** 14 of 41 in-scope eval tickets are unanswerable because the KB does not state withdrawal time, fees, minimums, payment channels or verification details ([`kb/KB_AUDIT.md`](kb/KB_AUDIT.md)). Every abstain is logged with a `kb_gap` sentence. Fixing the four pages raises coverage for every configuration at zero model cost.

## What the shadow week must measure before the numbers are believed

- Draft acceptance rate and edit distance per category: replaces the 2-minute assumption.
- Handle time with and without a draft: replaces the 6-minute assumption.
- Real category mix: replaces the 60% in-scope assumption.
- Agent-flagged wrong statements: replaces the eval's 1-in-58 with a real rate.

Until then: expected savings in the low thousands of dollars per month in agent time, at tens of dollars in model cost, with the error profile above. Worth running; configuration C; one week in shadow first.
