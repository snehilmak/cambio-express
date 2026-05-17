// Date / time rendering helpers.
//
// Single source of truth for "what timezone do we render in?"
// across the SPA. The fallback chain (per BACKLOG "Store
// timezone") is:
//
//   user.timezone → store.timezone → browser default
//
// Both upstream sources are optional (an admin who hasn't set
// either falls through to whatever `toLocaleString` picks). We
// resolve once per render — pass an explicit ``timezone`` if the
// caller already knows it; otherwise the helper picks the best
// available.

const _MONTH_LONG_FMT = (timezone?: string) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone || undefined,
  });

const _DATE_ONLY_FMT = (timezone?: string) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: timezone || undefined,
  });


/** Resolve the active timezone. Empty / undefined values fall
 *  through to the next layer. ``undefined`` return means
 *  "use the browser default" (Intl skips ``timeZone`` then). */
export function resolveTimezone(
  userTimezone?: string | null,
  storeTimezone?: string | null,
): string | undefined {
  const u = (userTimezone || "").trim();
  if (u) return u;
  const s = (storeTimezone || "").trim();
  if (s) return s;
  return undefined;
}


/** Format a UTC ISO-8601 timestamp ("2026-05-09T17:42:00Z") for
 *  display. Includes a TZ suffix so the reader can tell where
 *  the displayed time is grounded.
 *
 *  ``May 09, 2026 17:42 CST``   (when timezone resolves to America/Chicago)
 *  ``May 09, 2026 17:42 UTC``   (fallback when nothing is set)
 *  ``"—"``                      (empty / unparseable input)
 */
export function formatTimestamp(
  iso: string | null | undefined,
  opts: {
    userTimezone?: string | null;
    storeTimezone?: string | null;
  } = {},
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const tz = resolveTimezone(opts.userTimezone, opts.storeTimezone);
  const base = _MONTH_LONG_FMT(tz).format(d);
  const tzLabel = formatTzAbbrev(d, tz);
  return tzLabel ? `${base} ${tzLabel}` : base;
}


/** Date-only formatter — for column cells where the time of day
 *  doesn't matter and would just clutter the view. */
export function formatDate(
  iso: string | null | undefined,
  opts: {
    userTimezone?: string | null;
    storeTimezone?: string | null;
  } = {},
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const tz = resolveTimezone(opts.userTimezone, opts.storeTimezone);
  return _DATE_ONLY_FMT(tz).format(d);
}


/** Pull a short timezone abbreviation ("CST", "PST", "UTC") from
 *  an Intl format pass. Falls back to "UTC" when no timezone is
 *  passed (matches the default rendering before the helper). */
function formatTzAbbrev(d: Date, tz?: string): string {
  if (!tz) return "UTC";
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      timeZoneName: "short",
    }).formatToParts(d);
    const part = parts.find((p) => p.type === "timeZoneName");
    return part ? part.value : "";
  } catch {
    // Bad TZ string — silently degrade rather than crashing the
    // render. The user can fix the value in settings.
    return "";
  }
}
