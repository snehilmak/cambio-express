"""Account profile Service.

Field-level validation for the personal-info form. Caller
commits — the Service flushes but doesn't commit so a multi-
field edit can roll back atomically on error.
"""
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.Core.Clock import TIMEZONE_CHOICES as _CANONICAL_TIMEZONES
from api.Modules.Auth.Models import User


# Mirrors app._EMAIL_RE / _PHONE_DIGITS_RE so the SPA's API does
# the same validation as the legacy form.
_EMAIL_RE        = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_DIGITS_RE = re.compile(r"^\+?\d{7,20}$")
_PHONE_STRIP_RE  = re.compile(r"[\s\-\(\)]")


# Profile dropdown options (list form for the API payload).
TIMEZONE_CHOICES: list[str] = list(_CANONICAL_TIMEZONES)


class ProfileValidationError(Exception):
    """Raised when one or more profile fields fail validation.
    Carries a `field_errors` dict keyed by field name so the
    Controller can pass them straight back to the SPA — same
    shape the legacy Jinja template renders inline."""

    def __init__(self, field_errors: dict[str, str]):
        super().__init__("Profile validation failed")
        self.field_errors = field_errors


# Allowed theme values — kept in sync with the Pydantic
# ``ThemePreference`` Literal in Requests/profile.py.
_THEME_CHOICES = ("dark", "light")


def normalize_theme(raw: str | None) -> str:
    """Coerce ``user.theme_preference`` to a safe value.

    Any unknown / empty value falls back to ``"dark"`` — that
    matches the design-system default and guarantees a styled
    page even if the DB row is partially migrated or hand-edited.
    """
    return raw if raw in _THEME_CHOICES else "dark"


def get_profile_payload(user: User) -> dict[str, Any]:
    """Pure read — no DB access beyond what's already on `user`.
    Returns the payload for the Profile React page."""
    return {
        "user_id":          user.id,
        "username":         user.username or "",
        "role":             user.role or "",
        "full_name":        user.full_name or "",
        "email":            user.email or "",
        "phone":            user.phone or "",
        "timezone":         user.timezone or "",
        "theme_preference": normalize_theme(
            str(user.theme_preference) if user.theme_preference else None,
        ),
        "created_at":       user.created_at.isoformat() if user.created_at else "",
        "last_login_at":    user.last_login_at.isoformat() if user.last_login_at else "",
        "timezone_choices": TIMEZONE_CHOICES,
    }


def update_profile(
    db: Session, user: User, *,
    full_name:        Optional[str] = None,
    email:            Optional[str] = None,
    phone:            Optional[str] = None,
    timezone:         Optional[str] = None,
    theme_preference: Optional[str] = None,
) -> None:
    """Validate + apply changes to `user`. Raises
    ProfileValidationError on bad input. Caller commits.

    Each field is set only when the caller passed it (None means
    'don't touch'). Empty string (after strip) explicitly clears
    the field — matches the existing behaviour where a user can
    blank out their phone or email."""
    errors: dict[str, str] = {}

    if full_name is not None:
        name = full_name.strip()
        if not name:
            errors["full_name"] = "Display name cannot be empty."
        elif len(name) > 120:
            errors["full_name"] = (
                "Display name is too long (max 120 characters)."
            )

    if email is not None:
        normalized_email = email.strip().lower()
        if normalized_email and not _EMAIL_RE.match(normalized_email):
            errors["email"] = "Enter a valid email address."
        elif len(normalized_email) > 255:
            errors["email"] = "Email is too long (max 255 characters)."

    if phone is not None:
        phone_clean = _PHONE_STRIP_RE.sub("", phone or "")
        if phone_clean and not _PHONE_DIGITS_RE.match(phone_clean):
            errors["phone"] = (
                "Enter a valid phone number "
                "(7–20 digits, optional leading +)."
            )

    if timezone is not None:
        tz = timezone.strip()
        if tz and tz not in TIMEZONE_CHOICES:
            errors["timezone"] = "Pick a timezone from the list."

    if theme_preference is not None and theme_preference not in _THEME_CHOICES:
        errors["theme_preference"] = (
            "Theme must be 'dark' or 'light'."
        )

    if errors:
        raise ProfileValidationError(errors)

    if full_name is not None:
        setattr(user, "full_name", full_name.strip())
    if email is not None:
        setattr(user, "email", email.strip().lower())
    if phone is not None:
        setattr(user, "phone", _PHONE_STRIP_RE.sub("", phone or ""))
    if timezone is not None:
        setattr(user, "timezone", timezone.strip())
    if theme_preference is not None:
        setattr(user, "theme_preference", theme_preference)
    db.flush()
