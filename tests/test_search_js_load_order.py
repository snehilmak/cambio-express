"""Regression test: search.js must load synchronously (no `defer`).

Pages like /return-checks and /owner/locations have inline `<script>`
blocks in `{% block scripts %}` that call `attachSearchDebounce(...)`
directly during parse. If search.js is loaded with `defer` it won't
have executed yet — the global is undefined and the inline IIFE
throws, leaving the rest of the page JS (modal bindings, row-action
click handlers) un-wired.

Symptom from the field: clicking the "+ Payment" button on
/return-checks did nothing because `bindRowActions()` never ran.

This test pins the load contract so a future "let's defer everything
for perf" sweep can't regress it without flipping a guarded test.
"""






# /return-checks page rendering moved to React. The legacy Jinja
# IIFE that bound the +Payment row action is gone; the SPA
# (frontend/src/routes/ReturnChecks.tsx) owns row interactions
# now. Test deleted — was pinning Jinja-specific markers.
