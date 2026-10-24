# Support-ticket co-pilot for a retail FX/CFD broker

For every incoming ticket the co-pilot:

1. classifies it: category, urgency, language, sentiment;
2. drafts a reply grounded in the knowledge base with citations to the pages used, or abstains when the KB does not cover the question;
3. routes to a human reviewer whenever the rules require it.

The co-pilot never sends anything. Its output is a draft plus a decision (`draft_ready` / `needs_human` / `declined`) plus the reasons; a support agent sends.

Knowledge base: the four public Valetax help pages (deposit, withdraw, open an account, verify account), snapshotted as-is in `kb/pages`. What they do and do not say is in [`kb/KB_AUDIT.md`](kb/KB_AUDIT.md). The business case is in [`BUSINESS_CASE.md`](BUSINESS_CASE.md).

## Run it

```bash
pip install -e ".[dev,openai]"
python -m pytest -q
python cli.py process --brief --text "How long does a withdrawal take?"      # mock provider, no keys, no network

# live: any OpenAI-compatible endpoint; keys from the environment or a local .env / api_key.env (git-ignored)
python cli.py process --brief --provider openai --model qwen-max \
    --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 --api-key-env ALICLOUD_API_KEY \
    --text "How long does verification take? I uploaded my documents this morning."
python cli.py process --brief --provider anthropic --model claude-sonnet-5-5 \
    --text "How long does a withdrawal take?"                                          # needs ANTHROPIC_API_KEY

python cli.py eval --config mock             # harness smoke test
python cli.py eval --config C_strong_guard   # one live configuration; all of them are in evals/configs.yaml
python -m evals.run_eval --config C_strong_guard --rescore   # re-score saved outputs after a label fix, no API calls
python -m evals.business_case                # recompute the numbers from eval results + evals/assumptions.yaml
```

Each processed ticket is appended as one JSON line to `logs/<date>.jsonl`: decision, reasons, classification, citations, model, prompt version, KB version, tokens, cost, latency. Ticket text is stored PII-masked.

Example output:

```
cli: draft_ready  [verification/medium/en/neutral]
  reasons: -
  draft: Your account verification is currently being reviewed. Typically, account opening and document
         verification are completed within 48 hours.
  cite [how-to-open-an-account]: "Account opening and document verification will be completed within 48 hours."

cli: needs_human  [withdrawal/medium/en/neutral]
  reasons: kb_gap
  kb_gap: The knowledge base does not state how long a withdrawal takes to be processed.
```

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
                                              optional: claim check (2nd narrow model call) ─► needs_human
                                                                                 ▼
                                                                         draft_ready ──► agent
