# Business case: is the co-pilot worth running at 10,000 tickets/month, and in which configuration?

**Yes, it is worth running, but the configuration has to be chosen again. Scored with follow-up promises ("our team will check and get back to you") counted as wrong statements, D (Claude Sonnet 5.5), the previous pick, has the most: 10 of 58. The current guard removes those drafts, which cuts D's coverage from 60% to 38%. Re-run B, C and D on prompt v3, which no longer asks for the promise, and choose on those numbers before the shadow week starts.**

## Numbers

Inputs: `evals/assumptions.yaml` (volume and agent-time assumptions) and `evals/results/*.metrics.json` (measured on the 58-ticket eval set). Recompute with `python -m evals.business_case`.

Volume 10,000 tickets/month, 60% on the four KB topics. Agent time 6 min/ticket today, 2 min with a reviewed draft, 5 min when the ticket arrives classified but without a draft. Agent cost $10/hour. All three are placeholders until the shadow week measures them.

| Config | What it is | Coverage in scope | Drafts / mo | Agent hours saved / mo | Agent savings / mo | LLM cost / mo | Tickets with a wrong statement (of 58) | Bad drafts / mo, upper bound |
|---|---|---|---|---|---|---|---|---|
| A | Qwen Flash, no code guard | 67% | 4,002 | 367 | $3,668 | $2 | 6 | 1,034 |
| B | Qwen Flash + code guard | 69% | 4,140 | 374 | $3,737 | $2 | 4 | 690 |
| C | Qwen Max + code guard | 62% | 3,714 | 352 | $3,524 | $48 | 4 | 690 |
| D | Claude Sonnet 5.5 + code guard | 60% | 3,570 | 345 | $3,452 | $107 | 10 | 1,724 |
| E | B + model claim check | 36% | 2,142 | 274 | $2,738 | $3 | 0 | 0 |
| F | C + model claim check | 33% | 1,998 | 267 | $2,666 | $49 | 3 | 517 |

The runs are the saved prompt-v2 outputs, rescored: a draft that promises a later action or mentions the knowledge base now counts as a wrong statement, because nothing follows up on a sent draft. Coverage is still what the old guard let through. The current guard drops those drafts and sends partial answers to a person; applied offline to the same outputs, it gives coverage in scope of 62% (A), 64% (B), 57% (C) and 38% (D).

"Coverage in scope" is the share of in-scope eval tickets (answerable + KB gaps + account-specific) that came out as `draft_ready`. "Bad drafts / mo" extrapolates the eval violation rate to the full volume; it is an upper bound twice over, because a quarter of the eval set is deliberately unanswerable and because an agent reviews every draft before a customer sees it.

## Reading the table

1. **LLM cost does not decide anything.** $2 to $107 a month against $2,600–3,800 of agent time. Every configuration pays for itself in the first day. Choose on wrong statements.
2. **The code guard is free and removes a whole class of errors.** A→B costs nothing and stops invented citations from reaching an agent (one in the eval set at A). What it cannot stop is a real quote misread: "contact support if not received within 24 hours" rewritten as "funds arrive within 24 hours".
3. **D does not misread quotes.** On the withdrawal-time ticket, Sonnet quoted the 24-hour sentence as the threshold for contacting support and said the processing time is not stated. Qwen Max (C) turned the same sentence into "funds should be received within 24 hours". That misread is still the most expensive kind of error in the table.
4. **D's wrong statements are the ones the prompt asked for.** Prompt v2 told the model to say "the knowledge base does not state the rest and the team will check" on partly covered questions. Sonnet did so on 10 tickets, 7 of them in drafts marked ready, and no team was ever going to check. This kind of error is easy to remove: prompt v3 drops the rule, and the guard now drops such drafts in code. What it costs D in coverage on v3 is not measured yet.
5. **The model claim check gets to zero violations by refusing half the drafts.** E flags drafts whose sentences the quotes do not literally state, including correct translations. F's three remaining are follow-up promises; the v1 claim check was told they are fine. Keep the claim check for Phase 2, turned on per category once agent edits show where it earns its coverage cost.
6. **The biggest lever is not in this table.** 14 of 41 in-scope eval tickets are unanswerable because the KB does not state withdrawal time, fees, minimums, payment channels or verification details ([`kb/KB_AUDIT.md`](kb/KB_AUDIT.md)). Every abstain is logged with a `kb_gap` sentence. Fixing the four pages raises coverage for every configuration at zero model cost.

## What the shadow week must measure before the numbers are believed

- Draft acceptance rate and edit distance per category: replaces the 2-minute assumption.
- Handle time with and without a draft: replaces the 6-minute assumption.
- Real category mix: replaces the 60% in-scope assumption.
- Agent-flagged wrong statements: replaces the eval rates with a real rate.

Until then: expected savings in the low thousands of dollars per month in agent time, up to about $100/month in model cost. Worth running; pick the configuration after the v3 re-run; one week in shadow first.
