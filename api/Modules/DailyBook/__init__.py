"""DailyBook module.

Owns the per-store daily cash-ledger: DailyReport (one row per
date) plus its DailyLineItem rows (drops, deposits, expenses).

Layer rules (ADR):
    Controller → Service → Repository → Model
"""
