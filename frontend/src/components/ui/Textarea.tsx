import { inputStyle, tokens } from "./tokens";

/** Token-styled ``<textarea>``. */
export function Textarea({
  className, style, ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...rest}
      className={["ds-input", className].filter(Boolean).join(" ")}
      style={{
        ...inputStyle,
        fontFamily: tokens.fontBody,
        minHeight: "5rem",
        resize: "vertical",
        ...style,
      }}
    />
  );
}
