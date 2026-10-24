Volume 10,000 tickets/month, 60% on KB topics. Agent 6 min/ticket today, 2 min with a draft, 5 min classified-only, $10/h.

| Config | Coverage in scope | Drafts / mo | Hours saved / mo | Agent savings | LLM cost / mo | Net / mo | Tickets with a violation (of 58) | Bad drafts / mo (upper bound) | Exposure at $500/incident |
|---|---|---|---|---|---|---|---|---|---|
| A_cheap_noguard | 67% | 4,002 | 367 | $3,668 | $1.82 | $3,666 | 4 | 690 | $344,828 |
| B_cheap_guard_v1 | 71% | 4,284 | 381 | $3,809 | $1.72 | $3,807 | 4 | 690 | $344,828 |
| B_cheap_guard | 69% | 4,140 | 374 | $3,737 | $1.85 | $3,735 | 4 | 690 | $344,828 |
| C_strong_guard | 62% | 3,714 | 352 | $3,524 | $47.85 | $3,476 | 1 | 172 | $86,207 |
| E_cheap_guard_claims | 36% | 2,142 | 274 | $2,738 | $2.87 | $2,735 | 0 | 0 | $0 |
| F_strong_guard_claims | 33% | 1,998 | 267 | $2,666 | $48.98 | $2,617 | 0 | 0 | $0 |
