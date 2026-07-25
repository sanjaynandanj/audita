# ---- Stage 1: build the React frontend ----
FROM oven/bun:1 AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile || bun install
COPY frontend/ ./
RUN bun run build

# ---- Stage 2: Python backend serving API + built SPA ----
FROM python:3.12-slim AS runtime
WORKDIR /app

RUN useradd --create-home --uid 1001 audita
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir .

COPY --from=frontend /fe/dist ./static

ENV AUDITA_STATIC_DIR=/app/static \
    AUDITA_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data && chown -R audita:audita /data /app
USER audita
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
