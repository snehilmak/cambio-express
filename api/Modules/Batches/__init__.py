"""Batches module — ACH batch read-side for the SPA.

The legacy Flask `/batches` route lists ACH batches per store
with sort + variance computation. This module exposes the same
data via `/api/v2/batches` so the SPA's batches page can
consume it. Write-side (create / edit / link transfers) stays
on Flask until subsequent PRs migrate it.
"""
