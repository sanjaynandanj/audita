# Audita — Hosting & Deployment

Status: v1.0 · 2026-07-23

## 1. Topology

One container serves everything: FastAPI hosts the JSON API, the signed share-link workpapers,
**and** the built React SPA (multi-stage Dockerfile: bun builds `frontend/dist` → copied into
the Python image, `AUDITA_STATIC_DIR=/app/static`). One process, one port (8080), one
persistent volume (`/data`).

> Honesty note: the Dockerfile has not yet been validated by a full `docker build` on the dev
> machine (Docker daemon was down when this doc was written). Validate it before first deploy —
> §3 step 1.

## 2. Environment variables

| Var | Required | Default | Notes |
|---|---|---|---|
| `AUDITA_SECRET_KEY` | **prod: yes** | dev: generated to `data/secret_key` | Signs report links. Rotating invalidates all outstanding links. |
| `AUDITA_DATA_DIR` | no | `backend/data` (dev) / `/data` (container) | Must be a persistent volume in prod. |
| `AUDITA_STATIC_DIR` | no | unset (dev) / `/app/static` (container) | Enables SPA serving + `/app/*` fallback. |
| `AUDITA_CORS_ORIGINS` | no | localhost:5173 | Comma-separated. Leave empty in single-container prod (same-origin). |
| `AUDITA_LINK_MAX_AGE` | no | `604800` (7 d) | Seconds. |
| `GEMINI_API_KEY` | no | — | Enables Vision Agent + ADK agent runtime. |
| `AUDITA_VISION_MODEL` | no | `gemini-2.5-flash` | |

## 3. Local / self-hosted (Docker)

```bash
cp .env.example .env            # fill AUDITA_SECRET_KEY
docker compose up --build       # step 1: this also validates the Dockerfile
# http://localhost:8080  (landing, app, API — all one origin)
```

Data persists in the `audita-data` named volume.

## 4. Development (no Docker)

```bash
# backend
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
uvicorn app.main:app --port 8000        # avoid --reload on this Windows machine (venv lock)

# frontend (separate shell)
cd frontend && bun install && bun run dev   # http://localhost:5173, proxies /api and /r to :8000
```

Tests & lint: `cd backend && pytest && ruff check app tests` · frontend type-check: `bun run build`.

## 5. Production — GCP asia-south1 (Mumbai)

Chosen per the design doc (ADK/Gemini alignment + DPDP residency).

**Pilot-recommended shape: Cloud Run + Cloud Storage volume mount** (or a small Compute Engine
VM with a persistent disk if you prefer boring):

```bash
# one-time
gcloud auth login && gcloud config set project <PROJECT>
gcloud artifacts repositories create audita --repository-format=docker --location=asia-south1
gsutil mb -l asia-south1 gs://<PROJECT>-audita-data

# each deploy
gcloud builds submit --tag asia-south1-docker.pkg.dev/<PROJECT>/audita/app:latest .
gcloud run deploy audita \
  --image asia-south1-docker.pkg.dev/<PROJECT>/audita/app:latest \
  --region asia-south1 \
  --port 8080 \
  --min-instances 1 --max-instances 1 \
  --add-volume name=data,type=cloud-storage,bucket=<PROJECT>-audita-data \
  --add-volume-mount volume=data,mount-path=/data \
  --set-secrets AUDITA_SECRET_KEY=audita-secret-key:latest \
  --no-allow-unauthenticated
```

Non-negotiables for the pilot:
- **`--max-instances 1`.** SQLite over a GCS FUSE mount is single-writer; do not scale
  horizontally until the Postgres migration (TRD §7.2).
- **`--no-allow-unauthenticated` + IAM/IAP** until user auth exists (SECURITY.md §3). Share
  access with pilot users via IAP; report links still work for authenticated viewers.
- Secret in **Secret Manager**, never in env files on disk.
- TLS, disk encryption: platform defaults cover both.

## 6. Backups & retention

- `/data` is the whole state. GCS bucket: enable **object versioning**; or for a VM disk,
  daily snapshot schedule (7 daily + 4 weekly).
- Restore drill = point a fresh deploy at a bucket/disk copy; verify `/healthz` and one report.
- Purge job (`data/uploads` > 30 days) — required before non-founder-network clients
  (SECURITY.md §3).

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
