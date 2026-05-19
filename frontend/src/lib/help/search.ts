// Token-overlap fuzzy search over the help registry.  Skipping
// Fuse.js to avoid a runtime dep — the registry is tiny (~25
// entries), so a 30-line scoring function is faster and ships
// fewer KB to the client.
//
// Algorithm:
//   1. Lowercase + word-split the query into tokens.
//   2. For each entry, compute:
//        a. token-overlap score (how many query tokens appear
//           as a substring of the entry's `keywords` blob)
//        b. exact-substring boost when the whole query appears
//           in the entry's title or keywords (rewards "what is
//           over short" matching "what does over/short mean")
//   3. Sort by score desc; return entries above a threshold.
//
// No threshold tuning is needed for the first cut — surface
// every entry that has at least one matching token.  The empty
// query returns the top N by an authored ``weight`` so the
// initial panel always has something useful to read.

import type { HelpEntry } from "./registry";


function tokenize(s: string): string[] {
  return s
    .toLowerCase()
    .split(/[\s/,.?!:;()]+/)
    .filter((t) => t.length > 0);
}


/** Score one entry against a (already-lowercased) query.  Higher
 *  is better; 0 = no signal. */
function scoreEntry(entry: HelpEntry, lowerQuery: string, tokens: string[]): number {
  if (lowerQuery === "") {
    // Empty query → fall back to the authored weight so we still
    // render something useful when the panel opens.
    return entry.weight ?? 1;
  }
  const blob = `${entry.title} ${entry.keywords}`.toLowerCase();
  // Whole-query substring is the strongest signal: "what does
  // over short mean" hitting the entry titled "Over/short".
  let score = 0;
  if (blob.includes(lowerQuery)) score += 5;
  // Per-token substring match.  Each contributes a smaller
  // increment so the full-phrase bonus stays dominant.
  for (const t of tokens) {
    if (t.length < 2) continue;
    if (blob.includes(t)) score += 1;
  }
  return score;
}


/** Run the search.  Returns the entries with score > 0, sorted
 *  by score desc, capped at ``limit``.  An empty query returns
 *  the highest-weighted entries (so the panel is never blank). */
export function searchHelp(
  query: string,
  entries: readonly HelpEntry[],
  limit = 6,
): HelpEntry[] {
  const lower = query.trim().toLowerCase();
  const tokens = tokenize(lower);
  const scored = entries
    .map((e) => ({ entry: e, score: scoreEntry(e, lower, tokens) }))
    .filter((s) => s.score > 0);
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((s) => s.entry);
}
