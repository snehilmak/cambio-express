// Shared field-validation library (system-wide standard).
//
// One source of truth for the rules every form reuses, so "email must
// look like an email" or "phone must be a valid number" is defined once
// and applied everywhere. Built on Zod (the project's form-validation
// standard) so it plugs into both stacks in the codebase:
//
//   * react-hook-form forms → pass a composed schema to `zodResolver`.
//   * plain useState forms   → call `<schema>.safeParse(value)` inline
//     and drop `.error.issues[0].message` into the field's error slot.
//
// Phone validation is backed by libphonenumber-js so per-country rules
// (US = 10 digits, other countries = their own formats) come for free —
// see `PhoneField` for the matching input component. The canonical wire
// format for a phone value is E.164 ("+13105551234") or "" when empty.

import { z } from "zod";
import { isValidPhoneNumber, type CountryCode } from "libphonenumber-js";

// ── Strings ────────────────────────────────────────────────

/** Trimmed, non-empty. `label` personalises the message. */
export const zRequiredString = (label = "This field") =>
  z.string().trim().min(1, `${label} is required`);

/** Trimmed, optional (empty string allowed). */
export const zOptionalString = z.string().trim();

// Pragmatic email shape — one @, a dot in the domain, no spaces. We
// deliberately don't chase the full RFC 5322 grammar; the real
// deliverability check is the server + the confirmation email.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Valid email, or empty (optional field). */
export const zEmailOptional = z
  .string()
  .trim()
  .refine((v) => v === "" || EMAIL_RE.test(v), {
    message: "Enter a valid email address",
  });

/** Valid email, required. */
export const zEmailRequired = z
  .string()
  .trim()
  .refine((v) => EMAIL_RE.test(v), { message: "Enter a valid email address" });

// ── Numbers ────────────────────────────────────────────────

/** Digits only. Pass `length` to require an exact count (e.g. a 5-digit
 *  ZIP). Empty passes — wrap with a required check when mandatory. */
export const zDigitsOnly = (length?: number) =>
  z.string().trim().refine(
    (v) =>
      v === "" ||
      (/^\d+$/.test(v) && (length === undefined || v.length === length)),
    {
      message:
        length !== undefined ? `Enter exactly ${length} digits` : "Numbers only",
    },
  );

/** Coerced positive whole number (`<input type="number">` gives a string). */
export const zPositiveInt = z.coerce
  .number()
  .int("Must be a whole number")
  .positive("Must be greater than 0");

/** Coerced number ≥ 0. */
export const zNonNegativeNumber = z.coerce
  .number()
  .min(0, "Must be 0 or more");

/** Money amount — coerced number ≥ 0. Use `zMoneyPositive` when 0 is invalid. */
export const zMoney = z.coerce.number().min(0, "Must be 0 or more");
export const zMoneyPositive = z.coerce
  .number()
  .positive("Must be greater than 0");

/** A fraction in [0, 1] — e.g. a tax rate stored as 0.01 = 1%. */
export const zFraction = z.coerce
  .number()
  .min(0, "Must be 0 or more")
  .max(1, "Must be 1.0 (100%) or less");

// ── Choice / date ──────────────────────────────────────────

/** A dropdown that must be chosen (non-empty value). */
export const zRequiredSelect = (label = "Selection") =>
  z.string().min(1, `${label} is required`);

/** A required date string (`<input type="date">` → "YYYY-MM-DD"). */
export const zRequiredDate = (label = "Date") =>
  z.string().min(1, `${label} is required`);

// ── Phone ──────────────────────────────────────────────────

/** True when `value` is a valid phone number. E.164 strings (leading
 *  "+") are validated globally; bare national strings are validated
 *  against `country`. Never throws. */
export function isValidPhone(
  value: string,
  country: CountryCode = "US",
): boolean {
  if (!value) return false;
  try {
    return value.startsWith("+")
      ? isValidPhoneNumber(value)
      : isValidPhoneNumber(value, country);
  } catch {
    return false;
  }
}

/** Valid phone (E.164) or empty — the common optional-contact case. */
export const zPhoneOptional = z
  .string()
  .trim()
  .refine((v) => v === "" || isValidPhone(v), {
    message: "Enter a valid phone number",
  });

/** Valid phone (E.164), required. */
export const zPhoneRequired = z
  .string()
  .trim()
  .refine((v) => isValidPhone(v), { message: "Enter a valid phone number" });

// ── Helpers for plain (non-RHF) forms ──────────────────────

/** Run a single schema against a value and return the first error
 *  message, or null when valid. Ergonomic for the useState +
 *  fieldErrors pattern: `setError("email", firstError(zEmailOptional, v))`. */
export function firstError(
  schema: z.ZodType,
  value: unknown,
): string | null {
  const res = schema.safeParse(value);
  return res.success ? null : (res.error.issues[0]?.message ?? "Invalid value");
}
