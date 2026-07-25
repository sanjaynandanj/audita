# Audita v2 — Agentic Finance Platform PRD

| | |
|---|---|
| Status | v2.0 draft · 2026-07-25 |
| Owner | Sanjay (founder) |
| Supersedes | `PRD.md` §7 exclusion of bookkeeping/AP automation |
| Reference | Numero+Royu acquisition (May 2026) — the "agentic system of work" category is now priced and validated |

## 1. Why expand now

PRD v1 deliberately stayed out of the Numero+Royu lane (general agentic finance-ops) and
committed to growing toward it *from the compliance wedge*. Two things changed:

1. **The category got validated and vacated.** Royu (Chennai, <1 yr old) was acquired for
   double-digit millions; the combined entity is US/CFO-office led. The India-SME,
   GST-compliance-anchored version of the same system of work is unserved.
2. **The wedge machinery is the moat.** Audita's append-only trail, headline gating, and
   CA-sign-off column are exactly what "agents doing bookkeeping" needs to be trusted.
   Expanding the agent surface *multiplies* the value of the trust layer rather than
   diluting the wedge — every new agent's output lands in the same verified-only,
   event-logged pipeline.

**Thesis unchanged: agents do the grind, a CA signs the number.** v2 widens "the grind"
from reconciliation to the full monthly finance loop: capture → categorize → reconcile →
close → review.

## 2. Product shape (target)

Four new capabilities on top of the shipped v1 agents, in build order:

| # | Agent | One-liner | Feeds the wedge how |
|---|---|---|---|
| P1 | **Invoice Agent** | Scanned/photographed purchase invoice → extracted fields → human-confirmed row in the purchase register | Confirmed invoices flow straight into ITC recon; Vision graduates from beta to a wired loop |
| P2 | **Bookkeeping Agent** | Bank/ledger transactions auto-categorized to a chart of accounts; low-confidence entries queued for review | Categorized ledger enables bank recon at account level + P3 |
| P3 | **Review Agent** | Month-end P&L snapshot, variance vs prior period, deterministic anomaly flags, LLM-narrated commentary | The "financial review" a CA does before signing — packaged as a workpaper annex |
| P4 | **Agent Workspace** | One review queue: every pending human decision from every agent in a single inbox with named sign-off | The "system of work" UX — the daily surface for the accountant + CA |

## 3. Non-negotiable invariants (inherited from v1)

Every new agent MUST:

1. **Never let an LLM compute or mutate a rupee amount.** LLMs extract (Vision), suggest
   (categorization), and narrate (review commentary). All totals come from deterministic
   code using `decimal.Decimal`.
2. **Land every action in the append-only event log** (`agent_events`, UPDATE/DELETE
   rejected by DB triggers). New action verbs per agent, same table.
3. **Gate headlines on human verification.** Nothing an agent produced counts in a
   headline figure until a named human confirms it. Suggested categorizations,
   extracted invoices, and anomaly flags are "pending" until confirmed.
4. **Quarantine ambiguity, never guess** (precision over recall). Low-confidence
   extraction/categorization goes to the review queue, not the books.
5. **Env-gate all LLM calls** (`GEMINI_API_KEY`); every feature degrades to
   manual-entry-with-audit-trail when unconfigured.

## 4. Phase specs

### Phase 1 — Invoice Agent (AP capture pipeline)

**Problem:** Vision extraction exists but is a dead end (TRD §7.3 known debt). Purchase
registers arrive as CSVs; the messy reality is photos and PDFs of bills.

**Flow:** upload invoice image/PDF → Vision extracts fields (supplier GSTIN, invoice no,
date, taxable value, IGST/CGST/SGST/cess, total) → draft invoice in **review queue** with
per-field editability → named human confirms (optional CA sign-off) → confirmed row lands
in a stored purchase register for the period → register export/feed into ITC recon.

**Backend:** new `app/ap/` module.
- `POST /api/invoices` — multipart upload; runs Vision if configured, else blank draft.
  Event: `invoice_uploaded`, `invoice_extracted`.
- `GET /api/invoices?period=YYYY-MM&status=` — list drafts/confirmed.
- `POST /api/invoices/{id}/confirm` — human-corrected fields + actor (+ ca_signoff).
  Event: `invoice_confirmed`. Reject edits after confirmation (append a correction as a
  new event, never mutate).
- `GET /api/registers/{period}.csv` — confirmed invoices as a purchase-register CSV
  parseable by the existing `parsers/purchase_register.py` (recon interop test required).
- Storage: JSON per invoice under `data/invoices/` (mirrors report storage), IDs via
  `secrets.token_hex(8)`.

