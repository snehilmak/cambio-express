"""Audit module — append-only logs of admin / operator actions.

Owns three tables:
  - ``SuperadminAuditLog`` — platform-admin actions.
  - ``OperatorAuditLog``   — store-side actions (transfers,
                              daily reports, batches, etc.).
  - ``TransferAudit``      — per-Transfer change history,
                              FK-tied so it cascades on delete.
"""
