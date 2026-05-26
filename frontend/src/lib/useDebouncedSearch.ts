import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Debounced search synced to URL search params. Handles the
 * standard CLAUDE.md "Table search UX" pattern:
 * - 300ms debounce on the text input
 * - 2-char minimum before firing
 * - URL updated via history.replaceState so the filter is shareable
 * - Focus stays in the input (swap region below)
 *
 * Returns [draft, setDraft, committed] where:
 * - draft: the current input value (controlled)
 * - setDraft: call on onChange
 * - committed: the debounced value synced to the URL
 */
export function useDebouncedSearch(
  paramKey: string = "q",
  delayMs: number = 300,
  minChars: number = 2,
): [string, (v: string) => void, string] {
  const [sp, setSP] = useSearchParams();
  const committed = sp.get(paramKey) ?? "";
  const [draft, setDraft] = useState(committed);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    clearTimeout(timer.current);
    if (draft.length > 0 && draft.length < minChars) return;
    timer.current = setTimeout(() => {
      const next = new URLSearchParams(sp);
      if (draft) next.set(paramKey, draft);
      else next.delete(paramKey);
      setSP(next, { replace: true });
    }, delayMs);
    return () => clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sp triggers loops; we only care about draft
  }, [draft]);

  return [draft, setDraft, committed];
}
