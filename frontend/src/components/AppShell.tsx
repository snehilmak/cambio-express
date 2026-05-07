import { NavLink, useNavigate } from "react-router-dom";

import { clearAccessToken, getCurrentIdentity } from "../lib/auth";

// App chrome wrapping every authed page: sidebar + topbar.
//
// Layout:
//
//   ┌─────────┬──────────────────────────────────┐
//   │ Sidebar │ Topbar (user chrome / sign-out)  │
//   │ (icons  ├──────────────────────────────────┤
//   │ + nav)  │  Page content (children)         │
//   │         │                                  │
//   └─────────┴──────────────────────────────────┘
//
// Sidebar items mirror the legacy sidebar groupings (CLAUDE.md
// "Sidebar groupings"): Workspace · Books · Finance · Account.
// We register each migrated route under the same group so the
// SPA's nav structure converges with the legacy site.
//
// Stays inside RequireAuth in App.tsx — the shell is only
// rendered on authed routes. Login + the bare landing don't
// get the chrome.

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    title: "Workspace",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: iconDashboard() },
    ],
  },
  {
    title: "Books",
    items: [
      { to: "/transfers", label: "Transfers", icon: iconTransfers() },
      { to: "/customers", label: "Customers", icon: iconCustomers() },
      { to: "/daily",     label: "Daily book", icon: iconDaily() },
    ],
  },
  {
    title: "Finance",
    items: [
      { to: "/reports",   label: "Reports", icon: iconReports() },
    ],
  },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const identity = getCurrentIdentity();

  function onSignOut() {
    clearAccessToken();
    navigate("/login", { replace: true });
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "16rem 1fr",
        gridTemplateRows:    "auto 1fr",
        minHeight: "100vh",
        background: "var(--db-surface, #0a0a0a)",
      }}
    >
      <Sidebar />
      <Topbar identity={identity} onSignOut={onSignOut} />
      <ContentColumn>{children}</ContentColumn>
    </div>
  );
}

function Sidebar() {
  return (
    <aside
      style={{
        gridRow: "1 / -1",
        gridColumn: "1",
        background: "var(--db-surface-2, #141414)",
        borderRight: "1px solid var(--db-border, #262626)",
        padding: "1.25rem 0.75rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.6rem",
          padding: "0 0.5rem",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: "1.75rem",
            height: "1.75rem",
            borderRadius: "0.4rem",
            background: "var(--db-accent, #3fff00)",
            color: "var(--db-on-accent, #0a0a0a)",
            fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
            fontWeight: 700,
            fontSize: "1rem",
          }}
        >
          $
        </span>
        <span
          style={{
            fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
            fontWeight: 600,
            fontSize: "1.05rem",
          }}
        >
          DineroBook
        </span>
      </div>

      {NAV.map((group) => (
        <div key={group.title}>
          <p
            style={{
              margin: "0 0.5rem 0.5rem",
              fontSize: "0.72rem",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--db-text-muted, #a3a3a3)",
            }}
          >
            {group.title}
          </p>
          <ul
            style={{
              listStyle: "none",
              margin: 0,
              padding: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.15rem",
            }}
          >
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} style={navLinkStyle} end={false}>
                  {item.icon}
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </aside>
  );
}

function Topbar({
  identity, onSignOut,
}: {
  identity: ReturnType<typeof getCurrentIdentity>;
  onSignOut: () => void;
}) {
  return (
    <header
      style={{
        gridColumn: "2",
        gridRow: "1",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: "1rem",
        padding: "0.85rem 1.5rem",
        borderBottom: "1px solid var(--db-border, #262626)",
        background: "var(--db-surface-2, #141414)",
      }}
    >
      <span
        style={{
          fontSize: "0.9rem",
          color: "var(--db-text-muted, #a3a3a3)",
        }}
      >
        {identity?.username || "—"}
        {identity?.role && (
          <>
            {" "}·{" "}
            <code
              style={{
                fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
                fontSize: "0.85rem",
              }}
            >
              {identity.role}
            </code>
          </>
        )}
      </span>
      <button onClick={onSignOut} style={signOutStyle}>
        Sign out
      </button>
    </header>
  );
}

function ContentColumn({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        gridColumn: "2",
        gridRow: "2",
        minWidth: 0,         // allow children to shrink in CSS grid
        display: "flex",
        flexDirection: "column",
      }}
    >
      {children}
    </div>
  );
}

const navLinkStyle = ({
  isActive,
}: { isActive: boolean }): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: "0.6rem",
  padding: "0.5rem 0.7rem",
  borderRadius: "0.5rem",
  textDecoration: "none",
  color: isActive
    ? "var(--db-text, #f5f5f5)"
    : "var(--db-text-muted, #a3a3a3)",
  background: isActive
    ? "var(--db-surface, #0a0a0a)"
    : "transparent",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.92rem",
  borderLeft: isActive
    ? "2px solid var(--db-accent, #3fff00)"
    : "2px solid transparent",
  transition: "background 120ms ease, color 120ms ease",
});

const signOutStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.4rem 0.85rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.85rem",
  cursor: "pointer",
  transition: "border-color 120ms ease, background 120ms ease",
};

// Inline stroke SVGs per CLAUDE.md design system: stroke-width 2,
// round caps, currentColor, no fill. Match the legacy sidebar's
// look so the SPA + Jinja site feel like one product during the
// migration.

function iconDashboard() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" />
      <rect x="14" y="3" width="7" height="5" />
      <rect x="14" y="12" width="7" height="9" />
      <rect x="3" y="16" width="7" height="5" />
    </svg>
  );
}
function iconTransfers() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M17 4l3 3-3 3" />
      <path d="M20 7H8" />
      <path d="M7 20l-3-3 3-3" />
      <path d="M4 17h12" />
    </svg>
  );
}
function iconCustomers() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <circle cx="9"  cy="8" r="3.5" />
      <path d="M3 20c1.5-3 4-4.5 6-4.5s4.5 1.5 6 4.5" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M14 19.5c.7-1.7 2-2.7 3-2.7s2.3 1 3 2.7" />
    </svg>
  );
}
function iconDaily() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 9h18" />
      <path d="M8 3v4" />
      <path d="M16 3v4" />
    </svg>
  );
}
function iconReports() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 15v-4" />
      <path d="M12 15V8" />
      <path d="M16 15v-6" />
    </svg>
  );
}
