"""Audit module — append-only logs of admin/operator actions.

Re-exports the legacy `SuperadminAuditLog` and `OperatorAuditLog`
models during the strangler-fig migration window. Once the legacy
file is gone these will be defined here directly.
"""
