"""Pydantic-based settings.

Single `Settings` instance loaded once at import. Reads from
environment variables (or a `.env` if present) so the same code
path works for dev, test, and prod.

Usage:
    from api.Core.Config import settings
    settings.database_url
"""
from .settings import Settings, get_settings, settings

__all__ = ["Settings", "get_settings", "settings"]
