import { useEffect, useRef, useState } from "react";
import {
  AsYouType,
  getCountryCallingCode,
  parsePhoneNumber,
  type CountryCode,
} from "libphonenumber-js";

import { Input } from "./Input";
import { Select } from "./Select";

// Reusable phone control: a country picker + a national-number input
// that emits a single E.164 string ("+13105551234") — or "" when
// empty — via `onChange`. Per-country validation lives in the schema
// (`zPhoneOptional` / `zPhoneRequired` in lib/validators); this
// component is purely the input surface.
//
// Value contract:
//   * `value` is E.164 or "". On mount / external change it's parsed
//     back into a country + a nicely-formatted national number.
//   * While typing, an incomplete number still emits a best-effort
//     E.164 ("+1512555…") so the validator flags it as invalid rather
//     than silently treating it as "no phone entered".
//
// Bare control by convention — wrap it in <Field label error> like any
// other input.

// Curated list — US first (default), then the common remittance
// destinations this product serves. Calling codes are derived from
// libphonenumber-js so they can't drift.
const COUNTRIES: { iso: CountryCode; name: string; flag: string }[] = [
  { iso: "US", name: "United States", flag: "🇺🇸" },
  { iso: "MX", name: "Mexico", flag: "🇲🇽" },
  { iso: "GT", name: "Guatemala", flag: "🇬🇹" },
  { iso: "HN", name: "Honduras", flag: "🇭🇳" },
  { iso: "SV", name: "El Salvador", flag: "🇸🇻" },
  { iso: "NI", name: "Nicaragua", flag: "🇳🇮" },
  { iso: "CO", name: "Colombia", flag: "🇨🇴" },
  { iso: "DO", name: "Dominican Rep.", flag: "🇩🇴" },
  { iso: "IN", name: "India", flag: "🇮🇳" },
  { iso: "PH", name: "Philippines", flag: "🇵🇭" },
];

function callingCode(iso: CountryCode): string {
  try {
    return getCountryCallingCode(iso);
  } catch {
    return "";
  }
}

// Best-effort E.164 from a (possibly incomplete) national string.
function toE164(display: string, country: CountryCode): string {
  const digits = display.replace(/\D/g, "");
  if (!digits) return "";
  try {
    const parsed = parsePhoneNumber(display, country);
    if (parsed) return parsed.number; // valid → canonical E.164
  } catch {
    /* fall through to best-effort below */
  }
  const cc = callingCode(country);
  return cc ? `+${cc}${digits}` : `+${digits}`;
}

export interface PhoneFieldProps {
  value: string;
  onChange: (e164: string) => void;
  defaultCountry?: CountryCode;
  disabled?: boolean;
  id?: string;
  name?: string;
  placeholder?: string;
  "aria-invalid"?: boolean;
}

export function PhoneField({
  value,
  onChange,
  defaultCountry = "US",
  disabled,
  id,
  name,
  placeholder = "(555) 123-4567",
  "aria-invalid": ariaInvalid,
}: PhoneFieldProps) {
  const [country, setCountry] = useState<CountryCode>(defaultCountry);
  const [display, setDisplay] = useState("");
  // Tracks the last E.164 we emitted so an external `value` sync doesn't
  // clobber the number the user is actively typing (our own echo).
  const lastEmitted = useRef<string>("");

  // Hydrate the internal display buffer from the external `value` prop
  // (edit-form load / programmatic set). This is the canonical
  // sync-to-external-state effect — `value` is owned outside this
  // component, and we keep a formatted national display separate from
  // the E.164 wire value, so the setState calls here are intentional.
  /* eslint-disable react-hooks/set-state-in-effect -- hydrate local formatted-display buffer from the external value prop */
  useEffect(() => {
    if (value === lastEmitted.current) return; // our own echo — ignore
    if (!value) {
      setDisplay("");
      return;
    }
    try {
      const parsed =
        parsePhoneNumber(value) ?? parsePhoneNumber(value, defaultCountry);
      if (parsed) {
        setCountry((parsed.country as CountryCode) ?? defaultCountry);
        setDisplay(parsed.formatNational());
        lastEmitted.current = value;
        return;
      }
    } catch {
      /* not parseable — show raw so nothing is lost */
    }
    setDisplay(value);
  }, [value, defaultCountry]);
  /* eslint-enable react-hooks/set-state-in-effect */

  function emit(nextDisplay: string, nextCountry: CountryCode) {
    setDisplay(nextDisplay);
    setCountry(nextCountry);
    const e164 = toE164(nextDisplay, nextCountry);
    lastEmitted.current = e164;
    onChange(e164);
  }

  function onNumberInput(raw: string) {
    // AsYouType progressively formats the national number for the
    // selected country as the operator types.
    emit(new AsYouType(country).input(raw), country);
  }

  function onCountryChange(nextIso: CountryCode) {
    // Re-format the existing digits under the new country's rules.
    const digits = display.replace(/\D/g, "");
    emit(new AsYouType(nextIso).input(digits), nextIso);
  }

  return (
    <div style={{ display: "flex", gap: "0.5rem" }}>
      <Select
        aria-label="Country code"
        value={country}
        disabled={disabled}
        onChange={(e) => onCountryChange(e.target.value as CountryCode)}
        style={{ flex: "0 0 auto", width: "auto", minWidth: "6.5rem" }}
      >
        {COUNTRIES.map((c) => (
          <option key={c.iso} value={c.iso}>
            {c.flag} +{callingCode(c.iso)}
          </option>
        ))}
      </Select>
      <Input
        type="tel"
        inputMode="tel"
        autoComplete="tel-national"
        id={id}
        name={name}
        value={display}
        disabled={disabled}
        placeholder={placeholder}
        aria-invalid={ariaInvalid}
        onChange={(e) => onNumberInput(e.target.value)}
        style={{ flex: "1 1 auto" }}
      />
    </div>
  );
}
