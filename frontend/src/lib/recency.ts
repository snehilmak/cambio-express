// localStorage-backed recency tracker for the "Most Used" strip
// on /app/home.  Records one entry per nav-eligible visit; the
// hub reads back the top N by visit count (recency breaks ties).
//
// Storage: ``dinerobook.nav_recency.v1`` → JSON map
//   { "<path>": { count: number, lastAt: number } }
//
// We cap the map to MAX_TRACKED entries to bound localStorage
// growth; the oldest entries get evicted when the cap is hit so
// long-tail one-off routes never crowd out repeat visits.
//
// Per-device only — nothing here syncs to the server. If a user
// signs in on a new browser the strip starts empty until they
// click around a few times.

const STORAGE_KEY = "dinerobook.nav_recency.v1";
const MAX_TRACKED  = 40;

export interface RecencyEntry {
  path: string;
  count: number;
  lastAt: number;
}

type RecencyMap = Record<string, { count: number; lastAt: number }>;

function load(): RecencyMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") return parsed as RecencyMap;
  } catch {
    // Corrupt JSON — start fresh.
  }
  return {};
}

function save(map: RecencyMap): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // Storage full / disabled (Safari private mode) — silently skip.
  }
}

/** Bump the visit counter for ``path``.  Caller is responsible for
 *  passing only routes that should appear in the strip (filter out
 *  Home itself, sub-pages like /transfers/123, etc.). */
export function recordVisit(path: string): void {
  if (!path) return;
  const map = load();
  const prev = map[path];
  map[path] = {
    count:  (prev?.count ?? 0) + 1,
    lastAt: Date.now(),
  };
  evictIfFull(map);
  save(map);
}

/** Return the top ``limit`` entries sorted by visit count, with
 *  most-recent breaking ties.  Drops any entry whose path is not
 *  in ``eligiblePaths`` — that's the role filter applied at the
 *  call site so a demoted user doesn't see admin routes in their
 *  strip. */
export function topVisited(
  eligiblePaths: ReadonlySet<string>,
  limit: number,
): RecencyEntry[] {
  const map = load();
  return Object.entries(map)
    .filter(([path]) => eligiblePaths.has(path))
    .map(([path, e]) => ({ path, count: e.count, lastAt: e.lastAt }))
    .sort((a, b) => b.count - a.count || b.lastAt - a.lastAt)
    .slice(0, limit);
}

/** Wipe every recorded visit.  Called from sign-out so a shared
 *  device doesn't leak a coworker's habits to the next user. */
export function clearVisits(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Same private-mode story — silently skip.
  }
}

function evictIfFull(map: RecencyMap): void {
  const keys = Object.keys(map);
  if (keys.length <= MAX_TRACKED) return;
  // Sort ascending by lastAt and drop the oldest until we're back
  // under the cap. O(n log n) but n is at most ~40 — fine.
  keys
    .sort((a, b) => map[a].lastAt - map[b].lastAt)
    .slice(0, keys.length - MAX_TRACKED)
    .forEach((k) => { delete map[k]; });
}
