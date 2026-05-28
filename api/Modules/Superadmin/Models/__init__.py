"""Superadmin — Models.

PlatformSetting stores global key-value configuration (maintenance
mode, platform-wide banners, etc.) that superadmin can toggle
without a code deploy.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from api.Core.Database import Base
from api.Core.Clock import utc_now


class PlatformSetting(Base):
    """Key-value store for platform-wide superadmin configuration.

    Rows are upserted by key — each key has exactly one row.
    The value column is free-form text (JSON for complex values,
    plain string for simple flags).
    """
    __tablename__ = "platform_setting"
    id        = Column(Integer, primary_key=True)
    key       = Column(String(60), unique=True, nullable=False, index=True)
    value     = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_setting(db, key: str, default: str = "") -> str:
    row = db.query(PlatformSetting).filter_by(key=key).first()
    return row.value if row else default


def set_setting(db, key: str, value: str) -> None:
    row = db.query(PlatformSetting).filter_by(key=key).first()
    if row:
        row.value = value
        row.updated_at = utc_now()
    else:
        db.add(PlatformSetting(key=key, value=value))
    db.commit()
