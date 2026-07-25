# Audita

**GST audit agents for Indian businesses.** Agents do the grind — GST/ITC reconciliation, bank
reconciliation, month-end close — and a chartered accountant signs every rupee in the headline.

```
audita/
├── backend/     Python 3.12 · FastAPI · deterministic matching engines · SQLite append-only
│   │            event log · Google ADK agent layer · Gemini vision (env-gated)
│   ├── app/{engine,parsers,report,close,events,agents,vision,ap,books,review}
│   ├── tests/               106 tests (engine, parsers, report gating, API, event log, AP, books, review)
│   └── sample_data/         GSTR-2B JSON, purchase register, bank statement + ledger
├── frontend/    TypeScript · React 19 · Tailwind v4 · Vite
│   └── src/pages/           Landing, ITC Recon, Bank Recon, Invoices, Books, Review, Close, Operations
├── docs/        PRD · TRD · SECURITY · DEPLOYMENT
├── Dockerfile   multi-stage: bun builds SPA → python image serves API + app on :8080
└── docker-compose.yml
```

## The agents

| Agent | Status | Output |
|---|---|---|
| Recon Agent | in service | "₹X of input tax credit at risk" — GSTR-2B vs purchase register, every exception traced to source, CA sign-off column |
| Bank Recon Agent | in service | Classic BRS: unrecorded items, uncleared cheques, deposits in transit |
| Close Agent | in service | Per-period close workbook, 12 controls, named ticks |
| Invoice Agent | in service | Photo/PDF of a bill → extracted fields → human-confirmed row in the purchase register → feeds ITC recon |
| Bookkeeping Agent | in service | Bank transactions coded to a chart of accounts: deterministic rules first, LLM suggestions queued for review, learning loop from confirmations |
| Review Agent | in service | Month-end review workbook: deterministic P&L movement + anomaly flags (variance, new counterparties, round sums, GST drift), CA-narrated when configured |
| Vision Agent | beta | Scanned-invoice field extraction (needs `GEMINI_API_KEY`) |

Product guarantees: headline counts **only human-verified exceptions** · append-only audit
trail (UPDATE/DELETE rejected at the DB) · signed expiring report links · precision over recall
(ambiguous matches quarantined, never guessed).

## Quick start (dev)

```bash
# backend
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
uvicorn app.main:app --port 8000

# frontend (second shell)
cd frontend && bun install && bun run dev     # http://localhost:5173
```

Try it with `backend/sample_data/`. Tests: `cd backend && pytest`. Lint: `ruff check app tests`.

## One-container run

```bash
cp .env.example .env      # set AUDITA_SECRET_KEY
docker compose up --build # http://localhost:8080
```

## ADK agent (conversational)

```bash
cd backend && set GEMINI_API_KEY=...          # Windows
adk run app/agents                            # or: adk web app/agents
```

The agent orchestrates and explains; all rupee math stays in the deterministic engines.

## Docs

- [PRD](docs/PRD.md) — problem, wedge, gates, competitive frame
- [TRD](docs/TRD.md) — architecture, matching specs (normative), API, debt register
- [SECURITY](docs/SECURITY.md) — controls, honest gaps, DPDP posture, threat model
- [DEPLOYMENT](docs/DEPLOYMENT.md) — env vars, Docker, GCP asia-south1, backups

Reports are CA-reviewed workpapers, not statutory audit opinions.
