"""Transfers module.

Owns the per-store transfer ledger: list with filters/pagination,
get-by-id, create, edit, delete, batch operations. Full transfer-
form business logic — federal_tax calculation, fee handling,
customer upsert, audit-log emission — lives in the Service layer.

The Reports module also has a Transfers-aggregation repository at
``api.Modules.Reports.Repositories.transfers`` — that one composes
GROUP BY queries for the report cards. The Transfers module's
repository handles row-level CRUD + filtered list. Both coexist
because they answer different questions about the same table.

Layer rules (ADR):
    Controller → Service → Repository → Model
"""
