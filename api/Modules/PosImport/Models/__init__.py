"""PosImport — Models.

``PosMerchandiseMap`` is the operator's one-time mapping from the
POS's numeric merchandise (department) codes to the store's own
Department catalog. Gilbarco journals identify departments only
by number ("4", "1024"); what those numbers MEAN is site
configuration the operator owns — same product principle as the
catalogs themselves (HANDOFF.md §2). Commit refuses to book a day
while any code present in the data is unmapped, so the mapping
review is a hard gate, not a silent default.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base


class PosMerchandiseMap(Base):
    __tablename__ = "pos_merchandise_map"
    id                = Column(Integer, primary_key=True)
    store_id          = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    merchandise_code  = Column(String(20), nullable=False)
    department_id     = Column(
        Integer, ForeignKey("department.id"), nullable=False,
    )
    created_at        = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("store_id", "merchandise_code"),
    )

    department = relationship("Department")


__all__ = ["PosMerchandiseMap"]
