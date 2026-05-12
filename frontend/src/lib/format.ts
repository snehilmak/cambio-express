// PII formatting helpers — keep redaction rules in one place so
// every list view + report masks the same way and the audit
// surface for "what does over-the-shoulder reveal?" stays small.

const PHONE_DOT = "·"; // middle dot · — visually distinct from the comma we see in non-mono fonts

/** Mask all but the last 4 digits of a phone number. Preserves
 *  the trailing 4 + the original separator style so the result
 *  is recognisable but unusable for re-dialing.
 *
 *  Behavior:
 *    "555-555-1234"        → "·······1234"
 *    "(555) 555-1234"      → "··········1234"  (non-digit chars dropped, then masked)
 *    "1234"                → "1234"            (≤4 digits stays as-is)
 *    ""                    → "—"               (empty fallback)
 *
 *  Pair with `maskedPhoneWithCountry` when you also want to keep
 *  the country code visible — useful for cashier-facing tables
 *  where "+1 ··· 1234" still tells the reader "domestic number".
 */
export function maskPhone(raw: string | null | undefined): string {
  const s = (raw ?? "").trim();
  if (!s) return "—";
  const digits = s.replace(/\D+/g, "");
  if (digits.length <= 4) return digits || s;
  const last4 = digits.slice(-4);
  const hidden = PHONE_DOT.repeat(Math.min(digits.length - 4, 10));
  return `${hidden}${last4}`;
}

/** Concatenated country-code + masked phone — for list views
 *  that already render the country code in its own pill (e.g. the
 *  customer directory). Drops the country code when empty so the
 *  table doesn't show a leading space. */
export function maskedPhoneWithCountry(
  country: string | null | undefined,
  number: string | null | undefined,
): string {
  const c = (country ?? "").trim();
  const masked = maskPhone(number);
  return c ? `${c} ${masked}` : masked;
}
