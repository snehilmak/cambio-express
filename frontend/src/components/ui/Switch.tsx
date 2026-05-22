import type { CSSProperties, ReactNode } from "react";

import { tokens } from "./tokens";

/** Boolean toggle — semantically identical to `<Checkbox>` but
 *  visually a slide switch.  Use for preference / on-off
 *  settings where the visual affordance "I'm flipping a switch"
 *  reads better than "I'm checking a box".
 *
 *  Examples in our codebase: enforce_business_hours,
 *  require_passkey, require_geofence, light/dark theme
 *  preference.  Reach for `<Checkbox>` instead when the control
 *  feels like an item-selection ("Include this in the export?").
 *
 *  Implemented as a native `<input type="checkbox">` under the
 *  hood so form-libraries + native validation hooks Just Work.
 *  The visible UI is CSS-painted; the input is offscreen but
 *  remains keyboard-focusable.
 */
export function Switch({
  checked, defaultChecked, onChange, disabled, name,
  children, style, "aria-describedby": describedBy,
}: {
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (next: boolean) => void;
  disabled?: boolean;
  name?: string;
  /** Label rendered next to the switch.  Pass null/undefined
   *  for an unlabelled switch (rare — usually paired with a
   *  separate `<Field>` label). */
  children?: ReactNode;
  style?: CSSProperties;
  "aria-describedby"?: string;
}) {
  // Render is controlled-or-uncontrolled depending on `checked`
  // — let the native input own the value so React's reconciler
  // doesn't fight the browser's checkbox state.
  const isControlled = checked !== undefined;
  const isOn = isControlled ? checked : defaultChecked;

  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.6rem",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
        ...style,
      }}
    >
      <span style={trackStyle(!!isOn)}>
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          defaultChecked={defaultChecked}
          onChange={(e) => onChange?.(e.target.checked)}
          disabled={disabled}
          name={name}
          aria-describedby={describedBy}
          style={hiddenInputStyle}
        />
        <span style={thumbStyle(!!isOn)} aria-hidden="true" />
      </span>
      {children != null && <span>{children}</span>}
    </label>
  );
}

function trackStyle(on: boolean): CSSProperties {
  return {
    position: "relative",
    width: "2.1rem",
    height: "1.15rem",
    borderRadius: 999,
    background: on ? tokens.accent : tokens.surface3,
    transition: "background 140ms ease-out",
    flexShrink: 0,
    display: "inline-block",
  };
}

function thumbStyle(on: boolean): CSSProperties {
  return {
    position: "absolute",
    top: "50%",
    left: on ? "calc(100% - 0.95rem - 0.1rem)" : "0.1rem",
    transform: "translateY(-50%)",
    width: "0.95rem",
    height: "0.95rem",
    borderRadius: 999,
    background: on ? "var(--db-on-accent, #0a0a0a)" : tokens.text,
    transition: "left 140ms ease-out",
    pointerEvents: "none",
  };
}

// The native input lives invisibly over the track so click +
// keyboard focus still hit the browser checkbox machinery.
// `appearance: none` strips the native paint; opacity:0 hides
// it visually but it remains a hit target.
const hiddenInputStyle: CSSProperties = {
  position: "absolute",
  inset: 0,
  width: "100%",
  height: "100%",
  margin: 0,
  appearance: "none",
  opacity: 0,
  cursor: "inherit",
};
