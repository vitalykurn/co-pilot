# Business case: is the co-pilot worth running at 10,000 tickets/month, and in which configuration?

**Yes. Run configuration D (Claude Sonnet 5.5 + the code-level guard) in shadow for one week, then live. It is the only single-call configuration with no wrong statement on the eval set, at $107/month in tokens. C (Qwen Max, $48/month, one invented timeline) is the fallback if the production vendor is not Anthropic.**

## Numbers

Inputs: `evals/assumptions.yaml` (volume and agent-time assumptions) and `evals/results/*.metrics.json` (measured on the 58-ticket eval set). Recompute with `python -m evals.business_case`.

Volume 10,000 tickets/month, 60% on the four KB topics. Agent time 6 min/ticket today, 2 min with a reviewed draft, 5 min when the ticket arrives classified but without a draft. Agent cost $10/hour. All three are placeholders until the shadow week measures them.

| Config | What it is | Coverage in scope | Drafts / mo | Agent hours saved / mo | Agent savings / mo | LLM cost / mo | Tickets with a wrong statement (of 58) | Bad drafts / mo, upper bound |
|---|---|---|---|---|---|---|---|---|
| A | Qwen Flash, no code guard | 67% | 4,002 | 367 | $3,668 | $2 | 3 | 517 |
| B | Qwen Flash + code guard | 69% | 4,140 | 374 | $3,737 | $2 | 3 | 517 |
| C | Qwen Max + code guard | 62% | 3,714 | 352 | $3,524 | $48 | 1 | 172 |
| **D** | **Claude Sonnet 5.5 + code guard** | **60%** | **3,570** | **345** | **$3,452** | **$107** | **0** | **0** |
| E | B + model claim check | 36% | 2,142 | 274 | $2,738 | $3 | 0 | 0 |
| F | C + model claim check | 33% | 1,998 | 267 | $2,666 | $49 | 0 | 0 |

"Coverage in scope" is the share of in-scope eval tickets (answerable + KB gaps + account-specific) that came out as `draft_ready`. "Bad drafts / mo" extrapolates the eval violation rate to the full volume; it is an upper bound twice over, because a quarter of the eval set is deliberately unanswerable and because an agent reviews every draft before a customer sees it.

## Reading the table

1. **LLM cost does not decide anything.** $2 to $107 a month against $2,600–3,800 of agent time. Every configuration pays for itself in the first day. Choose on wrong statements.
2. **The code guard is free and removes a whole class of errors.** A→B costs nothing and stops invented citations from reaching an agent (one in the eval set at A). What it cannot stop is a real quote misread: "contact support if not received within 24 hours" rewritten as "funds arrive within 24 hours".
3. **D is the one that does not make that mistake.** On the withdrawal-time ticket, Sonnet quoted the 24-hour sentence as the threshold for contacting support and said the processing time is not stated. Qwen Max (C) turned the same sentence into "funds should be received within 24 hours" — the one remaining wrong statement in C. D costs $59/month more than C. One such reply reaching a customer costs more than that.
4. **D's misses are safe misses.** One Russian ticket came back as unparseable JSON and went to a person. One correct account-opening draft was dropped because it stated "48 hours" without attaching that sentence as a citation. Both are the guard doing what it is for, which is why decision accuracy is 0.93 rather than 0.98 and coverage is two points under C.
5. **The model claim check gets to zero violations by refusing half the drafts.** E and F flag drafts whose sentences the quotes do not literally state, including correct translations. D reaches the same zero without that second call. Keep the claim check for Phase 2, turned on per category once agent edits show where it earns its coverage cost.
6. **The biggest lever is not in this table.** 14 of 41 in-scope eval tickets are unanswerable because the KB does not state withdrawal time, fees, minimums, payment channels or verification details ([`kb/KB_AUDIT.md`](kb/KB_AUDIT.md)). Every abstain is logged with a `kb_gap` sentence. Fixing the four pages raises coverage for every configuration at zero model cost.

## What the shadow week must measure before the numbers are believed

- Draft acceptance rate and edit distance per category: replaces the 2-minute assumption.
- Handle time with and without a draft: replaces the 6-minute assumption.
- Real category mix: replaces the 60% in-scope assumption.
- Agent-flagged wrong statements: replaces the eval's 0-in-58 for D and 1-in-58 for C with a real rate.

Until then: expected savings in the low thousands of dollars per month in agent time, about $100/month in model cost. Worth running; configuration D; one week in shadow first.