```

Files: `copilot/schema.py` (contract), `prompts/draft_v2.md` (prompt; `draft_v1.md` kept for the before/after), `copilot/guard.py` (rules), `copilot/verifier.py` + `prompts/verify_v1.md` (optional claim check), `copilot/pipeline.py` (glue + log), `copilot/kb.py` (KB loader and the `find_quote` grounding check), `copilot/providers/` (mock, OpenAI-compatible, Anthropic).

## What the eval says

58 labelled synthetic tickets, deterministic scoring. Qwen through the OpenAI-compatible DashScope endpoint, Claude through the Anthropic Messages API. Full numbers in `evals/results/*.metrics.json`; the per-ticket outputs, including what the model said before the guard, are in the `.json` files next to them.

| Config | Model | Code guard | Claim check | Category acc | Decision acc | Abstain recall on KB gaps | Coverage (answerable) | Tickets with a wrong statement | $ / ticket |
|---|---|---|---|---|---|---|---|---|---|
| A | qwen-flash | off | off | 0.81 | 0.91 | 0.64 | 0.85 | 3 (incl. 1 invented citation) | 0.00018 |
| B v1 | qwen-flash, prompt v1 | on | off | 0.91 | 0.90 | 0.43 | 0.92 | 3 | 0.00017 |
| B | qwen-flash | on | off | 0.88 | 0.95 | 0.64 | 0.92 | 3 | 0.00019 |
| C | qwen-max | on | off | 0.98 | 0.98 | 0.86 | 0.88 | 1 | 0.0048 |
| **D** | **claude-sonnet-5-5** | **on** | **off** | **0.97** | **0.93** | **0.79** | **0.81** | **0** | **0.0107** |
| E | qwen-flash (+ qwen-plus check) | on | on | 0.85 | 0.88 | 0.71 | 0.54 | 0 | 0.00029 |
| F | qwen-max (+ qwen-plus check) | on | on | 0.98 | 0.90 | 0.86 | 0.50 | 0 | 0.0049 |

Three things the numbers show:

- **Prompt v1 → v2 was driven by the eval, not by taste.** The first live run declined factual product questions ("what is your maximum leverage") as trading advice and turned "contact support if not received within 24 hours" into a 24-hour delivery promise. v2 names both failure modes. Decision accuracy 0.88 → 0.95 and abstain recall on KB gaps 0.43 → 0.64 on the same model.
- **The code guard cannot catch a misread quote.** The wrong statements that remain under the guard are valid citations used for a claim the quote does not make: "any preferred currency" as "we do not support crypto", "begin trading immediately" as "yes, you can trade unverified", and, on Qwen Max, the 24-hour contact-support sentence rewritten as "funds should be received within 24 hours". Quoting that sentence as the contact threshold is not counted. Sonnet (D) did the first and not the second, which is why its violation count is 0. Its two non-draft outcomes on answerable tickets were safe: one unparseable JSON, one draft dropped because it stated "48 hours" without citing that sentence.
- **The claim check removes the misreads and half the drafts.** E and F reach 0 violations the way D does, by refusing correct translations along with the bad sentences. D gets there in one call.
- **Zero hard-rule violations across all configurations**: every trading-advice request was declined (including the one hidden in a prompt injection), every complaint and KYC case went to a person, no draft stated a KYC outcome.

## Decisions and why

**The whole KB goes into the prompt; there is no retrieval in Phase 1.** Four pages are about 1,500 tokens. A retriever on four pages adds a failure mode (wrong chunk retrieved) and saves nothing. `KnowledgeBase.context_for(ticket)` is the single seam where retrieval plugs in when the KB outgrows the context window.

**Grounding is checked in code, not by the model.** The model must copy citations verbatim. `kb.find_quote()` looks for each quote as a literal substring of a snapshot page (whitespace- and quote-style-insensitive, nothing else). A citation that is not in the KB is dropped; a draft with no valid citation is dropped. Then every number in the draft (`8`, `60`, `48`, `1:2000`, `24`) must appear in a surviving citation or in the customer's own text, otherwise the draft is dropped. This is what makes "never invent policy, fees or timelines" a property of the system rather than a line in the prompt.

**Hard rules run after the model and do not depend on it.** A trading-advice request is declined if either the classifier or a regex says so; the decline text is fixed, not generated. Complaints and KYC/AML cases always go to a person, with the draft (if any) kept as a hint. The model's own `requires_account_lookup` flag routes account-specific questions ("my deposit has not arrived") to a person while still handing the agent the general facts.

**A bad model answer is a soft failure of one ticket.** Non-JSON, schema mismatch, provider timeout: the ticket comes out as `needs_human` with the reason, nothing is retried in a loop, nothing crashes.

**The one model-based check is optional, narrow and measured.** `verify_claims` sends only the quotes and the draft (no ticket, no KB, no role) to a model and asks which sentences the quotes do not state. It is the only way to catch a misread quote, it is switched on per configuration, and the eval table shows exactly what it costs in coverage.

**The KB is used as-is, gaps included.** The withdrawal page is a copy of the deposit page and says nothing about processing time, minimum amount or fees; the verification page says nothing about documents or review time (those facts are on the account-opening page). The co-pilot abstains on the first set and cites the account-opening page for the second. Every abstain carries a one-sentence `kb_gap`, which is the KB backlog for the support lead.

**Deterministic eval, no LLM judge for scoring.** 58 synthetic labelled tickets in `evals/tickets.jsonl`: 24 answerable (incl. cross-page answers and six languages), 14 KB gaps, 6 trading-advice requests (some disguised), 6 complaints/KYC, 4 prompt injections, 3 account-specific, 1 greeting. Scores: classification accuracy, abstain precision/recall on KB gaps, raw citation validity (before the guard), coverage, and violations judged on the final output (invalid citation, uncited number, advice language, a draft for a human-only case, or a forbidden phrase such as an invented timeline). Labels were corrected twice after reading live outputs; `--rescore` re-applies labels to saved outputs so a label fix never needs an API call.

**What was deliberately not built**: retrieval, a queue, a UI beyond the CLI, a ticket-system integration, tuning of the claim check. Each is a paragraph below, not code, because none of them changes the answer to "is this worth running" at 10k tickets/month.

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
- **The claim check, tuned.** Today it is all-or-nothing. Phase 2 runs it only where misreads happen (the eval says: withdrawal timelines), uses agent accept/edit decisions to measure its precision, and relaxes it where it rejects correct translations.
- **Cost at volume.** A cheap model classifies everything; the stronger model drafts only tickets that are not already routed to a person. Cache answers to repeated questions by normalized text. Batch API for anything that is not interactive.
- **Operations.** Queue with idempotency on `ticket_id` so a redelivered ticket does not produce a second draft, dead-letter queue, alerts on rising `model_output_invalid`, rising abstain rate, or any hard-rule violation in the log.

## Honesty notes

- All tickets are synthetic and were labelled by hand. Urgency and sentiment labels are the author's judgement and are reported but not used for routing decisions beyond the negative+high rule.
- The mock provider is a keyword matcher that exists so the harness and CI run without keys. Its scores in `evals/results/mock.*` say nothing about model quality.
- Price per token in `copilot/providers/pricing.yaml` and every number in `evals/assumptions.yaml` are inputs, not findings.
- Models were chosen by the keys at hand: Qwen on DashScope, Claude on the Anthropic API. Both sit behind the same `Provider` interface; switching is a block in `evals/configs.yaml`, and the eval is how the choice was made.
- Built with Cursor as the agentic coding tool; commit history shows the order of work: KB snapshot and audit → contract → guards → eval set → first live run → prompt v2 and label fixes → claim check → business case.
