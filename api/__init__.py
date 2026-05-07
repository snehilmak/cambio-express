"""DineroBook FastAPI backend (in-progress migration).

Per `docs/architecture/MIGRATION_ADR.md`, this package is the new
home for the modular, multi-layer FastAPI backend that's gradually
strangling the Flask monolith in `app.py`. Modules are migrated one
at a time; both apps run side-by-side in the same repo until the
final cleanup PR.

Why `api/` and not `app/` (as the ADR §2 originally specified):
A top-level `app/` package collides with the existing `app.py` file
(the Flask monolith) because Python's import machinery prefers
packages over single-file modules with the same name. Renaming to
`api/` avoids the collision AND matches the FastAPI mount path
(`/api/v2/...`). The ADR was updated to reflect the actual layout.

Structure:
    api/
      Core/         # Config, Database, Providers (cross-cutting)
      Modules/      # one folder per bounded context
      main.py       # FastAPI app factory, mounts module routers

The legacy Flask code lives in `app.py` (the file at repo root),
not in this package. Don't confuse the two.
"""
