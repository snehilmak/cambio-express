"""Transfers module — third vertical slice in the strangler-fig migration.

Owns the per-store transfer ledger: list with filters/pagination,
get-by-id, create, edit, delete, batch operations. The complete
transfer-form business logic (federal_tax calculation, fee handling,
customer upsert, audit log emission) will land in the Service layer
in PR 11+; this PR is just the Model + Repository scaffolding.

The Reports module already has a Transfers-aggregation repository at
`api.Modules.Reports.Repositories.transfers` — that one composes
GROUP BY queries for the report cards. The Transfers module's
repository handles row-level CRUD + filtered list. Both can coexist
because they answer different questions about the same table.

Layer rules (ADR):
    Controller → Service → Repository → Model
"""
