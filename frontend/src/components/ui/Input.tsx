import { inputStyle } from "./tokens";

/** Token-styled text/number/date input with the ds-input focus
 *  glow class applied. Forwards every standard input prop. */
export function Input({
  className, style, ...rest
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={["ds-input", className].filter(Boolean).join(" ")}
      style={{ ...inputStyle, ...style }}
    />
  );
}
