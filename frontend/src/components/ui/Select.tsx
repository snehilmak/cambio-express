import { inputStyle } from "./tokens";

/** Token-styled ``<select>`` with the same focus glow as ``<Input>``. */
export function Select({
  className, style, children, ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={["ds-input", className].filter(Boolean).join(" ")}
      style={{ ...inputStyle, ...style }}
    >
      {children}
    </select>
  );
}
