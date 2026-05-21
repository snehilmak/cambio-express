import type { CSSProperties, ReactNode } from "react";

import { tokens } from "./tokens";

export type IconButtonTone = "neutral" | "danger" | "ghost";
export type IconButtonSize = "sm" | "md";

/** Square / round button for icon-only controls (close ×,
 *  delete trash, kebab menu, etc.).  Use when the kit `<Button>`
 *  is wrong because the action is purely visual + the label is
 *  the icon itself.
 *
 *  Defaults to a neutral border + transparent background that
 *  flips to a subtle hover tint — matches the chrome's other
 *  outlined controls.  `tone="danger"` swaps to a red tint for
 *  destructive icons (× on a connected bank account, etc.).
 *  `tone="ghost"` strips the border for an in-row delete that
 *  shouldn't compete visually with the row's content.
 *
 *  Pair with `title` + `aria-label` so screen readers + tooltip
 *  hovers explain what the icon means.
 */
export function IconButton({
  tone = "neutral", size = "md", children, busy, style, className,
  title, "aria-label": ariaLabel, type = "button", ...rest
}: {
  tone?: IconButtonTone;
  size?: IconButtonSize;
  children: ReactNode;
  busy?: boolean;
  style?: CSSProperties;
  className?: string;
  type?: "button" | "submit" | "reset";
  title?: string;
  "aria-label"?: string;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>,
         "style" | "children" | "type" | "className"
         | "title" | "aria-label">) {
  const dim = size === "sm" ? "1.5rem" : "1.75rem";
  const palette = tone === "danger"
    ? { color: tokens.negative, borderColor: tokens.negative }
    : tone === "ghost"
      ? { color: tokens.textMuted, borderColor: "transparent" }
      : { color: tokens.textMuted, borderColor: tokens.border };
  const cls = ["ds-btn", `ds-iconbtn--${tone}`];
  if (className) cls.push(className);
  const dimmed = busy || rest.disabled;
  return (
    <button
      type={type}
      title={title}
      aria-label={ariaLabel ?? title}
      {...rest}
      className={cls.join(" ")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: dim,
        height: dim,
        padding: 0,
        borderRadius: "50%",
        background: "transparent",
        border: `1px solid ${palette.borderColor}`,
        color: palette.color,
        fontFamily: tokens.fontBody,
        fontSize: size === "sm" ? "0.85rem" : "0.95rem",
        lineHeight: 1,
        cursor: dimmed ? (busy ? "wait" : "not-allowed") : "pointer",
        opacity: dimmed ? 0.55 : 1,
        ...style,
      }}
    >
      {children}
    </button>
  );
}
