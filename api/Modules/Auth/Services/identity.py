"""Login identifiers — email and phone.

People sign in with an email address or a phone number. Usernames
are retired for NEW accounts (owner directive 2026-08-31); the ones
already in the database keep working forever so nobody — the seeded
superadmin included — is locked out by the change.

Both identifiers need a canonical form before they can be looked up,
because the string a person types is not the string we stored:
``Amber@Store.com`` must find ``amber@store.com``, and
``(555) 123-4567`` must find ``5551234567``. Normalising at both
write and read time is what makes that work; matching on the raw
input would fail on nothing more than a space.

Everything here is a pure string function — no DB, no policy. Who
may sign in is the login Service's business.
"""
import re


# Deliberately permissive: something@something.tld with no spaces.
# This is a *routing* check — "does this look like an email or a
# phone number?" — not a deliverability guarantee, which only
# sending mail can establish. Being strict here would reject valid
# addresses and lock people out of their own accounts.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# North-American numbers are 10 digits; 11 with the country code.
_NANP_LEN = 10
_NANP_WITH_COUNTRY = 11

# Shortest string of digits we'll treat as a phone number. Below
# this it's far more likely to be a legacy username that happens to
# be numeric, and we'd rather fall through to the username path than
# invent a phone match.
_MIN_PHONE_DIGITS = 7


def normalize_email(raw: str | None) -> str:
    """Canonical email: trimmed and lower-cased.

    Only the case and surrounding whitespace are touched. We do NOT
    strip dots or ``+tags`` from the local part — Gmail treats those
    as the same mailbox but most providers do not, and collapsing
    them would let one person's address match another's account.
    """
    return (raw or "").strip().lower()


def is_email(raw: str | None) -> bool:
    """True when `raw` looks like an email address."""
    return bool(_EMAIL_RE.match((raw or "").strip()))


def normalize_phone(raw: str | None) -> str:
    """Canonical phone: digits only, country code dropped for
    North-American numbers.

    ``(555) 123-4567``, ``555-123-4567``, ``+1 555 123 4567`` and
    ``15551234567`` all normalise to ``5551234567``, so the number
    someone types finds the account however it was entered.

    Non-NANP numbers keep every digit, including the country code —
    we can't tell a country code from a subscriber digit without a
    full phone library, and dropping the wrong leading digits would
    corrupt an international number. Returns ``""`` when there
    aren't enough digits to be a phone number at all.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < _MIN_PHONE_DIGITS:
        return ""
    if len(digits) == _NANP_WITH_COUNTRY and digits.startswith("1"):
        return digits[1:]
    return digits


def looks_like_phone(raw: str | None) -> bool:
    """True when `raw` normalises to a usable phone number."""
    return bool(normalize_phone(raw))


def login_identifier(email: str | None, phone: str | None) -> str:
    """The canonical identifier stored on ``User.username`` for a
    NEW account.

    Email wins when both are given: it's the channel password reset
    already runs on. Phone is the fallback for staff who have no
    email address — common for cashiers.

    The ``username`` column is not going away. It still carries the
    per-store uniqueness constraint that stops one store issuing two
    logins for the same person, and dropping a live column without a
    dual-write window is exactly what CLAUDE.md forbids. It simply
    stops being something a human types or sees.

    Returns ``""`` when neither identifier is usable; the caller
    turns that into a validation error.
    """
    normalized_email = normalize_email(email)
    if normalized_email and is_email(normalized_email):
        return normalized_email
    return normalize_phone(phone)