**Frontend:** `Invoices` page — dropzone upload, queue table (thumbnail, extracted
fields inline-editable, confidence styling), confirm form (actor + sign-off), period
filter, "send to recon" affordance.

**Done when:** photo of a sample bill → confirmed register row → that register runs
through `/api/recon` and produces a workpaper. Tests: extraction gating (no key = blank
draft), confirm immutability, register CSV round-trip through existing parser.

### Phase 2 — Bookkeeping Agent (transaction categorization)

**Problem:** bank recon says *matched/unmatched*; books need every transaction coded to
an account. That coding is the bookkeeping grind.

**Scope:**
- Default Indian-SME chart of accounts (seedable, editable): ~40 accounts across
  income/COGS/opex/taxes (GST input/output split)/assets/liabilities.
- **Deterministic rules engine first:** user-defined rules (`description contains "GSTIN"
  / ref pattern / counterparty → account`) applied in priority order. Rule hits
  auto-categorize with `source=rule`.
- **LLM suggestion fallback** (env-gated): unmatched transactions get a *suggested*
  account + confidence; always `status=pending` until a human confirms.
- Review queue for pending items; confirm/override with actor. Events:
  `txn_categorized_rule`, `txn_category_suggested`, `txn_category_confirmed`.
- Output: a categorized ledger per period — the input for Phase 3.

**Done when:** sample bank statement → ≥80% auto-coded by rules on second run (rules
learned from first-run confirmations), remainder queued, zero unconfirmed suggestions in
any total.

### Phase 3 — Review Agent (monthly financial review)

**Scope:**
- Deterministic computation from the Phase-2 ledger: P&L snapshot, month-over-month
  variance per account, flags for (a) variance > threshold, (b) new counterparties,
  (c) round-sum anomalies, (d) GST control-account drift vs recon output.
- LLM narration (env-gated): turns computed flags into CA-style review notes. The
  narrative cites only computed numbers (same rule as the ADK orchestrator: never
  recompute).
- Output: a **Review workbook** annexed to the close — flags carry the same
  verified/pending gating and sign-off column.

**Done when:** two months of sample ledger → review workbook with flags; every number in
the narrative traceable to a computed figure.

### Phase 4 — Agent Workspace (unified review queue)

**Scope:**
- `GET /api/workqueue` — aggregates every pending human decision: unverified recon
  exceptions, draft invoices, pending categorizations, open close items, unreviewed
  flags. Each item: agent, type, ₹ impact, age, deep link.
- Workspace page replaces Operations as the default in-app landing: queue (actionable)
  + live activity feed (existing operations poll) side by side.
- ADK orchestrator gains tools: `get_workqueue`, `get_invoice_status`,
  `get_ledger_status` — so "what needs my attention?" works in agent chat.

**Done when:** an accountant can run the entire month (upload bills, code transactions,
verify exceptions, tick close, review flags) without leaving the workspace.

## 5. Sequencing & gates

- Build order P1 → P2 → P3 → P4; each phase ships behind its own page, no flag system.
- **Gate v2.1 (after P1):** one pilot business runs a real month of bills through the
  Invoice Agent into a recon workpaper. Bar: <2 min median human time per invoice.
- **Gate v2.2 (after P2+P3):** a CA reviews a generated Review workbook and states,
  unprompted, that it saved review time. Bar: ≥1 of the pilot CAs.
- P4 proceeds only if both gates pass; otherwise revisit which surface is the daily
  driver.
- v1 gates (Gate 0/Gate 1 in `PRD.md`) remain in force — v2 phases must not starve the
  interview/pilot motion.

## 6. Out of scope (still)

- Statutory audit opinions (unchanged, ICAI constraint).
- Sales-side invoicing / AR, payroll, e-invoicing (IRP) integration.
- Multi-tenant auth (capability URLs remain; Postgres+auth migration per TRD roadmap
  before any multi-business pilot).
- Live GSTN/GSP APIs, Tally two-way sync (import only).

## 7. Risks (v2-specific)

1. **Wedge starvation** — building the platform delays Gate 0/1 validation. Mitigation:
   phase gates above; stop after P1 if pilot signal weakens.
2. **Categorization trust** — one bad auto-coding erodes the "defensible" brand.
   Mitigation: invariant #3/#4 — suggestions never enter totals unconfirmed.
3. **Head-on with Numero+Royu** — they move into India SME. Assessment: their center of
   gravity is US CFO office; Audita's GST-native ingestion + CA network remains the
   rebuild-cost moat.
