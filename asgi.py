"""ASGI entrypoint for production.

Gunicorn-with-UvicornWorker boots from this module:

    gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker

The shim does two things in order:

1. Imports `app.app` (the legacy Flask app). app.py's bottom block
   mounts the FastAPI sub-app at /api/v2 via DispatcherMiddleware
   + a2wsgi.ASGIMiddleware. After this import the Flask WSGI app
   is fully wired (Flask routes + /api/v2/* → FastAPI routes).
2. Wraps the resulting WSGI app in a2wsgi.WSGIMiddleware to expose
   it to the ASGI server.

The architecture during the migration window remains "Flask outer,
FastAPI mounted inside" — this shim doesn't invert it. What it
delivers is the ASGI server: gunicorn-with-UvicornWorker on every
incoming request, instead of plain gunicorn-WSGI. This is the
foundation Step 1 of Option C ("migrate everything to FastAPI,
retire Flask"). Subsequent PRs move legacy Flask routes to the
FastAPI sub-app one at a time, and at the end of that path Flask
disappears entirely — at which point this shim collapses to a
direct re-export of api.main:api_app.

Why route through the legacy Flask app rather than mount it inside
FastAPI directly: Reports.Models has a pre-existing circular import
(legacy hop `from app import Transfer, ...`) that breaks any
import path that tries to load `api.main` BEFORE app.py has
finished. gunicorn app:app and this shim both load app.py first,
so neither hits that path.
"""
from a2wsgi import WSGIMiddleware

from app import app as flask_app

# `flask_app.wsgi_app` is the post-init dispatcher chain: legacy
# Flask routes for everything except /api/v2/*, FastAPI for
# /api/v2/*. Wrapping it in WSGIMiddleware exposes the whole thing
# as a single ASGI app the UvicornWorker can serve.
asgi_app = WSGIMiddleware(flask_app.wsgi_app)
