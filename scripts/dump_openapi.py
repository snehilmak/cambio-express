"""Dump the FastAPI app's OpenAPI schema to JSON.

Used by ``frontend/`` to generate TypeScript types via
``openapi-typescript`` so the SPA's request/response shapes stay
in lockstep with the Pydantic models on the backend.

Run from the repo root::

    python -m scripts.dump_openapi > frontend/src/api/openapi.json

The standard workflow is ``npm run generate-types`` (in
``frontend/``), which chains this script with ``openapi-typescript``
to produce ``frontend/src/api/openapi.d.ts``.

The dump is deterministic — Pydantic emits keys in declaration
order — so the generated ``openapi.d.ts`` round-trips cleanly
under ``git diff`` and a CI check can fail on stale types.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    # Avoid the full DB init (Alembic upgrade + seed) — we only
    # need the route + schema metadata to serialize the OpenAPI
    # spec. ``api/main.py``'s lifespan honours this flag.
    os.environ["DINEROBOOK_SKIP_INIT_DB"] = "1"
    # Match the env vars the CI workflow's import smoke test sets;
    # without them the Pydantic settings loader rejects boot.
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("SECRET_KEY", "openapi-dump-key")
    os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dump")
    os.environ.setdefault("STRIPE_BASIC_PRICE_ID", "price_basic_dump")
    os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro_dump")
    os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dump")
    os.environ.setdefault("RATELIMIT_ENABLED", "0")

    from api.main import api_app

    spec = api_app.openapi()
    json.dump(spec, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
