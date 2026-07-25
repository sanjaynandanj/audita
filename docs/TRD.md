# Audita — Technical Requirements Document

| | |
|---|---|
| Status | v1.0 · 2026-07-23 |
| Stack decision record | see §2 |

## 1. Architecture

```
                      ┌─────────────────────────────────────────────┐
                      │              Browser (React SPA)            │
                      │  Landing · ITC Recon · Bank Recon · Close · │
                      │  Operations (live queue, 2.5s poll)         │
                      └───────────────┬─────────────────────────────┘
                                      │ HTTPS (JSON + multipart)
                      ┌───────────────▼─────────────────────────────┐
                      │            FastAPI (backend/app)            │
                      │                                             │
   /api/recon ────────►  parsers ──► engine.matcher ──► report      │
   /api/bankrec ──────►  parsers.bank ─► engine.bank ─► bank_report │
   /api/close/* ──────►  close.workbook                             │
   /api/operations ───►  events.log (read)                          │
   /r/{token}* ───────►  server-rendered workpaper + xlsx export    │
                      │        │                │                   │
                      │        ▼                ▼                   │
                      │  ┌───────────┐   ┌──────────────────┐       │
                      │  │ data/*.json│  │ events.db (SQLite)│      │
                      │  │ reports,   │  │ agent_events      │      │
                      │  │ bankrecs,  │  │ APPEND-ONLY       │      │
                      │  │ close      │  │ (triggers block   │      │
                      │  └───────────┘  │  UPDATE/DELETE)   │       │
                      │                 └──────────────────┘        │
                      │  agents/ (Google ADK, gemini-2.5-flash)     │
                      │    5 tools over the deterministic engines   │
                      │  vision/ (Gemini extraction, env-gated)     │
                      └─────────────────────────────────────────────┘
```

**Prime rule:** all rupee math is deterministic code. The LLM layer (ADK agent, Vision)
orchestrates and extracts; it never computes, adjusts, or estimates amounts.

## 2. Stack decisions (and why)

| Layer | Choice | Rationale |
|---|---|---|
| Backend | **Python 3.12+ / FastAPI** | Google ADK is Python-first; Gemini SDK native; Decimal arithmetic; the team can move fast. Rust was considered and rejected: no ADK support, slower iteration, zero perf need at pilot scale. |
| Frontend | **TypeScript + React 19 + Tailwind v4 + Vite** | Typed API client; industrial design system in utility CSS; instant HMR. |
| Agents | **Google ADK** (`google-adk`), model `gemini-2.5-flash` | Explicit product requirement; tools-over-engine pattern keeps determinism. |
| Vision | **Gemini** via `google-genai` (optional extra) | Aligned with ADK; env-gated so the core runs without any API key. |
| Storage | **JSON documents + SQLite event log** (Phase ≤3) | Single-tenant pilot scale; zero ops. Postgres migration path documented (§7). |
| Money | **`decimal.Decimal` end-to-end, serialized as strings** | Floats never touch rupee amounts — including in JSON payloads. |
| Fuzzy matching | **rapidfuzz** (difflib fallback) | Fast, deterministic ratios. |
| Excel | **openpyxl** | Workpaper export. |
| Signing | **itsdangerous** URLSafeTimedSerializer | Expiring signed report links, per-purpose salts. |
| Lint | **ruff** (E,F,W,I,B,UP,SIM · line 120) | Clean as of this document. |
| Packaging | multi-stage **Docker** (bun build → python:3.12-slim) | One container serves API + SPA. |

## 3. Matching specifications (normative)

### 3.1 ITC recon (`engine/matcher.py`)
- Key: **exact normalized GSTIN** (upper, trimmed) — never fuzzy.
- Invoice number: normalized (uppercase, strip non-alphanumerics, strip leading zeros);
  rapidfuzz ratio **≥ 90 ⇒ pair**; **75–89 ⇒ both records to `unresolved`** (ambiguous —
  never silently matched or counted at risk); **< 75 ⇒ no pair**.
- Amount tolerance: `max(₹1, 0.1%)`, applied independently to taxable value and total tax.
  Within both ⇒ `matched`; paired but outside ⇒ `mismatched` (₹ at stake = |tax delta|).
- Books-without-2B ⇒ `books_only` (ITC at risk = total tax). 2B-without-books ⇒ `gstr2b_only`
  (missed ITC).
- **Quarantine (Phase 1):** credit/debit notes, GSTR-2B amendments (b2ba/cdnra), reverse
  charge, ISD ⇒ `unresolved`, excluded from every headline.
- Determinism: books processed in input order; candidate choice by (ratio, amount-closeness).

### 3.2 Bank recon (`engine/bank.py`)
- Sign convention: statement credit = +in / ledger **debit** = +in (the accounting mirror is
  handled in parsers, tested).
- Match: same sign + amount within tolerance + date gap ≤ **7 days** (unparseable dates don't
  disqualify); best of ref/description partial-ratio breaks ties.
- Bank-without-books ⇒ `bank_only` (unrecorded). Books-without-bank ⇒ `books_only`
  (uncleared cheque / deposit in transit).

### 3.3 Headline gating (`report/builder.py`)
`verified_at_risk = Σ verified exceptions` only. Pending and unresolved are reported separately
and never merged into the headline. Verification requires a named actor; CA sign-off optional
but recorded and displayed.

