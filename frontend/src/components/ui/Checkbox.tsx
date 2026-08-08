import type { CSSProperties, ReactNode } from "react";

import { tokens } from "./tokens";

/** Boolean control.  Visually styled to match the kit's
 *  surface / border tokens; behaviourally a plain native
 *  `<input type="checkbox">` so form-libraries (react-hook-form,
 *  uncontrolled forms) Just Work.
 *
 *  Always pass children — they're rendered as the clickable
 *  label.  The whole label-row is the hit target so the checkbox
 *  itself doesn't need pixel-perfect aim.
 *
 *  For purely-decorative use ("show as checked, don't gate any
 *  state"), pair with `disabled` and an explicit `aria-readonly`.
 */
export function Checkbox({
  checked, defaultChecked, onChange, disabled, name, value,
  children, style, "aria-describedby": describedBy,
}: {
  /** Controlled-mode `checked`.  Pair with `onChange` to update
   *  it.  Mutually exclusive with `defaultChecked`. */
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (next: boolean) => void;
  disabled?: boolean;
  name?: string;
  value?: string;
  children: ReactNode;
  style?: CSSProperties;
  "aria-describedby"?: string;
}) {
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "flex-start",
        gap: "0.55rem",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
        ...style,
      }}
    >
      <input
        type="checkbox"
        checked={checked}
        defaultChecked={defaultChecked}
        onChange={(e) => onChange?.(e.target.checked)}
        disabled={disabled}
        name={name}
        value={value}
        aria-describedby={describedBy}
        style={inputStyle}
      />
      <span>{children}</span>
    </label>
  );
}

// Native checkbox styled to match the design system.  Uses
// `accent-color` so the checked state takes the brand neon
// without us having to draw the checkmark ourselves.
const inputStyle: CSSProperties = {
  width: "1rem",
  height: "1rem",
  marginTop: "0.15rem",   // align with the first line of the label
  accentColor: tokens.accent,
  cursor: "inherit",
  flexShrink: 0,
};
