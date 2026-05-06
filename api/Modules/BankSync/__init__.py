"""BankSync module — fourth vertical slice in the strangler-fig migration.

Owns the Stripe Financial Connections integration: connected bank
accounts, synced transactions, operator + built-in categorization
rules. Read-side first (PR 14-15: list + filter), write-side later
(rule CRUD, manual categorization, daily-book post).

Layer rules (ADR):
    Controller → Service → Repository → Model
"""
