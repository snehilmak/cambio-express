


from sqlalchemy import func, or_
from sqlalchemy.orm import Session


# Platform-staff roles: full cross-store ticket access, "staff"
# chat bubbles, and the superadmin audit sink. ``support`` is the
# tickets-only platform role — it passes HERE and nowhere else
# (never ``_require_superadmin`` / ``resolve_superadmin_user``,
# never the Casbin superadmin bypass). Lives in Services so both
# the Support Controllers and the Notifications recipient query
# import one tuple instead of re-typing it.
PLATFORM_STAFF_ROLES = ("superadmin", "support")


def unread_message_counts(
    db: Session, ticket_ids: list[int], viewer_kind: str,
) -> dict[int, int]:
    """Unread replies per ticket for one conversation side.

    ``viewer_kind`` is ``"user"`` (store side — counts staff
    messages newer than ``user_last_seen_at``) or ``"staff"``
    (platform side — counts user messages newer than
    ``staff_last_seen_at``). A NULL last-seen means the side has
    never opened the thread, so every opposite-side message is
    unread. Tickets with zero unread are omitted from the dict.
    """
    from api.Modules.Support.Models import SupportMessage, SupportTicket

    if not ticket_ids:
        return {}
    other_kind = "staff" if viewer_kind == "user" else "user"
    seen_col = (
        SupportTicket.user_last_seen_at
        if viewer_kind == "user"
        else SupportTicket.staff_last_seen_at
    )
    rows = (
        db.query(SupportMessage.ticket_id, func.count(SupportMessage.id))
          .join(SupportTicket, SupportTicket.id == SupportMessage.ticket_id)
          .filter(
              SupportMessage.ticket_id.in_(ticket_ids),
              SupportMessage.author_kind == other_kind,
              or_(seen_col.is_(None), SupportMessage.created_at > seen_col),
          )
          .group_by(SupportMessage.ticket_id)
          .all()
    )
    return {int(tid): int(n) for tid, n in rows}


def unread_total(
    db: Session, viewer_kind: str, store_id: int | None = None,
) -> int:
    """Total unread replies for the nav badge — same semantics as
    ``unread_message_counts`` summed across the tickets the viewer
    can see (one store for the store side, everything for staff)."""
    from api.Modules.Support.Models import SupportMessage, SupportTicket

    other_kind = "staff" if viewer_kind == "user" else "user"
    seen_col = (
        SupportTicket.user_last_seen_at
        if viewer_kind == "user"
        else SupportTicket.staff_last_seen_at
    )
    q = (
        db.query(func.count(SupportMessage.id))
          .join(SupportTicket, SupportTicket.id == SupportMessage.ticket_id)
          .filter(
              SupportMessage.author_kind == other_kind,
              or_(seen_col.is_(None), SupportMessage.created_at > seen_col),
          )
    )
    if store_id is not None:
        q = q.filter(SupportTicket.store_id == store_id)
    return int(q.scalar() or 0)
