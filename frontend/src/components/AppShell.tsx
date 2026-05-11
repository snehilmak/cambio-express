import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

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
  /** Roles that should see this group. Omit for "everyone authed". */
  roles?: string[];
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
      { to: "/transfers",     label: "Transfers",     icon: iconTransfers() },
      { to: "/customers",     label: "Customers",     icon: iconCustomers() },
      { to: "/daily",         label: "Daily book",    icon: iconDaily() },
      { to: "/return-checks", label: "Return checks", icon: iconReturnChecks() },
    ],
  },
  {
    title: "Finance",
    items: [
      { to: "/reports",            label: "Reports",     icon: iconReports() },
      { to: "/monthly",            label: "Monthly P&L", icon: iconMonthly() },
      { to: "/batches",            label: "ACH batches", icon: iconBatches() },
      { to: "/bank-transactions",  label: "Bank txns",   icon: iconBank() },
    ],
  },
  {
    title: "Owner",
    roles: ["owner", "superadmin"],
    items: [
      { to: "/owner/locations", label: "Locations", icon: iconOwner() },
      { to: "/owner/pl-rollup", label: "P&L rollup", icon: iconRollup() },
    ],
  },
  {
    title: "Platform",
    roles: ["superadmin"],
    items: [
      { to: "/superadmin/stores",        label: "Stores",        icon: iconPlatform() },
      { to: "/superadmin/audit-log",     label: "Audit log",     icon: iconAudit() },
      { to: "/superadmin/announcements", label: "Announcements", icon: iconBanner() },
    ],
  },
  {
    title: "Account",
    items: [
      { to: "/settings",  label: "Settings",    icon: iconSettings() },
    ],
  },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const identity = getCurrentIdentity();
  // Drawer is a mobile-only concern but the state lives unconditionally
  // so the CSS class flip is the same code path on every viewport.
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Auto-close the drawer on navigation. Without this, tapping a
  // nav link on mobile would route to the new page but leave the
  // drawer open over it. The route-change pulse is the canonical
  // "sync to external state" use of an effect — pathname is owned
  // by the router, not React state.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- close drawer when the router navigates; pathname comes from outside React state
    setDrawerOpen(false);
  }, [location.pathname]);

  function onSignOut() {
    clearAccessToken();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <Sidebar drawerOpen={drawerOpen} />
      <Topbar
        identity={identity}
        onSignOut={onSignOut}
        onToggleDrawer={() => setDrawerOpen((v) => !v)}
      />
      <ContentColumn>{children}</ContentColumn>
      <button
        type="button"
        aria-hidden={!drawerOpen}
        tabIndex={-1}
        className={`app-backdrop${drawerOpen ? " is-open" : ""}`}
        onClick={() => setDrawerOpen(false)}
      />
    </div>
  );
}

function Sidebar({ drawerOpen }: { drawerOpen: boolean }) {
  const identity = getCurrentIdentity();
  const role = identity?.role ?? "";
  const groups = NAV.filter(
    (g) => !g.roles || g.roles.includes(role),
  );
  return (
    <aside
      className={`app-sidebar${drawerOpen ? " is-open" : ""}`}
      aria-label="Primary navigation"
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

      {groups.map((group) => (
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
  identity, onSignOut, onToggleDrawer,
}: {
  identity: ReturnType<typeof getCurrentIdentity>;
  onSignOut: () => void;
  onToggleDrawer: () => void;
}) {
  return (
    <header className="app-topbar">
      <button
        type="button"
        className="app-hamburger"
        aria-label="Open navigation"
        onClick={onToggleDrawer}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M4 6h16" />
          <path d="M4 12h16" />
          <path d="M4 18h16" />
        </svg>
      </button>
      <span style={topbarSpacer} />
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
  return <div className="app-content">{children}</div>;
}

const topbarSpacer: React.CSSProperties = { flex: 1 };

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
function iconBatches() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M3 5h18" />
      <path d="M3 12h18" />
      <path d="M3 19h18" />
    </svg>
  );
}
function iconBank() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M3 10l9-6 9 6" />
      <path d="M5 10v8" />
      <path d="M9 10v8" />
      <path d="M15 10v8" />
      <path d="M19 10v8" />
      <path d="M3 20h18" />
    </svg>
  );
}
function iconReturnChecks() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <path d="M7 10h6" />
      <path d="M7 14h4" />
      <path d="M17 9l3 3-3 3" />
    </svg>
  );
}
function iconMonthly() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="3" y="6" width="18" height="14" rx="2" />
      <path d="M3 10h18" />
      <path d="M8 4v4" />
      <path d="M16 4v4" />
    </svg>
  );
}
function iconOwner() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <circle cx="9" cy="6" r="3" />
      <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
      <path d="M16 3l2 2 4-4" />
    </svg>
  );
}
function iconRollup() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M4 4v16h16" />
      <path d="M8 16l3-4 3 2 4-6" />
    </svg>
  );
}
function iconPlatform() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="3"  y="3"  width="7" height="7" rx="1.5" />
      <rect x="14" y="3"  width="7" height="7" rx="1.5" />
      <rect x="3"  y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}
function iconAudit() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </svg>
  );
}
function iconBanner() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M3 11l18-5v12l-18-5z" />
      <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
    </svg>
  );
}
function iconSettings() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.36.16.66.43.85.78.19.34.31.74.32 1.13V12c0 .39-.12.79-.32 1.13-.19.34-.49.61-.85.78z" />
    </svg>
  );
}
