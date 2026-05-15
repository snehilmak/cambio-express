import type { CSSProperties, ReactNode } from "react";

import { fontSize, tokens } from "./tokens";

export type ButtonTone = "primary" | "secondary" | "danger" | "ghost";

const buttonPalette: Record<ButtonTone, CSSProperties> = {
  primary: {
    background: tokens.accent,
    color: tokens.onAccent,
    border: "none",
  },
  secondary: {
    background: "transparent",
    color: tokens.text,
    border: `1px solid ${tokens.border}`,
  },
  danger: {
    background: "transparent",
    color: tokens.negative,
    border: `1px solid ${tokens.negative}`,
  },
  ghost: {
    background: "transparent",
    color: tokens.textMuted,
    border: "none",
    padding: 0,
    textDecoration: "underline",
  },
};

const buttonSizing = {
  sm: { padding: "0.35rem 0.75rem", fontSize: fontSize.sm,   minHeight: "2rem"   },
  md: { padding: "0.55rem 1rem",    fontSize: "0.9rem",      minHeight: "2.4rem" },
  lg: { padding: "0.75rem 1.4rem",  fontSize: fontSize.base, minHeight: "2.85rem"},
} as const;

export function Button({
  tone = "primary", busy, children, style, type = "button",
  className, size = "md", ...rest
}: {
  tone?: ButtonTone;
  busy?: boolean;
  children: ReactNode;
  style?: CSSProperties;
  type?: "button" | "submit" | "reset";
  className?: string;
  /** `sm` for inline-table buttons / compact toolbars,
   *  `md` (default) for most buttons,
   *  `lg` for primary CTAs in hero/empty states. */
  size?: "sm" | "md" | "lg";
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>,
         "style" | "children" | "type" | "className">) {
  const palette = buttonPalette[tone];
  const dimmed = busy || rest.disabled;
  const cls = ["ds-btn", `ds-btn--${tone}`];
  if (className) cls.push(className);
  const sizing = buttonSizing[size];
  return (
    <button
      type={type}
      {...rest}
      className={cls.join(" ")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.4rem",
        borderRadius: tone === "ghost" ? 0 : "0.5rem",
        padding: tone === "ghost" ? 0 : sizing.padding,
        minHeight: tone === "ghost" ? undefined : sizing.minHeight,
        fontFamily: tokens.fontBody,
        letterSpacing: tone === "primary" ? "-0.005em" : undefined,
        fontSize: tone === "ghost" ? fontSize.sm : sizing.fontSize,
        fontWeight: tone === "primary" || tone === "danger" ? 600 : 500,
        cursor: dimmed ? (busy ? "wait" : "not-allowed") : "pointer",
        opacity: dimmed ? 0.6 : 1,
        whiteSpace: "nowrap",
        ...palette,
        ...style,
      }}
    >
      {children}
    </button>
  );
}


/** Anchor styled like a Button. For internal navigation, prefer
 *  wrapping ``<Button>`` in a ``<Link>`` instead (gets client-side
 *  routing); reach for ``<ButtonLink>`` when you need an ``href``
 *  for CSV downloads, external URLs, etc. */
export function ButtonLink({
  tone = "secondary", children, href, style, className, size = "md", ...rest
}: {
  tone?: ButtonTone;
  href: string;
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
  size?: "sm" | "md" | "lg";
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>,
         "style" | "children" | "href" | "className">) {
  const palette = buttonPalette[tone];
  const sizing = buttonSizing[size];
  const cls = ["ds-btn", `ds-btn--${tone}`];
  if (className) cls.push(className);
  return (
    <a
      href={href}
      {...rest}
      className={cls.join(" ")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.4rem",
        textDecoration: "none",
        borderRadius: "0.5rem",
        padding: sizing.padding,
        minHeight: sizing.minHeight,
        fontFamily: tokens.fontBody,
        fontSize: sizing.fontSize,
        fontWeight: tone === "primary" || tone === "danger" ? 600 : 500,
        whiteSpace: "nowrap",
        ...palette,
        ...style,
      }}
    >
      {children}
    </a>
  );
}
