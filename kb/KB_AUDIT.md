# Knowledge base audit

Four public Valetax help pages, snapshotted 2026-10-23 with `kb/fetch.py` (hashes in `manifest.json`). The task says to use them as they are, including gaps, overlaps and inconsistencies. This file lists what the pages actually state, so the co-pilot's abstentions can be checked against the source and so the support lead gets a KB backlog.

## What each page states

| Page | Facts the co-pilot may cite | Not on the page |
|------|-----------------------------|-----------------|
| `how-to-deposit` | Member Area → Deposit → payment channel → account details and amount. Minimum deposit "from 8 USD, depending on the account type". Any currency into a USD account at that day's exchange rate. "Deposits are instant", balance updated "within 60 minutes". Trading possible once the balance is updated. Deposit/withdrawal/transfer history is in the Member Area. | List of payment channels (the section is a row of logos, no text). Deposit fees. Per-account-type minimums. |
| `how-to-withdraw` | Member Area → payment channel → details and amount. Status "pending" = in queue, being processed, notified on approval. Rejection reasons: account not verified, data-entry error, insufficient margin; reason is sent by email. "Should you not receive your funds within 24 hours, please reach out to our friendly support team." | **Withdrawal processing time.** Minimum withdrawal amount. Withdrawal fees. Same-method / same-name rule. Which channels are available for withdrawal. |
| `how-to-open-an-account` | Create Account at valetax.com → details → Member Area → first deposit. Live account documents: proof of identification and proof of address (bank statement or utility bill) "not older than 6 months", name clearly displayed. "Account opening and document verification will be completed within 48 hours." Leverage "up to 1:2000 depending on account types". All accounts Islamic-friendly, no swap. Read Risk Disclosures, Privacy Policy, Terms of Business. | Account types and their minimums (page links out: "view details here"). Which countries are accepted. Demo vs live. Age requirement. |
| `how-to-verify-account` | Complete the fields and upload documents to the KYC profile; the account is then reviewed; then "verification completed". | **Which documents.** **How long review takes.** Rejection reasons. How to resubmit. Limits on an unverified account. Whether verification is required before deposit, before withdrawal, or both. |

## Inconsistencies and overlaps

1. **`how-to-withdraw` is a copy of `how-to-deposit`.** Step 3 on the withdrawal page reads "Enter your account details and amount to **deposit**". The FAQ block is identical on both pages (same nine questions, same text). The only withdrawal-specific content is three FAQ items that also appear on the deposit page.
2. **"24 hours" is not a processing SLA.** It is the threshold after which the customer should contact support. The co-pilot must not turn it into "withdrawals take up to 24 hours".
3. **`how-to-open-an-account` promises "3 quick and simple steps" and lists four.**
4. **Verification facts live on the wrong page.** Required documents and the 48-hour window are on the account-opening page, not on the verification page. A verification question is answered by citing `how-to-open-an-account`.
5. **"48 hours" covers "account opening and document verification" together.** Whether a re-submitted document resets the clock is not stated.
6. **Leverage.** The page states a fact (up to 1:2000) and, to "what leverage should I select", answers "dependent on your trading strategy and goals". The co-pilot may cite the fact; it may not recommend a setting (hard rule: no trading advice).
7. **Typos preserved in snapshots**: "request in in queue", "insifficient margin", "All our account are Islamic friendly and there is no swap is credited". Citations must match the snapshot text, typos included; the draft may paraphrase.
8. **Dead links.** "Click here", "view details here" point to pages outside the KB. The co-pilot cannot follow them and must not pretend to know what is there.

## Consequences for the co-pilot

- Questions that must end in **abstain** with the current KB: withdrawal processing time, withdrawal fee, minimum withdrawal, payment channels available, verification rejection reasons, account-type minimums, country eligibility, limits for unverified accounts.
- Questions that are **answerable, with the citation on a non-obvious page**: "what documents for verification" and "how long does verification take" → `how-to-open-an-account`.
- Questions that are **answerable from either of two pages**: "why was my withdrawal rejected", "what does pending mean" → cite `how-to-withdraw` (topical page), accept `how-to-deposit` as valid grounding too.

## KB backlog (for the support lead)

Each abstain the co-pilot logs carries a `kb_gap` sentence. With the current pages the first items are predictable:

1. Withdrawal processing time per channel, minimum withdrawal, fees.
2. Verification page: required documents, review time, rejection reasons, resubmission.
3. Payment channels as text, not logos, for deposit and for withdrawal.
4. Account types and minimum deposits inline, not behind a link.
