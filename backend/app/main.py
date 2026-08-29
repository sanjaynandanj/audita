"""Audita — GST audit agents platform.

Multi-tenant: every workspace (org) gets isolated Postgres-backed stores,
strict RBAC per membership (owner > reviewer > preparer > viewer), and an
append-only event log. Reports are shared via signed expiring links
(view-only); every verification is identity-backed by a logged-in reviewer.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .auth.router import router as auth_router
from .db.migrate import migrate
from .orgs.router import router as orgs_router
from .routers import bankrec, books, close, invoices, public, recon, review, workqueue


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        with db.open_pool().connection() as conn:
            migrate(conn)
    except Exception as exc:
        logging.getLogger("audita").warning("Postgres unavailable at startup: %s", exc)
    yield
    db.close_pool()


app = FastAPI(title="Audita", docs_url=None, redoc_url=None, lifespan=_lifespan)

for _router in (
    auth_router,
    orgs_router,
    public.router,
    recon.router,
    bankrec.router,
    close.router,
    invoices.router,
    books.router,
    review.router,
    workqueue.router,
):
    app.include_router(_router)

_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "AUDITA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Production: serve the built React app from AUDITA_STATIC_DIR (see Dockerfile).
_static_dir = Path(os.environ.get("AUDITA_STATIC_DIR", ""))
SPA_ENABLED = _static_dir.is_dir() and (_static_dir / "index.html").is_file()
if SPA_ENABLED:
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")


@app.get("/", response_class=HTMLResponse)
async def index():
    if SPA_ENABLED:
        return FileResponse(_static_dir / "index.html")
    return HTMLResponse(
        "<h1>Audita API</h1><p>The web app is served separately in development "
        "(<code>cd frontend && bun run dev</code>).</p>"
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "spa": SPA_ENABLED}


if SPA_ENABLED:
    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/signup", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/app", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/app/{rest:path}", response_class=HTMLResponse, include_in_schema=False)
    async def spa_fallback(rest: str = ""):
        return FileResponse(_static_dir / "index.html")
