import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";

import { fontSize, tokens } from "./tokens";

export type ButtonTone = "primary" | "secondary" | "danger" | "ghost";

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
        ...style,
      }}
    >
      {children}
    </button>
  );
}


/** Button-styled link.  Renders as either an `<a>` or a React
 *  Router `<Link>` depending on which prop you pass:
 *
 *    - `to`   → internal SPA route (client-side, no full reload).
 *               React Router prefixes the SPA basename `/app` so
 *               pass the path WITHOUT it (`to="/dashboard"`, not
 *               `to="/app/dashboard"`).
 *    - `href` → external URL or download (full HTTP request).
 *               Use for CSV downloads, Stripe portal redirects,
 *               or anything outside the SPA shell.
 *
 *  Exactly one of `to` or `href` must be set.  In dev, the
 *  combination of both will type-error via the discriminated
 *  union; in prod, `to` wins.
 */
export function ButtonLink({
  tone = "secondary", children, to, href, style, className, size = "md",
  ...rest
}: {
  tone?: ButtonTone;
  to?: string;
  href?: string;
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
  size?: "sm" | "md" | "lg";
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>,
         "style" | "children" | "href" | "className">) {
  const sizing = buttonSizing[size];
  const cls = ["ds-btn", `ds-btn--${tone}`];
  if (className) cls.push(className);
  const sharedStyle: CSSProperties = {
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
    ...style,
  };
  // Prefer client-side routing when a SPA `to` is provided —
  // avoids the full-page-reload flash that hurts perceived
  // perf + drops React-Query / TanStack state on every nav.
  if (to !== undefined) {
    return (
      <Link to={to} className={cls.join(" ")} style={sharedStyle}>
        {children}
      </Link>
    );
  }
  return (
    <a
      href={href}
      {...rest}
      className={cls.join(" ")}
      style={sharedStyle}
    >
      {children}
    </a>
  );
}
