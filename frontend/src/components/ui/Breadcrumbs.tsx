import { Link } from "react-router-dom";

import { tokens } from "./tokens";

/** Breadcrumb navigation trail — shows the user where they are
 *  and lets them jump back to any ancestor page.
 *
 *  ```tsx
 *  <Breadcrumbs crumbs={[
 *    { label: "Transfers", to: "/transfers" },
 *    { label: `Transfer #${id}` },
 *  ]} />
 *  ```
 *
 *  The last crumb is the current page (no link). Every other
 *  crumb is a `<Link>`. Especially important in the PWA
 *  standalone window where the browser back button is invisible.
 */
export function Breadcrumbs({ crumbs }: {
  crumbs: Array<{ label: string; to?: string }>;
}) {
  if (crumbs.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" style={barStyle}>
      <ol style={listStyle}>
        {crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <li key={i} style={itemStyle}>
              {i > 0 && <span style={sepStyle} aria-hidden="true">/</span>}
              {c.to && !isLast ? (
                <Link to={c.to} style={linkStyle}>
                  {c.label}
                </Link>
              ) : (
                <span style={isLast ? currentStyle : linkStyle}>
                  {c.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

const barStyle: React.CSSProperties = {
  fontSize: "0.8rem",
  fontFamily: tokens.fontBody,
};

const listStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "0.15rem",
  listStyle: "none",
  margin: 0,
  padding: 0,
};

const itemStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.15rem",
};

const sepStyle: React.CSSProperties = {
  color: tokens.textMuted,
  userSelect: "none",
  padding: "0 0.25rem",
};

const linkStyle: React.CSSProperties = {
  color: tokens.textMuted,
  textDecoration: "none",
};

const currentStyle: React.CSSProperties = {
  color: tokens.text,
  fontWeight: 500,
};
