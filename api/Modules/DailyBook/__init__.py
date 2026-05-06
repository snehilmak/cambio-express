"""DailyBook module — sixth and final vertical slice in the
strangler-fig migration.

Owns the per-store daily cash-ledger: DailyReport (one row per
date) plus its DailyLineItem rows (drops, deposits, expenses).
PR 21 ships Models + Repositories; PR 22+ adds Services and the
Flask flip.

Layer rules (ADR):
    Controller → Service → Repository → Model
"""
