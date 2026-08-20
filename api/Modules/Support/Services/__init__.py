


# Platform-staff roles: full cross-store ticket access, "staff"
# chat bubbles, and the superadmin audit sink. ``support`` is the
# tickets-only platform role — it passes HERE and nowhere else
# (never ``_require_superadmin`` / ``resolve_superadmin_user``,
# never the Casbin superadmin bypass). Lives in Services so both
# the Support Controllers and the Notifications recipient query
# import one tuple instead of re-typing it.
PLATFORM_STAFF_ROLES = ("superadmin", "support")
