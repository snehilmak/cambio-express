"""ReturnChecks module — bounced customer checks workflow.

The legacy /return-checks Jinja routes manage the full
workflow (list, create, edit, mark recovered/loss/fraud, reopen,
record payments). This module exposes the read-side + status
transitions so the SPA can replace the daily admin flow.
Per-payment CRUD ships in a follow-up PR.
"""
