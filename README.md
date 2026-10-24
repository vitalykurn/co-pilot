# Support-ticket co-pilot for a retail FX/CFD broker

For every incoming ticket the co-pilot:

1. classifies it: category, urgency, language, sentiment;
2. drafts a reply grounded in the knowledge base with citations to the pages used, or abstains when the KB does not cover the question;
3. routes to a human reviewer whenever the rules require it.

The co-pilot never sends anything. Its output is a draft plus a decision (`draft_ready` / `needs_human` / `declined`) plus the reasons; a support agent sends.

Knowledge base: the four public Valetax help pages (deposit, withdraw, open an account, verify account), snapshotted as-is in `kb/pages`. What they do and do not say is in [`kb/KB_AUDIT.md`](kb/KB_AUDIT.md). The business case is in [`BUSINESS_CASE.md`](BUSINESS_CASE.md).

## Run it

```bash
pip install -e ".[dev]"            # add [openai] and/or [anthropic] for live models
python -m pytest -q
python cli.py process --brief --text "How long does a withdrawal take?"          # mock provider, no keys
python cli.py process --brief --provider openai --text "What is the minimum deposit?"   # needs OPENAI_API_KEY
python cli.py process tickets.jsonl --provider anthropic --model claude-sonnet-4-5      # needs ANTHROPIC_API_KEY
python cli.py eval --config mock   # harness smoke test; configs in evals/configs.yaml
python -m evals.business_case      # recompute the numbers from eval results + evals/assumptions.yaml
```

Each processed ticket is appended as one JSON line to `logs/<date>.jsonl`: decision, reasons, classification, citations, model, prompt version, KB version, tokens, cost, latency. Ticket text is stored PII-masked.

## How a ticket flows

```
ticket ──► PII mask ──► LLM (system prompt = rules + the whole KB) ──► JSON ──► pydantic
                                                                                 │ invalid → needs_human
                                                                                 ▼
                                                                        guards, in code
                      trading advice (classifier OR regex) ──────────────────► declined, fixed text
                      every citation must be a literal substring of a KB page
                      every number in the draft must be in a citation or in the ticket
                      no advice-like language in the draft
                      complaint / KYC / AML ───────────────────────────────► needs_human
                      account-specific question, negative+high, unsupported language ─► needs_human
                                                                                 ▼
                                                                         draft_ready ──► agent
```

Files: `copilot/schema.py` (contract), `prompts/draft_v1.md` (prompt), `copilot/guard.py` (rules), `copilot/pipeline.py` (glue + log), `copilot/kb.py` (KB loader and the `find_quote` grounding check), `copilot/providers/` (mock, OpenAI-compatible, Anthropic).

## Decisions and why

**The whole KB goes into the prompt; there is no retrieval in Phase 1.** Four pages are about 1,500 tokens. A retriever on four pages adds a failure mode (wrong chunk retrieved) and saves nothing. `KnowledgeBase.context_for(ticket)` is the single seam where retrieval plugs in when the KB outgrows the context window.

**Grounding is checked in code, not by the model.** The model must copy citations verbatim. `kb.find_quote()` looks for each quote as a literal substring of a snapshot page (whitespace- and quote-style-insensitive, nothing else). A citation that is not in the KB is dropped; a draft with no valid citation is dropped. Then every number in the draft (`8`, `60`, `48`, `1:2000`, `24`) must appear in a surviving citation or in the customer's own text, otherwise the draft is dropped. This is what makes "never invent policy, fees or timelines" a property of the system rather than a line in the prompt.

**Hard rules run after the model and do not depend on it.** A trading-advice request is declined if either the classifier or a regex says so; the decline text is fixed, not generated. Complaints and KYC/AML cases always go to a person, with the draft (if any) kept as a hint. The model's own `requires_account_lookup` flag routes account-specific questions ("my deposit has not arrived") to a person while still handing the agent the general facts.

**A bad model answer is a soft failure of one ticket.** Non-JSON, schema mismatch, provider timeout: the ticket comes out as `needs_human` with the reason, nothing is retried in a loop, nothing crashes.

**The KB is used as-is, gaps included.** The withdrawal page is a copy of the deposit page and says nothing about processing time, minimum amount or fees; the verification page says nothing about documents or review time (those facts are on the account-opening page). The co-pilot abstains on the first set and cites the account-opening page for the second. Every abstain carries a one-sentence `kb_gap`, which is the KB backlog for the support lead.

**Deterministic eval, no LLM judge.** 58 synthetic labelled tickets in `evals/tickets.jsonl`: 24 answerable (incl. cross-page answers and six languages), 12 KB gaps, 6 trading-advice requests (some disguised), 6 complaints/KYC, 4 prompt injections, 3 account-specific, 3 misc. Scores: classification accuracy, abstain precision/recall on KB gaps, raw citation validity (before the guard), coverage, and hard-rule violations judged on the final output. Violations must be zero for a configuration to be recommended.

**What was deliberately not built**: retrieval, a queue, a UI beyond the CLI, a ticket-system integration, an LLM-as-judge for draft wording. Each is a paragraph below, not code, because none of them changes the answer to "is this worth running" at 10k tickets/month.

## Phase 1 — ship

What is in this repository is Phase 1: one Python process, one LLM call per ticket, guards in code, a JSONL log, a CLI. To put it in front of agents:

- Wrap `Copilot.process()` in a small HTTP endpoint or a ticket-system webhook; the agent sees decision, reasons, draft, citations with URLs.
- Run it in **shadow for one week**: agents work as today; the co-pilot's draft is shown alongside. Measure how often the draft is used, how much it is edited (edit distance), and the handle time with and without it. Those three numbers replace the assumptions in `evals/assumptions.yaml`.
- Keys in the environment, prompts in git, every result stamped with prompt version and KB version.

## Phase 2 — scale

10,000 tickets a month is 14 an hour. Throughput is not the problem. These are:

- **The KB outgrows the context window.** Chunk pages by section with stable IDs, retrieve top-k by BM25 + embeddings, pass only those chunks. Citations are verified by the same `find_quote` against the same snapshots, so the guard does not change. `context_for()` is the only function that does.
- **The KB and SOPs change.** `kb/fetch.py` re-snapshots and re-hashes; a changed hash re-runs the eval set in CI before the new KB reaches production. SOPs that are not public pages go through the same snapshot format.
- **Quality drifts.** Eval in CI on every prompt change (today the mock metrics file is diffed; with keys, the live configs run on a schedule). A new prompt or model runs in shadow next to the current one before it is switched.
- **Agents are the feedback loop.** Draft-vs-sent edit distance per category and per KB page is the cheapest quality signal there is; drafts that are always rewritten point to a KB page that needs work.
- **Cost at volume.** A cheap model classifies everything; the stronger model drafts only tickets that are not already routed to a person. Cache answers to repeated questions by normalized text. Batch API for anything that is not interactive.
- **Operations.** Queue with idempotency on `ticket_id` so a redelivered ticket does not produce a second draft, dead-letter queue, alerts on rising `model_output_invalid`, rising abstain rate, or any hard-rule violation in the log.

## Honesty notes

- All tickets are synthetic and were labelled by hand. Urgency and sentiment labels are the author's judgement and are reported but not used for routing decisions beyond the negative+high rule.
- The mock provider is a keyword matcher that exists so the harness and CI run without keys. Its scores in `evals/results/mock.*` say nothing about model quality.
- Price per token in `copilot/providers/pricing.yaml` and every number in `evals/assumptions.yaml` are inputs, not findings.
- Built with Cursor as the agentic coding tool; commit history shows the order of work.
