import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useProfile } from "../api/account";
import { clearAccessToken, getCurrentIdentity } from "../lib/auth";
import { clearVisits, recordVisit } from "../lib/recency";
import { reconcileTheme } from "../lib/theme";
import { AnnouncementBanner } from "./AnnouncementBanner";
import { HomeButton } from "./HomeButton";
import { InstallAppButton } from "./InstallAppButton";
import { filterNavForRole } from "./navConfig";
import { SlimSidebar } from "./SlimSidebar";
import ThemeToggle from "./ThemeToggle";
import { UserMenu } from "./UserMenu";

// App chrome wrapping every authed page: slim icon sidebar + topbar.
//
// Layout:
//
//   ┌───┬──────────────────────────────────────┐
//   │   │ Topbar (user chrome / sign-out)      │
//   │ s ├──────────────────────────────────────┤
//   │ l │ Page content (children)              │
//   │ i │                                      │
//   │ m │  (fly-out panel slides in from the   │
//   │   │   slim column when a group is        │
//   │   │   tapped — see SlimSidebar)          │
//   └───┴──────────────────────────────────────┘
//
// Groups are: Daily · Finance · Owner · Platform · Account
// (Workspace + Books merged into Daily — the day-to-day flow
// of running a store).  Each group renders as an icon in the
// 4.75rem slim column; clicking opens a fly-out with that
// group's items as colored tiles.  On mobile the slim column +
// fly-out collapse into the AppShell hamburger drawer instead,
// which renders the same data as one scrollable column.
//
// Stays inside RequireAuth in App.tsx — the shell is only
// rendered on authed routes. Login + the bare landing don't
// get the chrome.


export default function AppShell({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const identity = getCurrentIdentity();
  // Drawer is a mobile-only concern but the state lives unconditionally
  // so the CSS class flip is the same code path on every viewport.
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Pull the user's saved theme preference and apply it. The
  // inline script in index.html already restored the localStorage
  // cache for first paint; this catches the case where the user
  // toggled the theme on another device. Server wins.
  const { data: profile } = useProfile();
  useEffect(() => {
    reconcileTheme(profile?.theme_preference);
  }, [profile?.theme_preference]);

  // Auto-close the drawer on navigation. Without this, tapping a
  // nav link on mobile would route to the new page but leave the
  // drawer open over it. The route-change pulse is the canonical
  // "sync to external state" use of an effect — pathname is owned
  // by the router, not React state.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- close drawer when the router navigates; pathname comes from outside React state
    setDrawerOpen(false);
  }, [location.pathname]);

  // Record every authed route hit so the /app/home "Most Used"
  // strip can rank by frequency.  Skip /home itself (don't surface
  // the hub on the hub) — the strip-rank filter at the call site
  // is also enforced via the eligiblePaths set in topVisited().
  useEffect(() => {
    if (location.pathname && !location.pathname.endsWith("/home")) {
      recordVisit(location.pathname);
    }
  }, [location.pathname]);

  function onSignOut() {
    clearAccessToken();
    // Shared-device hygiene — the next user on this browser
    // shouldn't inherit the previous cashier's "Most Used" tiles.
    clearVisits();
    navigate("/login", { replace: true });
  }

  const role = identity?.role ?? "";
  const groups = filterNavForRole(role);
  return (
    <div className="app-shell">
      <SlimSidebar groups={groups} drawerOpen={drawerOpen} />
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
      <HomeButton />
      <InstallAppButton />
      <ThemeToggle />
      <UserMenu identity={identity} onSignOut={onSignOut} />
    </header>
  );
}

function ContentColumn({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-content">
      <AnnouncementBanner />
      {children}
    </div>
  );
}

const topbarSpacer: React.CSSProperties = { flex: 1 };
