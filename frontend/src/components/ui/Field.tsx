import type { CSSProperties, ReactNode } from "react";

import { tokens } from "./tokens";

/** Form field label wrapper with optional inline error + hint.
 *
 *  Standard usage:
 *
 *      <Field label="Email" error={errors.email} hint="We never share this.">
 *        <Input type="email" {...register("email")} />
 *      </Field>
 */
export function Field({
  label, highlight, error, hint, style, children,
}: {
  label: ReactNode;
  /** Tints the label red when the server flagged a field-level
   *  validation error. Inferred to ``true`` when ``error`` is set. */
  highlight?: boolean;
  /** Field-level error message. Renders below ``children`` in the
   *  negative color, and tints the label red. The server's
   *  ``field_errors`` envelope maps 1:1 to this prop. */
  error?: ReactNode;
  /** Small muted help text below ``children`` (above the error if
   *  both are present). For the "you can't deactivate yourself"
   *  class of inline guidance. */
  hint?: ReactNode;
  /** Extra style on the wrapping ``<label>``. Use for ``gridColumn:
   *  "1 / -1"`` style overrides when a field needs to span the full
   *  width of a parent grid. */
  style?: CSSProperties;
  children: ReactNode;
}) {
  const isErr = Boolean(error) || highlight;
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.45rem", ...style }}>
      {label !== "" && label != null && (
        <span
          style={{
            // Slightly bigger + bolder than the original 0.78rem / 400.
            // 0.8rem / 600 reads as a proper form label instead of a
            // whisper.
            fontSize: "0.8rem",
            fontWeight: 600,
            color: isErr ? tokens.negative : tokens.text,
            letterSpacing: "0",
          }}
        >
          {label}
        </span>
      )}
      {children}
      {hint && (
        <span style={{ fontSize: "0.78rem", color: tokens.textMuted }}>
          {hint}
        </span>
      )}
      {error && (
        <span style={{ fontSize: "0.8rem", color: tokens.negative }}>
          {error}
        </span>
      )}
    </label>
  );
}
