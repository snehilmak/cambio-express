"""Standalone CLI entrypoints.

Replaces the ``flask <command>`` invocations that depended on the
Flask CLI machinery booting all of ``app.py``. Each script in this
package is invoked via ``python -m scripts.<name>`` and pulls only
the modules it actually needs — Services + Models + observability
init — so the cron service startup is fast and Flask-free.

Render's cron service runs ``python -m scripts.purge_expired_stores``;
see ``render.yaml`` for the wiring.
"""
