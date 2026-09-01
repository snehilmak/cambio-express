import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useProfile, useSessionStatus, useStoreInfo } from "../api/account";
import { useTicketsUnread } from "../api/support";
import { clearAccessToken, getCurrentIdentity } from "../lib/auth";
import StoreGate from "./StoreGate";
import { clearVisits, recordVisit } from "../lib/recency";
import { reconcileTheme } from "../lib/theme";
import { AnnouncementBanner } from "./AnnouncementBanner";
import { CommandPalette } from "./CommandPalette";
import { HelpCenter } from "./HelpCenter";
import { InstallAppButton } from "./InstallAppButton";
import { filterNavForRole, SUPPORT_LINK } from "./navConfig";
import { isOwnerSession } from "../api/switchStore";
import { SlimSidebar } from "./SlimSidebar";
import SwitchStoreModal from "./SwitchStoreModal";
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
  // Unread ticket replies — the phone-style badge on the Support
  // nav button (polls every minute + refetch-on-focus).
  const ticketsUnread = useTicketsUnread();
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

  // Store gate (PR C): a frozen or lapsed-subscription store locks its
  // users out to a re-subscribe / suspended screen. Superadmin is never
  // gated (backend returns gated=false — no store scope). While the
  // status query is loading we render the normal shell to avoid a
  // gate flash on every navigation.
  const { data: sessionStatus } = useSessionStatus();
  const gated = sessionStatus?.gated === true;
  const gateReason = sessionStatus?.reason;
  // The subscription gate must let the Subscribe flow render so the user
  // can self-serve re-subscribe (Stripe Checkout). basename is "/app",
  // so the in-router path is "/subscribe". Frozen has no self-serve path,
  // so it gates every route.
  const onSubscribeFlow = location.pathname.startsWith("/subscribe");
  const showGate =
    gated && !(gateReason === "subscription" && onSubscribeFlow);
  if (showGate && (gateReason === "frozen" || gateReason === "subscription")) {
    return (
      <StoreGate
        reason={gateReason}
        storeName={sessionStatus?.store_name ?? ""}
        onSignOut={onSignOut}
      />
    );
  }

  const role = identity?.role ?? "";
  const perms = identity?.permissions ?? [];
  const groups = filterNavForRole(role, perms, sessionStatus?.features);
  return (
    <div className="app-shell">
      <SlimSidebar
        groups={groups}
        drawerOpen={drawerOpen}
        supportLink={SUPPORT_LINK}
        supportBadge={ticketsUnread.data?.unread ?? 0}
      />
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
      {/* Floating help bubble — only inside ``RequireAuth`` so
          the bottom-right CTA never bleeds onto the marketing
          landing or login pages. */}
      <CommandPalette />
      <HelpCenter />
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
  const storeInfo = useStoreInfo();
  const referralCode = storeInfo.data?.referral_code;
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
      {isOwnerSession() && <StoreSwitchChip identity={identity} />}
      <span style={topbarSpacer} />
      <TrialChip />
      {referralCode && <ReferralBadge code={referralCode} />}
      <InstallAppButton />
      <ThemeToggle />
      <UserMenu identity={identity} onSignOut={onSignOut} />
    </header>
  );
}

// Trial countdown (W-1). Present for the WHOLE trial rather than
// appearing near the end: "5 days left" on day two sets an
// expectation, while something that materialises on day four reads
// as an alarm. It is a link, not a dismissible notice — a dismissal
// is a one-time event, and the person who most needs the reminder is
// the one who dismissed it on day two.
//
// Nothing renders for a paid store: the server sends `trial: null`.
function TrialChip() {
  const session = useSessionStatus();
  const trial = session.data?.trial;
  if (!trial) return null;
  return (
    <Link
      to="/subscribe"
      className={`app-trial-chip is-${trial.tone}`}
      title={`${trial.message} Click to subscribe.`}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2" strokeLinecap="round"
        strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
      <span className="app-trial-chip-text">
        {trial.status === "active" || trial.status === "expiring_soon"
          ? (trial.days_left === 0
              ? "Trial ends today"
              : `${trial.days_left} day${trial.days_left === 1 ? "" : "s"} left`)
          : "Trial ended"}
      </span>
      <span className="app-trial-chip-cta">Subscribe</span>
    </Link>
  );
}

// Owner store-context chip (U-2, single-dashboard principle):
// shows which store the owner is currently viewing and opens the
// Switch Store modal. Rendered only for owner sessions — base
// owner logins ("Enter a store") and owner-context store views.
function StoreSwitchChip({
  identity,
}: {
  identity: ReturnType<typeof getCurrentIdentity>;
}) {
  const [open, setOpen] = useState(false);
  const session = useSessionStatus();
  const inStore = identity?.role === "admin" && identity?.owner_id != null;
  const label = inStore
    ? (session.data?.store_name || "Switch store")
    : "Enter a store";
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Switch store"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.4rem",
          padding: "0.3rem 0.8rem",
          borderRadius: "999px",
          border: "1px solid var(--db-border-strong, var(--border-strong))",
          background: "var(--db-surface-2, var(--surface-2))",
          color: "var(--db-text, var(--text))",
          cursor: "pointer",
          fontWeight: 600,
          maxWidth: "14rem",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M3 9l1-5h16l1 5" />
          <path d="M4 9v11h16V9" />
          <path d="M9 20v-6h6v6" />
        </svg>
        {label}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <SwitchStoreModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function ReferralBadge({ code }: { code: string }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate("/account/referrals")}
      title={`Earn $100 — share your code: ${code}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.3rem",
        padding: "0.3rem 0.7rem",
        borderRadius: "999px",
        background: "linear-gradient(135deg, #d4a017 0%, #f5c842 100%)",
        color: "#1a1a1a",
        fontSize: "0.72rem",
        fontWeight: 800,
        letterSpacing: "0.03em",
        cursor: "pointer",
        border: "none",
        whiteSpace: "nowrap",
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="#1a1a1a"
        stroke="none" aria-hidden="true">
        <path d="M2.5 8.5L5 3h14l2.5 5.5L12 21 2.5 8.5z" />
        <path d="M12 3l-2 5.5h4L12 3z" opacity="0.5" />
      </svg>
      $100
    </button>
  );
}

function MaintenanceBanner() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/v2/maintenance-status")
      .then((r) => r.json())
      .then((d: { enabled: boolean; message: string }) => {
        if (d.enabled) setMsg(d.message || "The platform is under maintenance.");
        else setMsg(null);
      })
      .catch(() => {});
  }, []);
  if (!msg) return null;
  return (
    <div style={{
      background: "var(--db-tone-warning-bg, rgba(245,158,11,0.12))",
      border: "1px solid var(--db-tone-warning-border, rgba(245,158,11,0.3))",
      color: "var(--db-tone-warning-fg, #fbbf24)",
      padding: "0.6rem 1.25rem",
      textAlign: "center",
      fontSize: "0.88rem",
      fontWeight: 500,
    }}>
      {msg}
    </div>
  );
}

function ContentColumn({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-content">
      <MaintenanceBanner />
      <AnnouncementBanner />
      {children}
    </div>
  );
}

const topbarSpacer: React.CSSProperties = { flex: 1 };
