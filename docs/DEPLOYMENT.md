# Audita — Hosting & Deployment

Status: v2.0 · 2026-07-27 · multi-tenant, Postgres-backed

## 1. Topology

One app container (FastAPI hosts the JSON API, the signed share-link workpapers, **and** the
built React SPA) plus **Postgres** for all tenant data: users, orgs, memberships, sessions,
invites, reports, invoices (scans as bytea), ledgers, close/review workbooks, and the
append-only event log. The `/data` volume now only holds the upload tempdir and the dev
signing-key fallback. Migrations run automatically at app startup.

## 2. Environment variables

| Var | Required | Default | Notes |
|---|---|---|---|
| `AUDITA_DATABASE_URL` | **prod: yes** | `postgresql://audita:audita@localhost:5434/audita` | Compose injects the in-network URL for the app container. |
| `AUDITA_SECRET_KEY` | **prod: yes** | dev: generated to `data/secret_key` | Signs report links. Rotating invalidates all outstanding links (sessions are unaffected — they are DB-backed). |
| `AUDITA_DATA_DIR` | no | `backend/data` (dev) / `/data` (container) | Upload tempdir + dev key only. |
| `AUDITA_STATIC_DIR` | no | unset (dev) / `/app/static` (container) | Enables SPA serving + `/app/*`, `/login`, `/signup` fallback. |
| `AUDITA_CORS_ORIGINS` | no | localhost:5173 | Comma-separated. Leave empty in single-container prod (same-origin). |
| `AUDITA_LINK_MAX_AGE` | no | `604800` (7 d) | Seconds. |
| `AUDITA_MAX_UPLOAD_MB` | no | `15` | App-level upload ceiling (413 beyond it). |
| `AUDITA_COOKIE_SECURE` | no | `1` | Set `0` only for plain-HTTP LAN testing; browsers exempt localhost anyway. |
| `GEMINI_API_KEY` | no | — | Enables Vision Agent + ADK agent runtime. |
| `AUDITA_AGENT_ORG_ID` | ADK only | — | Org UUID the conversational agent operates in. |
| `AUDITA_VISION_MODEL` | no | `gemini-2.5-flash` | |

## 3. Local / self-hosted (Docker)

```bash
cp .env.example .env            # fill AUDITA_SECRET_KEY
docker compose up --build
# http://localhost:8080  (landing, app, API — all one origin)
```

Postgres data persists in the `audita-pg` named volume; uploads in `audita-data`.

## 4. Development (no Docker for the app)

```bash
docker compose up -d postgres           # Postgres on localhost:5434

# backend
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
uvicorn app.main:app --port 8000        # avoid --reload on this Windows machine (venv lock)

# frontend (separate shell)
cd frontend && bun install && bun run dev   # http://localhost:5173, proxies /api and /r to :8000
```

Tests & lint: `cd backend && pytest && ruff check app tests` (tests need the compose postgres;
they create and truncate their own `audita_test` database) · frontend type-check: `bun run build`.

## 5. Production — GCP asia-south1 (Mumbai)

Chosen per the design doc (ADK/Gemini alignment + DPDP residency).

**Recommended shape: Cloud Run + Cloud SQL for PostgreSQL** (both asia-south1):

```bash
# one-time
gcloud auth login && gcloud config set project <PROJECT>
gcloud artifacts repositories create audita --repository-format=docker --location=asia-south1
gcloud sql instances create audita-pg --database-version=POSTGRES_16 \
  --region=asia-south1 --tier=db-g1-small
gcloud sql databases create audita --instance=audita-pg
gcloud sql users create audita --instance=audita-pg --password=<STRONG_PASSWORD>

# each deploy
gcloud builds submit --tag asia-south1-docker.pkg.dev/<PROJECT>/audita/app:latest .
gcloud run deploy audita \
  --image asia-south1-docker.pkg.dev/<PROJECT>/audita/app:latest \
  --region asia-south1 \
  --port 8080 \
  --add-cloudsql-instances <PROJECT>:asia-south1:audita-pg \
  --set-secrets AUDITA_SECRET_KEY=audita-secret-key:latest,AUDITA_DATABASE_URL=audita-database-url:latest \
  --allow-unauthenticated
```

Notes:
- `AUDITA_DATABASE_URL` secret uses the Cloud SQL unix socket form:
  `postgresql://audita:<PASSWORD>@/audita?host=/cloudsql/<PROJECT>:asia-south1:audita-pg`
- With state fully in Postgres, the app scales horizontally — no `--max-instances 1` and no
  `/data` volume needed on Cloud Run (uploads are transient tempfiles).
- `--allow-unauthenticated` is now correct: the app has its own login and strict per-org RBAC.
  Keep IAP if you want defence in depth during early pilots.
- Secrets in **Secret Manager**, never in env files on disk.
- TLS, disk encryption: platform defaults cover both.

## 6. Backups & retention

- Postgres is the whole state: enable **Cloud SQL automated backups + PITR** (7 daily).
- Restore drill = restore to a clone instance, point a fresh deploy at it; verify `/healthz`,
  log in, open one report.
- Upload tempfiles are transient; a purge job for anything older than 30 days remains on the
  list before non-founder-network clients (SECURITY.md §3).

## 7. Monitoring

- Liveness: `GET /healthz` (Cloud Run uses it via the container HEALTHCHECK).
- Cloud Run request logs + error reporting are sufficient at pilot scale.
- The product's own Operations page (`/app/ops`) is the functional heartbeat — if the queue
  isn't moving during a demo, something's wrong.
- Alert worth having on day one: 5xx rate > 1% over 5 min.

## 8. CI/CD (when a remote exists)

Pilot: `gcloud builds submit` from the laptop is honest and sufficient.
When the repo gets a remote: GitHub Actions — job 1 `ruff + pytest` (backend), job 2
`bun run build` (frontend type-gate), job 3 on main: Cloud Build → Cloud Run deploy with the
same flags as §5. Keep deploys manual-approval until Gate 1 pilots are live.
