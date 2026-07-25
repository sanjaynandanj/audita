# Audita — Product Requirements Document

| | |
|---|---|
| Status | v1.0 · 2026-07-23 |
| Owner | Sanjay (founder) |
| Source design doc | `~/.gstack/projects/projects/sanjay-no-branch-design-20260723-125100.md` (APPROVED) |

## 1. Problem

Indian businesses pay hefty fees to auditors and accountants while the underlying work — GST
reconciliation, input tax credit (ITC) matching, bank reconciliation, month-end close, audit
preparation — is a manual grind done in Tally exports and Excel. Blocked ITC from GSTR-2B
mismatches is a **direct cash cost** most SMEs never quantify.

Existing tools fail for two reasons observed firsthand:
1. **They don't fit the Indian stack** — Tally exports, GSTN portal JSON, GST invoice formats,
   scanned/photographed bills.
2. **They're priced for large firms** — the 100k+ small firms and the SMEs they serve stay manual.

## 2. Product thesis

**Agents do the grind. A chartered accountant signs the number.**

Audita is an agentic finance-ops platform whose differentiators are (a) the CA-in-the-loop
trust layer — the headline rupee figure counts only human-verified exceptions — and (b) native
handling of the messy Indian document stack. The moat is not "AI agents" (commoditizing); it is
verified, defensible output plus the boring ingestion pipe nobody else builds.

## 3. Target user

**Primary buyer:** CFO / founder / finance head of an Indian business that pays audit and
compliance fees. Not the CA firm partner; never the article assistant (feels the pain, owns no
budget).

**Primary daily user:** the business's accountant plus the reviewing CA (founder-network CA in
pilots).

## 4. The wedge

**GST/ITC reconciliation quantified in rupees.** Upload GSTR-2B + purchase register → one
workpaper: "₹X of input tax credit at risk", every exception traced to its source row, with a CA
sign-off column.

**Why a CFO pays over free tools (ClearTax Reconcile, NovaTally, ICAI EasyRecon):** those stop
at "here are your mismatches" — an exceptions list the team still chases. Audita closes the last
mile: scanned-bill resolution (Vision) + a CA's sign-off — "resolved, reviewed, and defensible",
not "matched". *This is a hypothesis under test in Gate 0 interviews.*

## 5. Shipped functionality (current)

| Agent | Status | What it does |
|---|---|---|
| **Recon Agent** | In service | GSTR-2B vs purchase register. Exact GSTIN + fuzzy invoice no. (ratio ≥ 90) + ±₹1/0.1% tolerance. Buckets: matched / books-only (at risk) / 2B-only (missed) / mismatched / unresolved. CDN, amendments, RCM, ISD quarantined. |
| **Bank Recon Agent** | In service | Statement vs books bank ledger. Signed amounts, ±7-day clearing window, ref/UTR similarity tiebreak. Outputs classic BRS: unrecorded items + uncleared/in-transit. |
| **Close Agent** | In service | Per-period close workbook, 12 controls, named ticks, every action event-logged. |
| **Vision Agent** | Beta (env-gated) | Gemini extraction of scanned invoice fields to resolve exceptions. Requires `GEMINI_API_KEY`. |
| **ADK orchestrator** | Dev tool | Google ADK agent (`adk run app/agents`) with 5 tools over the deterministic engines. Never recomputes amounts. |

Cross-cutting product guarantees:
- **Headline gating** — the ₹ headline starts at 0 and counts only exceptions verified by a
  named reviewer; a CA sign-off column travels with every exception.
- **Append-only audit trail** — every agent action lands in a log where UPDATE/DELETE are
  rejected at the database level; surfaced in-product (Operations page) and annexed to reports.
- **Signed expiring report links** — no unauthenticated report URLs; default 7-day expiry.
- **Excel export** — the workpaper a CFO forwards to their CA.

## 6. Success criteria & gates (pre-registered, from the design doc)

- **Gate 0 — before scale (in progress):** 15–20 SME CFO/founder conversations. Bars:
  (a) GST/ITC/notice pain raised unprompted by a majority; (b) the why-pay hypothesis
  (resolution + sign-off beats free lists) validated; (c) 3 businesses commit real data.
  **Also required before Gate 0 interviews:** ICAI ethics call resolving what the founder can
  sign and what "accompanied by an auditor" may legally claim.
- **Gate 1 — after Phase 1 build:** 3 real reports delivered (<1 day each) + verbal pricing
  acceptance from ≥1 CFO within 2 weeks of delivery (paid conversion window ~4 weeks).
- **Within 6 weeks of the CA-review layer shipping:** 3 paying pilots using the report monthly,
  sourced from the Gate 0 interview cohort. Stretch: 5.

**Pricing hypothesis:** flat ₹10k–25k per monthly report, anchored below the staff cost of
chasing mismatches and as a small fraction of the ₹-at-risk figure surfaced.

## 7. Out of scope (deliberate)

- **Statutory audit opinions.** Reports are CA-reviewed workpapers. In India, statutory audits
  must be signed by practicing CAs in CA-owned firms; a software company cannot be the auditor
  of record. The partner-CA delivery network (Modus-for-India) is the declared endgame, pending
  ICAI fee-sharing/networking legal review.
- General bookkeeping/AP automation (Numero+Royu's funded lane) — Audita grows toward it from
  the compliance wedge, not head-on.
- %-of-recovered-ITC pricing as default (attribution problem: GSTR-3B reports aggregates).
- Multi-tenant auth, GSP/ASP live GSTN APIs — see TRD roadmap.

## 8. Competitive frame

| Player | Lane | Audita's answer |
|---|---|---|
| Numero + Royu ($XXm acq., 2026) | General agentic finance-ops, US-led | Compliance wedge + CA trust layer they'd have to rebuild |
| CORAA | AI audit tools sold to CA firms | Different buyer (business, not firm) |
| ClearTax / NovaTally / ICAI EasyRecon | GST recon lists | Last-mile: resolution + sign-off + workpaper |
| Modus ($85M, Lightspeed) | AI-native audit via partner firms, US | The India analogue is Audita's endgame (Approach C) |

## 9. Risks

1. **Why-pay fails Gate 0** — CFOs satisfied with free exceptions lists → rework wedge toward
   notice-response / audit-readiness packs.
2. **ICAI constraint bites** — sign-off must be downgraded to "CA-reviewed" → test that claim
   honestly in interviews.
3. **Speed of incumbents** — ClearTax adds a resolution layer → moat shifts entirely to the
   CA network + workpaper defensibility.
4. **Founder tech-first bias** (self-identified) — mitigated by the pre-registered gates.
