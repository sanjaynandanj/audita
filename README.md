# Audita

**GST audit agents for Indian businesses.** Agents do the grind — GST/ITC reconciliation, bank
reconciliation, month-end close — and a chartered accountant signs every rupee in the headline.

```
audita/
├── backend/     Python 3.12 · FastAPI · Postgres (multi-tenant, append-only event log)
│   │            deterministic matching engines · Google ADK agent layer · Gemini vision (env-gated)
│   ├── app/{auth,orgs,db,routers,engine,parsers,report,close,events,agents,vision,ap,books,review}
│   ├── tests/               134 tests (engine, parsers, auth/RBAC, tenancy isolation, API, event log, AP, books, review, workqueue)
│   └── sample_data/         GSTR-2B JSON, purchase register, bank statement + ledger
├── frontend/    TypeScript · React 19 · Tailwind v4 · Vite
│   └── src/pages/           Landing, Login/Signup, Workspace, ITC Recon, Bank Recon, Invoices, Books, Review, Close, Operations, Members
├── docs/        PRD · TRD · SECURITY · DEPLOYMENT
├── Dockerfile   multi-stage: bun builds SPA → python image serves API + app on :8080
└── docker-compose.yml       app + postgres:16
```

**Multi-tenant with strict RBAC.** Signup creates a workspace (org); owners invite members with
one-shot links at a role: `owner > reviewer > preparer > viewer`. Reviewers (CAs) verify and
sign off; sign-offs are identity-backed by the session — never a typed name. All data is
org-isolated in Postgres. Signed report links stay shareable but are view-only.

## The agents

| Agent | Status | Output |
|---|---|---|
| Recon Agent | in service | "₹X of input tax credit at risk" — GSTR-2B vs purchase register, every exception traced to source, CA sign-off column |
| Bank Recon Agent | in service | Classic BRS: unrecorded items, uncleared cheques, deposits in transit |
| Close Agent | in service | Per-period close workbook, 12 controls, named ticks |
| Invoice Agent | in service | Photo/PDF of a bill → extracted fields → human-confirmed row in the purchase register → feeds ITC recon |
| Bookkeeping Agent | in service | Bank transactions coded to a chart of accounts: deterministic rules first, LLM suggestions queued for review, learning loop from confirmations |
| Review Agent | in service | Month-end review workbook: deterministic P&L movement + anomaly flags (variance, new counterparties, round sums, GST drift), CA-narrated when configured |
| Agent Workspace | in service | The daily surface: every pending human decision from every agent in one queue, live activity feed alongside |
| Vision Agent | beta | Scanned-invoice field extraction (needs `GEMINI_API_KEY`) |

Product guarantees: headline counts **only human-verified exceptions** · append-only audit
trail (UPDATE/DELETE rejected at the DB) · signed expiring report links · precision over recall
(ambiguous matches quarantined, never guessed).

## Quick start (dev)

```bash
docker compose up -d postgres                 # Postgres on localhost:5434

# backend
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
uvicorn app.main:app --port 8000              # migrations run at startup

# frontend (second shell)
cd frontend && bun install && bun run dev     # http://localhost:5173
```

Sign up at `/signup` (creates your workspace), then try it with `backend/sample_data/`.
Tests: `cd backend && pytest` (uses the compose postgres). Lint: `ruff check app tests`.

## One-container run

```bash
cp .env.example .env      # set AUDITA_SECRET_KEY
docker compose up --build # http://localhost:8080
```

## ADK agent (conversational)

```bash
cd backend && set GEMINI_API_KEY=...          # Windows
set AUDITA_AGENT_ORG_ID=<org uuid>            # the workspace the agent works in
adk run app/agents                            # or: adk web app/agents
```

The agent orchestrates and explains; all rupee math stays in the deterministic engines.

## Docs

- [PRD](docs/PRD.md) — problem, wedge, gates, competitive frame
- [TRD](docs/TRD.md) — architecture, matching specs (normative), API, debt register
- [SECURITY](docs/SECURITY.md) — controls, honest gaps, DPDP posture, threat model
- [DEPLOYMENT](docs/DEPLOYMENT.md) — env vars, Docker, GCP asia-south1, backups

Reports are CA-reviewed workpapers, not statutory audit opinions.
