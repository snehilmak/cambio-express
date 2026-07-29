// Best-effort US timezone detection from a free-form address string.
//
// These are brick-and-mortar stores, so the store's address is a good
// proxy for its timezone. Reliable geocoding needs an external service,
// so instead we parse the US **state** out of the address and map it to
// the state's predominant IANA timezone — good enough for a *suggestion*
// the operator confirms (see Settings → General "Detect from address").
//
// Deliberately conservative: we only match a state code that sits right
// before a 5-digit ZIP ("Austin, TX 78701") or a spelled-out state name.
// We do NOT match a bare two-letter token, because "OR"/"IN"/"OK" etc.
// collide with common words and would mis-detect. No match → null, and
// the UI leaves the dropdown untouched.
//
// Multi-zone states (TX, FL, …) resolve to their predominant zone; the
// operator can still change it. All returned values are members of
// `TIMEZONE_CHOICES` (api/Core/Clock.py) so they're valid dropdown
// options.

const STATE_TO_TZ: Record<string, string> = {
  // Eastern
  CT: "America/New_York", DE: "America/New_York", FL: "America/New_York",
  GA: "America/New_York", ME: "America/New_York", MD: "America/New_York",
  MA: "America/New_York", NH: "America/New_York", NJ: "America/New_York",
  NY: "America/New_York", NC: "America/New_York", OH: "America/New_York",
  PA: "America/New_York", RI: "America/New_York", SC: "America/New_York",
  VT: "America/New_York", VA: "America/New_York", WV: "America/New_York",
  DC: "America/New_York", IN: "America/New_York", MI: "America/New_York",
  KY: "America/New_York",
  // Central
  AL: "America/Chicago", AR: "America/Chicago", IL: "America/Chicago",
  IA: "America/Chicago", KS: "America/Chicago", LA: "America/Chicago",
  MN: "America/Chicago", MS: "America/Chicago", MO: "America/Chicago",
  NE: "America/Chicago", ND: "America/Chicago", OK: "America/Chicago",
  SD: "America/Chicago", TN: "America/Chicago", TX: "America/Chicago",
  WI: "America/Chicago",
  // Mountain
  CO: "America/Denver", ID: "America/Denver", MT: "America/Denver",
  NM: "America/Denver", UT: "America/Denver", WY: "America/Denver",
  // Arizona keeps its own zone (no DST)
  AZ: "America/Phoenix",
  // Pacific
  CA: "America/Los_Angeles", NV: "America/Los_Angeles",
  OR: "America/Los_Angeles", WA: "America/Los_Angeles",
  // Non-contiguous
  AK: "America/Anchorage", HI: "Pacific/Honolulu",
};

// Spelled-out state names → code (for addresses without the ST-ZIP form).
const NAME_TO_CODE: Record<string, string> = {
  alabama: "AL", alaska: "AK", arizona: "AZ", arkansas: "AR",
  california: "CA", colorado: "CO", connecticut: "CT", delaware: "DE",
  florida: "FL", georgia: "GA", hawaii: "HI", idaho: "ID", illinois: "IL",
  indiana: "IN", iowa: "IA", kansas: "KS", kentucky: "KY", louisiana: "LA",
  maine: "ME", maryland: "MD", massachusetts: "MA", michigan: "MI",
  minnesota: "MN", mississippi: "MS", missouri: "MO", montana: "MT",
  nebraska: "NE", nevada: "NV", "new hampshire": "NH", "new jersey": "NJ",
  "new mexico": "NM", "new york": "NY", "north carolina": "NC",
  "north dakota": "ND", ohio: "OH", oklahoma: "OK", oregon: "OR",
  pennsylvania: "PA", "rhode island": "RI", "south carolina": "SC",
  "south dakota": "SD", tennessee: "TN", texas: "TX", utah: "UT",
  vermont: "VT", virginia: "VA", washington: "WA", "west virginia": "WV",
  wisconsin: "WI", wyoming: "WY", "district of columbia": "DC",
};

/** State code parsed from a free-form US address, or null. */
export function usStateFromAddress(address: string): string | null {
  if (!address) return null;
  const text = address.trim();

  // 1. Strongest signal: a 2-letter state code immediately before a
  //    5-digit ZIP, e.g. "Austin, TX 78701" / "austin tx 78701-1234".
  const zipMatch = text.match(/\b([A-Za-z]{2})\s+\d{5}(?:-\d{4})?\b/);
  if (zipMatch) {
    const code = zipMatch[1].toUpperCase();
    if (code in STATE_TO_TZ) return code;
  }

  // 2. Fallback: a spelled-out state name anywhere in the address.
  const lower = text.toLowerCase();
  // Check longer (multi-word) names first so "new york" wins over a
  // stray "york", and "west virginia" over "virginia".
  const names = Object.keys(NAME_TO_CODE).sort((a, b) => b.length - a.length);
  for (const name of names) {
    if (new RegExp(`\\b${name}\\b`).test(lower)) return NAME_TO_CODE[name];
  }

  return null;
}

/** Best-effort IANA timezone for a free-form US address, or null when
 *  no state can be confidently parsed. */
export function timezoneFromAddress(address: string): string | null {
  const code = usStateFromAddress(address);
  return code ? (STATE_TO_TZ[code] ?? null) : null;
}
