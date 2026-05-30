/**
 * useUrlFilterState — list/search page state synced to URL params.
 *
 * Standardises the pattern shared across Transfers, AdminAuditLog,
 * OwnerActivity, and any future list page:
 *
 *   - `params` reflect the current URL (string values, easy to feed
 *     straight into API hooks)
 *   - `setParam(key, value)` updates the URL + resets `page` to 1
 *     (since changing a filter invalidates the current page)
 *   - `setPage(n)` keeps the rest of the URL intact
 *   - `debounced(key)` lets you wire a debounced search input
 *     without rebuilding the timer dance in every page
 *
 * Why URL state (not React state):
 *   - Refresh + back/forward restore the view
 *   - Shareable links reproduce the exact filter combination
 *   - One source of truth — no draft/applied dual state
 *
 * Why a hook (not raw useSearchParams):
 *   - Filters reset page automatically (this is wrong to forget)
 *   - Debounce is built in with the right race-condition handling
 *   - 2-char minimum on free-text inputs matches CLAUDE.md's
 *     "Table search UX" invariant
 *
 * Typical usage:
 *
 *     const filters = useUrlFilterState({
 *       q: "",
 *       status: "",
 *       date_from: "",
 *       date_to: "",
 *     });
 *
 *     const apiQuery = useThings({
 *       page: filters.page,
 *       q: filters.params.q,
 *       status: filters.params.status,
 *     });
 *
 *     <Input
 *       value={filters.draft.q ?? filters.params.q}
 *       onChange={(e) => filters.debounced("q", e.target.value)}
 *     />
 *
 *     <Select
 *       value={filters.params.status}
 *       onChange={(e) => filters.setParam("status", e.target.value)}
 *     />
 *
 *     <Pager page={filters.page} totalPages={apiQuery.data?.total_pages ?? 1}
 *            onPageChange={filters.setPage} />
 */
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

interface Options {
  /** Debounce window for `debounced()` updates. Defaults to 300ms. */
  debounceMs?: number;
  /** Minimum input length before a debounced update writes to URL.
   *  Strings shorter than this still clear (length 0). Defaults to 2,
   *  matching the CLAUDE.md table-search-UX invariant. */
  minLength?: number;
}

export interface UrlFilterState<TKeys extends string> {
  /** Current URL param values (one per key, empty string when unset). */
  params: Record<TKeys, string>;
  /** Local draft mirror for debounced inputs. `undefined` for keys
   *  that haven't been edited since the URL last changed. */
  draft: Partial<Record<TKeys, string>>;
  /** Current page (1-based). */
  page: number;
  /** Update a single filter immediately. Resets `page` to 1. */
  setParam: (key: TKeys, value: string) => void;
  /** Update a free-text filter via debounce. Resets `page` to 1
   *  once the debounce fires. Keeps `draft[key]` populated so the
   *  input renders the in-flight value. */
  debounced: (key: TKeys, value: string) => void;
  /** Jump to a specific page. Other filters untouched. */
  setPage: (next: number) => void;
  /** Clear every filter (and reset page). */
  reset: () => void;
}

export function useUrlFilterState<TKeys extends string>(
  defaults: Record<TKeys, string>,
  options: Options = {},
): UrlFilterState<TKeys> {
  const { debounceMs = 300, minLength = 2 } = options;
  const [sp, setSP] = useSearchParams();
  const keys = Object.keys(defaults) as TKeys[];

  const params = keys.reduce((acc, key) => {
    acc[key] = sp.get(key) ?? defaults[key];
    return acc;
  }, {} as Record<TKeys, string>);
  const page = Number(sp.get("page") ?? 1) || 1;

  const [draft, setDraft] = useState<Partial<Record<TKeys, string>>>({});
  const debounceRefs = useRef<Record<string, ReturnType<typeof setTimeout> | null>>({});

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clear local drafts whenever the URL changes externally (browser back, link arrival)
    setDraft({});
  }, [sp]);

  function setParam(key: TKeys, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== ("page" as TKeys)) next.delete("page");
    setSP(next, { replace: true });
  }

  function debounced(key: TKeys, value: string) {
    setDraft((d) => ({ ...d, [key]: value }));
    if (debounceRefs.current[key as string]) {
      clearTimeout(debounceRefs.current[key as string] as ReturnType<typeof setTimeout>);
    }
    debounceRefs.current[key as string] = setTimeout(() => {
      const writeValue = value.length === 0 || value.length >= minLength ? value : "";
      const next = new URLSearchParams(sp);
      if (writeValue) next.set(key, writeValue);
      else next.delete(key);
      next.delete("page");
      setSP(next, { replace: true });
    }, debounceMs);
  }

  function setPage(next: number) {
    const np = new URLSearchParams(sp);
    np.set("page", String(next));
    setSP(np, { replace: true });
  }

  function reset() {
    const np = new URLSearchParams();
    setSP(np, { replace: true });
    setDraft({});
  }

  return { params, draft, page, setParam, debounced, setPage, reset };
}
