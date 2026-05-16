"""DineroBook FastAPI backend.

Mounts at ``/api/v2/*`` via the top-level ``asgi.py`` ASGI
dispatcher. Flask was retired in PR #550; this package is the
sole backend.

Structure:
    api/
      Core/         # Config, Database, Providers (cross-cutting)
      Modules/      # one folder per bounded context
      main.py       # FastAPI app factory, mounts module routers
"""
