// PII formatting helpers — keep redaction rules in one place so
// every list view + report masks the same way and the audit
// surface for "what does over-the-shoulder reveal?" stays small.

const PHONE_DOT = "·"; // middle dot · — visually distinct from the comma we see in non-mono fonts

/** Mask all but the last 4 digits of a phone number.
 *    "555-555-1234"   → "·······1234"
 *    "(555) 555-1234" → "··········1234"
 *    "1234"           → "1234"
 *    ""               → "—"
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
