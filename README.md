# Support-ticket co-pilot for a retail FX/CFD broker

Classifies an incoming support ticket (category, urgency, language, sentiment), drafts a reply grounded in the knowledge base with citations or abstains when the KB does not cover the question, and routes to a human reviewer whenever the rules require it. The co-pilot never sends anything: a person does.

Status: work in progress. Skeleton, KB snapshots and data contract are in place; pipeline, guards, CLI, eval and business case follow.

## Layout

```
kb/                 four Valetax help pages as committed snapshots + KB_AUDIT.md + fetch.py
copilot/schema.py   data contract: Ticket in, Result out (pydantic)
copilot/kb.py       KB loader, context_for() seam for Phase 2 retrieval, find_quote() grounding check
copilot/providers/  mock (deterministic, no keys), openai-compatible, anthropic; pricing.yaml
tests/
```

## Run

```
pip install -e ".[dev]"
python -m pytest -q
python kb/fetch.py        # refresh the KB snapshots (changes the KB version hash)
```

No real customer data is used anywhere in this repository. All tickets in the eval set are synthetic.
