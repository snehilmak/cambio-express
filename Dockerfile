# Portable production image (HANDOFF.md §2: stay on Render for now,
# but keep the app deployable anywhere — the move triggers are infra
# bill > ~$1k/mo, VPC/PCI needs, or multi-region).
#
# Render itself does NOT use this file (its native Python runtime
# runs scripts/build.sh); this is the escape hatch that makes a
# future migration a week instead of a quarter, and doubles as a
# way to run the full prod topology locally:
#
#   docker build -t dinerobook .
#   docker compose up -d                # local Postgres
#   docker run --rm -p 5000:5000 \
#     -e DATABASE_URL=postgresql://dinerobook:dinerobook@host.docker.internal:5432/dinerobook \
#     dinerobook
#
# Two stages: Node builds the SPA bundle, Python runs the ASGI app
# serving it (api/spa.py reads frontend/dist).

# ── Stage 1: frontend bundle ───────────────────────────────
# Node major pinned in lockstep with frontend/package.json engines
# + scripts/build.sh NODE_VERSION.
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: ASGI app ──────────────────────────────────────
# Python minor pinned in lockstep with runtime.txt.
FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /srv/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /build/frontend/dist ./frontend/dist

# Non-root runtime user — the app needs no filesystem writes
# outside of /tmp (SQLite dev DBs don't apply in a container;
# DATABASE_URL must point at Postgres).
RUN useradd --create-home appuser && chown -R appuser /srv/app
USER appuser

EXPOSE 5000
# Mirrors render.yaml's startCommand. init_db() runs `alembic
# upgrade head` on boot, so no separate migrate step is needed —
# same contract as the Render deploy.
CMD ["gunicorn", "asgi:asgi_app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120"]