## 4. API surface

| Method & path | Purpose |
|---|---|
| `POST /api/recon` | multipart (client_name, period_note, gstr2b_file, register_file) → `{report_id, token}` |
| `GET /api/reports/{token}` | report JSON + audit trail |
| `POST /api/reports/{token}/verify` | `{exception_id, actor, ca_signoff}` → updated report |
| `POST /api/bankrec` | multipart (statement_file, ledger_file, …) → `{report_id, token}` |
| `GET /api/bankrec/{token}` | BRS JSON |
| `GET /api/close/{period}` | workbook for `YYYY-MM` (auto-created) |
| `POST /api/close/{period}/item` | `{key, done, actor, note}` — done requires actor |
| `POST /api/invoices` | multipart (period, invoice_file) → draft with Vision-extracted fields (blank if unconfigured) |
| `GET /api/invoices` · `GET /api/invoices/{id}` | list/detail drafts + confirmed (+ audit trail) |
| `POST /api/invoices/{id}/confirm` | `{fields, actor, ca_signoff}` — immutable once confirmed (409 on re-confirm) |
| `GET /api/registers/{period}.csv` | confirmed invoices as a purchase-register CSV (feeds `/api/recon`) |
| `POST /api/books/{period}/transactions` | multipart statement upload → rules auto-code, misses queue (LLM suggestions attached if configured) |
| `GET /api/books/{period}` | ledger + per-account summary (coded+confirmed only; pending outside totals) |
| `POST /api/books/{period}/txn/{id}/confirm` | `{account_code, actor, rule_pattern?}` — immutable; optional rule creation (learning loop) |
| `GET /api/books/{period}/ledger.csv` | categorized ledger export (Phase 3 input) |
| `GET/POST /api/books/coa` · `GET/POST/DELETE /api/books/rules` | chart of accounts + deterministic categorization rules |
| `GET /api/operations?limit=` | recent events from the append-only log |
| `GET /r/{token}` · `POST /r/{token}/verify` · `GET /r/{token}/export.xlsx` | server-rendered workpaper + Excel (share-link surface) |
| `GET /healthz` | liveness + SPA flag |
| `GET /` · `GET /app/{...}` | SPA when `AUDITA_STATIC_DIR` is set; legacy Jinja upload page otherwise |

Errors: 400 (bad input/file type/missing actor), 404 (bad signature/not found),
410 (expired link). Upload types allowlisted: `.json .csv .xlsx .xls`.

## 5. Data model

- `data/reports/{id}.json` — ITC report (exceptions carry verified/verified_by/ca_signoff).
- `data/bankrecs/{id}.json` — BRS report.
- `data/close/{YYYY-MM}.json` — close workbook.
- `data/invoices/{id}.json` + `data/invoices/files/` — AP capture drafts/confirmed + stored bill artifacts.
- `data/books/coa.json` · `data/books/rules.json` · `data/books/ledgers/{YYYY-MM}.json` —
  chart of accounts, categorization rules, per-period categorized ledger.
- `data/events.db` — `agent_events(event_id, agent, action, input_doc_ref, output_ref, actor,
  reviewed_by, ts)`; SQLite **triggers reject UPDATE and DELETE**.
- `data/uploads/` — raw uploaded files (retention policy: delete on request; see SECURITY.md).
- `data/secret_key` — generated at first boot **iff** `AUDITA_SECRET_KEY` unset (dev only).

Report IDs: `secrets.token_hex(8)`; path traversal blocked by `isalnum()` check (tested).

## 6. Non-functional requirements

| Concern | Requirement | Current state |
|---|---|---|
| Correctness | precision > recall everywhere; ambiguous ⇒ unresolved | enforced + tested (92 tests) |
| Recon latency | < 60 s for a 10k-line register | in-memory matching; O(n·m) per GSTIN group — fine at pilot scale; index by invoice prefix if needed |
| Availability | pilot: single instance, restart-safe | stateless app over durable volume |
| Auditability | every mutating action event-logged with actor | enforced |
| I18n of money | en-IN formatting, tabular numerals | frontend `inr()` |

## 7. Known debt & roadmap

1. **No user auth.** Capability-URL security only (signed expiring links). Acceptable for
   founder-operated pilots; **required before multi-tenant:** OIDC (Google Identity Platform),
   org/tenant scoping of stores, RBAC (reviewer vs viewer). See SECURITY.md.
2. **SQLite + JSON files** — migrate event log + reports to Postgres (same `agent_events`
   shape; append-only via REVOKE + row-level policy) when >1 instance or >1 tenant.
3. **Vision loop not wired into the exception UI** — extraction exists (`vision/gemini.py`);
   the resolve-exception-with-scan flow is the next product increment.
4. **GSTN access** — file upload today; GSP/ASP API licensing decision deferred until volume.
5. **`.xls` (legacy BIFF)** — accepted by the allowlist but openpyxl only parses `.xlsx`;
   either add xlrd or drop `.xls` from the allowlist.
6. **Frontend tests** — none yet (engine/API covered); add Playwright smoke on the four pages.
7. **Windows dev note** — uvicorn `--reload` can lock the venv dir on this machine; restart
   the process instead.
