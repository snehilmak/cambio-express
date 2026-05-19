"""Geofence check for time-clock punches.

Pairs with the passkey gate (``timeclock_require_passkey``) as
the second leg of the anti-buddy-punching defense:

  passkey  → proves "this is the right person"
  geofence → proves "they're physically at the store"

The store admin pins a lat/lng + radius once (Settings → Store),
then flips ``Store.timeclock_require_geofence`` to True. Every
clock-in / clock-out request after that needs ``geo_lat`` +
``geo_lng`` in the body; the server checks distance via the
haversine formula and refuses outside the radius.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any


# Earth's mean radius in meters. Good enough for store-radius
# checks — sub-meter precision isn't relevant when the typical
# radius is ~100m.
_EARTH_RADIUS_M = 6_371_000.0


class GeofenceNotConfiguredError(ValueError):
    """Raised when the store has ``timeclock_require_geofence``
    on but no lat/lng has been pinned yet — the admin needs to
    finish the Settings page first."""


class GeofenceMissingCoordsError(ValueError):
    """Raised when the punch endpoint requires a geofence
    check but the body didn't include ``geo_lat`` / ``geo_lng``.
    The SPA reads these from ``navigator.geolocation``; a
    request without them means the cashier denied the browser
    permission prompt (or the device has no GPS)."""


class GeofenceOutOfRangeError(ValueError):
    """Raised when the cashier's coordinates fall outside the
    store's configured radius."""

    def __init__(self, message: str, *, distance_m: int) -> None:
        super().__init__(message)
        self.distance_m = distance_m


def haversine_meters(
    lat_a: float, lng_a: float, lat_b: float, lng_b: float,
) -> float:
    """Great-circle distance between two lat/lng points, in
    meters. Standard haversine — accurate to ~0.5% even at
    antipodes, which is overkill for a 100m store radius."""
    lat_a_r, lng_a_r = radians(lat_a), radians(lng_a)
    lat_b_r, lng_b_r = radians(lat_b), radians(lng_b)
    d_lat = lat_b_r - lat_a_r
    d_lng = lng_b_r - lng_a_r
    a = (sin(d_lat / 2) ** 2
         + cos(lat_a_r) * cos(lat_b_r) * sin(d_lng / 2) ** 2)
    c = 2 * asin(min(1.0, sqrt(a)))
    return _EARTH_RADIUS_M * c


def verify_punch_location(
    store: Any, *, geo_lat: float | None, geo_lng: float | None,
) -> None:
    """Raise the appropriate error when the punch can't proceed.

    No-op when the store doesn't have the gate turned on. The
    caller (controller) is expected to surface the resulting
    errors as 401 / 422 with helpful detail text.
    """
    if not getattr(store, "timeclock_require_geofence", False):
        return
    center_lat = store.timeclock_geofence_lat
    center_lng = store.timeclock_geofence_lng
    if center_lat is None or center_lng is None:
        raise GeofenceNotConfiguredError(
            "This store requires a geofenced punch, but the admin "
            "hasn't pinned the store location yet. Open Settings → "
            "Store and tap 'Use current location' first.",
        )
    if geo_lat is None or geo_lng is None:
        raise GeofenceMissingCoordsError(
            "This store requires a geofenced punch — allow the "
            "browser's location prompt before clocking in.",
        )
    radius_m = int(store.timeclock_geofence_radius_m or 100)
    distance = haversine_meters(center_lat, center_lng, geo_lat, geo_lng)
    if distance > radius_m:
        raise GeofenceOutOfRangeError(
            f"Punch refused — you're {int(distance)} m away from the "
            f"store (allowed: {radius_m} m). Try again from inside the "
            "store, or ask an admin to widen the geofence radius.",
            distance_m=int(distance),
        )
