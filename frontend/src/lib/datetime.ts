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


/** One entry of the ``Store.store_hours`` array (mirrors the
 *  backend ``StoreHourEntry`` Pydantic shape). */
export interface StoreHourLike {
  day:    number;
  open:   string;
  close:  string;
  closed: boolean;
}


/** Status returned by ``getOpenStatus`` — drives the UI pill on
 *  Dashboard + the soft warning on the New Transfer form. */
export interface OpenStatus {
  /** True when the current moment (in the resolved timezone) is
   *  inside the day's open window; false when the day is
   *  ``closed`` or before / after the window. */
  open: boolean;
  /** ``"09:00 - 18:00"`` style label for the current day —
   *  empty string when the store is closed today. */
  todayLabel: string;
  /** Day-of-week label for the row we looked at (``"Monday"``
   *  etc.) — useful for the pill tooltip. */
  dayLabel: string;
}


const DAY_NAMES = [
  "Monday", "Tuesday", "Wednesday", "Thursday",
  "Friday", "Saturday", "Sunday",
] as const;

/** Resolve whether the store is open right now per its 7-day
 *  schedule, evaluated in the store's local timezone. Returns
 *  null when ``hours`` is missing / malformed — callers should
 *  treat that as "no opinion, don't show an indicator". */
export function getOpenStatus(
  hours: StoreHourLike[] | null | undefined,
  storeTimezone?: string | null,
  now: Date = new Date(),
): OpenStatus | null {
  if (!Array.isArray(hours) || hours.length !== 7) return null;
  const tz = (storeTimezone || "").trim() || undefined;
  // Parse the wall-clock weekday + minute-of-day in the target tz.
  // ``Intl.DateTimeFormat`` with a single ``weekday`` part returns
  // English long names; we map back to the ISO 0..6 we store.
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, weekday: "long",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(now);
  const partMap: Record<string, string> = {};
  for (const p of parts) partMap[p.type] = p.value;
  const weekdayIdx = DAY_NAMES.indexOf(
    partMap.weekday as typeof DAY_NAMES[number],
  );
  if (weekdayIdx < 0) return null;
  const hh = Number(partMap.hour);
  const mm = Number(partMap.minute);
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return null;
  const row = hours.find((h) => h.day === weekdayIdx);
  if (!row) return null;
  const dayLabel = DAY_NAMES[weekdayIdx];
  if (row.closed) {
    return { open: false, todayLabel: "", dayLabel };
  }
  const openMin  = _toMinutes(row.open);
  const closeMin = _toMinutes(row.close);
  if (openMin == null || closeMin == null) {
    return null;
  }
  const nowMin = hh * 60 + mm;
  return {
    open: nowMin >= openMin && nowMin < closeMin,
    todayLabel: `${row.open} - ${row.close}`,
    dayLabel,
  };
}

function _toMinutes(value: string): number | null {
  if (typeof value !== "string") return null;
  const m = /^([0-2]\d):([0-5]\d)$/.exec(value);
  if (!m) return null;
  const hh = Number(m[1]);
  if (hh > 23) return null;
  return hh * 60 + Number(m[2]);
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
