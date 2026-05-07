"""Phone-country-code reference list for the customer + transfer
forms.

Ordered list of `(dial_code, country_label)` pairs surfaced in
the sender / recipient phone-country picker on the transfer +
customer forms. Ordering is intentionally by likelihood for a
US-based remittance storefront — the most common choices stay
on top so cashiers don't scroll for them.

Add new entries in the dial-code position that matches the
existing geographic grouping (LATAM clustered together, etc.)
rather than appending to the bottom.
"""


PHONE_COUNTRY_CODES: list[tuple[str, str]] = [
    ("+1",   "United States / Canada"),
    ("+52",  "Mexico"),
    ("+502", "Guatemala"),
    ("+503", "El Salvador"),
    ("+504", "Honduras"),
    ("+505", "Nicaragua"),
    ("+506", "Costa Rica"),
    ("+507", "Panama"),
    ("+509", "Haiti"),
    ("+57",  "Colombia"),
    ("+593", "Ecuador"),
    ("+51",  "Peru"),
    ("+58",  "Venezuela"),
    ("+54",  "Argentina"),
    ("+55",  "Brazil"),
    ("+56",  "Chile"),
    ("+91",  "India"),
    ("+92",  "Pakistan"),
    ("+63",  "Philippines"),
    ("+234", "Nigeria"),
    ("+254", "Kenya"),
    ("+233", "Ghana"),
]
