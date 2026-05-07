"""Store SQL helpers for the admin-settings endpoints."""
from sqlalchemy.orm import Session

from api.Modules.Admin.Models import Store


def find_store(db: Session, store_id: int) -> Store | None:
    return db.query(Store).filter_by(id=store_id).first()
