// Thin Promise wrapper around ``navigator.geolocation``. Surfaces
// a typed error when the API is unavailable or the user denies
// the permission prompt — both cases the time-clock punch flow
// needs to differentiate from a successful read.

export class GeolocationDeniedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GeolocationDeniedError";
  }
}

export class GeolocationUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GeolocationUnavailableError";
  }
}

export interface Coordinates {
  lat: number;
  lng: number;
  /** Accuracy in meters reported by the device. Useful for
   *  surfacing "your GPS reading is ±20m" hints in admin UI. */
  accuracy: number;
}


/** Resolve to the current browser-reported coordinates. Times
 *  out after ``timeoutMs`` (default 10 s) — slow IP-based
 *  geolocation otherwise blocks the punch UI indefinitely. */
export function getCurrentCoordinates(
  timeoutMs = 10_000,
): Promise<Coordinates> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new GeolocationUnavailableError(
        "This browser does not expose the geolocation API.",
      ));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          lat:      pos.coords.latitude,
          lng:      pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        });
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          reject(new GeolocationDeniedError(
            "Location permission denied. Allow the browser's "
            + "location prompt and try again — required when the "
            + "store has the geofence gate on.",
          ));
        } else {
          reject(new GeolocationUnavailableError(
            err.message || "Could not read the current location.",
          ));
        }
      },
      {
        enableHighAccuracy: true,
        maximumAge:         60_000,   // 1 min cache OK for punches
        timeout:            timeoutMs,
      },
    );
  });
}
