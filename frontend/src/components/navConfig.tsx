import type { NavGroup, NavItem } from "./SlimSidebar";

// Single source of truth for the SPA's primary navigation.  Both
// the slim sidebar / fly-out (SlimSidebar) and the /app/home
// tile-hub (HomeHub) read from this list — never duplicate route
// definitions or icons across components.
//
// Role-by-role nav so each persona only sees the surfaces they
// can actually use:
//
//   employee  — Daily only (Dashboard, Transfers, Customers,
//               Daily book, Return checks, Time clock).
//   admin     — Daily + Finance + Account.
//   owner     — Daily (Owner Dashboard) + Owner umbrella +
//               Account. No Finance — those are per-store
//               surfaces the owner reaches via the per-store
//               drill-down inside the Owner section.
//   superadmin — Platform + every other surface for support.
//
// Within Daily, the Dashboard target depends on role: store users
// land on /dashboard, owners on /owner/dashboard, superadmin on
// /superadmin/stores (their list view IS their landing page).
// Each variant is its own NavItem with a `roles` filter so the
// sidebar shows exactly one Dashboard link per role.

export const NAV: NavGroup[] = [
  {
    title: "Daily",
    icon: iconDaily(),
    items: [
      {
        to: "/dashboard", label: "Dashboard",
        roles: ["admin", "employee"],
        icon: iconDashboard(),
      },
      {
        to: "/owner/dashboard", label: "Dashboard",
        roles: ["owner"],
        icon: iconDashboard(),
      },
      {
        to: "/transfers", label: "Transfers",
        roles: ["admin", "employee"],
        icon: iconTransfers(),
      },
      {
        to: "/customers", label: "Customers",
        roles: ["admin", "employee"],
        icon: iconCustomers(),
      },
      {
        to: "/daily", label: "Daily book",
        roles: ["admin", "employee"],
        icon: iconDaily(),
      },
      {
        to: "/return-checks", label: "Return checks",
        roles: ["admin", "employee"],
        icon: iconReturnChecks(),
      },
      {
        // Storefront rate-board addon — admins configure the
        // countries / rates / Fire-TV pairing, customers see the
        // board running on the in-store TV.  Lives in Daily
        // because it's part of the storefront operation, not the
        // ledger/finance stack.
        to: "/tv-display", label: "TV display",
        roles: ["admin"],
        icon: iconDevice(),
      },
    ],
  },
  {
    // HR — anything that's about people / payroll / scheduling
    // rather than money flow.  Time clock is visible to both
    // admin AND employee (employees punch in here); the rest
    // are admin-only management surfaces.  The group disappears
    // entirely for owners / superadmins since `filterNavForRole`
    // drops groups whose every item gets filtered out.
    title: "HR",
    icon: iconHR(),
    items: [
      {
        to: "/timeclock", label: "Time clock",
        roles: ["admin", "employee"],
        icon: iconClock(),
      },
      {
        to: "/admin/timeclock", label: "Payroll",
        roles: ["admin"],
        icon: iconReports(),
      },
      {
        to: "/admin/timeclock/schedule", label: "Schedule",
        roles: ["admin"],
        icon: iconCalendarStar(),
      },
      {
        to: "/admin/timeclock/credentials", label: "Punch credentials",
        roles: ["admin"],
        icon: iconClock(),
      },
      {
        to: "/admin/cashiers", label: "Cashiers",
        roles: ["admin"],
        icon: iconCustomers(),
      },
      {
        to: "/admin/users", label: "Team users",
        roles: ["admin"],
        icon: iconCustomers(),
      },
    ],
  },
  {
    // Reports — everything that's a read-only retrospective view
    // of store activity (audit trails, P&L, exported snapshots).
    // Separate from Finance so the sidebar tells the user "go here
    // to LOOK at what happened" vs "go here to MOVE money."
    title: "Reports",
    roles: ["admin"],
    icon: iconReports(),
    items: [
      { to: "/reports",            label: "Reports",     icon: iconReports() },
      { to: "/monthly",            label: "Monthly P&L", icon: iconMonthly() },
      { to: "/admin/audit-log",    label: "Audit log",   icon: iconAudit() },
      { to: "/admin/data-export",  label: "Data export", icon: iconReports() },
    ],
  },
  {
    title: "Finance",
    roles: ["admin"],
    icon: iconBank(),
    items: [
      { to: "/batches",            label: "ACH batches", icon: iconBatches() },
      { to: "/bank",               label: "Bank sync",   icon: iconBank() },
      { to: "/bank-transactions",  label: "Bank txns",   icon: iconBank() },
    ],
  },
  {
    title: "Owner",
    roles: ["owner"],
    icon: iconOwner(),
    items: [
      { to: "/owner/locations",      label: "Locations",   icon: iconOwner() },
      { to: "/owner/connect",        label: "Connect",     icon: iconBanner() },
      { to: "/owner/bulk-add-user",          label: "Bulk add user",     icon: iconOwner() },
      { to: "/owner/cross-store-defaults",   label: "Cross-store defaults", icon: iconRollup() },
    ],
  },
  {
    // Owner Reports — the cross-store analytical surfaces lifted
    // out of the Owner group so the sidebar tells the same
    // "LOOK at what happened" vs "MOVE money / configure umbrella"
    // story it does for admins.
    title: "Reports",
    roles: ["owner"],
    icon: iconReports(),
    items: [
      { to: "/owner/pl-rollup",  label: "P&L rollup", icon: iconRollup() },
      { to: "/owner/reports",    label: "Reports",    icon: iconReports() },
    ],
  },
  {
    title: "Platform",
    roles: ["superadmin"],
    icon: iconPlatform(),
    items: [
      { to: "/superadmin/dashboard",     label: "Dashboard",     icon: iconDashboard() },
      { to: "/superadmin/stores",        label: "Stores",        icon: iconPlatform() },
      { to: "/superadmin/users",         label: "Users",         icon: iconCustomers() },
      { to: "/superadmin/audit-log",     label: "Audit log",     icon: iconAudit() },
      { to: "/superadmin/announcements", label: "Announcements", icon: iconBanner() },
      { to: "/superadmin/reports",       label: "Reports",       icon: iconReports() },
      { to: "/superadmin/controls",      label: "Controls",      icon: iconSettings() },
      { to: "/superadmin/health",        label: "Health",        icon: iconHealth() },
    ],
  },
  {
    title: "Account",
    icon: iconSettings(),
    items: [
      // Single "Settings" entry that lands on /settings (which
      // redirects to /settings/profile, the first tab).  Visible
      // to every authed role — owners + employees + admins all
      // have a Profile tab.  Used to be two items here (admin-only
      // "Settings" → /settings, everyone "Profile" → /settings/profile);
      // collapsed into one when Profile became a Settings tab.
      {
        to: "/settings", label: "Settings",
        icon: iconSettings(),
      },
      {
        to: "/account/notifications", label: "Notifications",
        icon: iconBell(),
      },
      {
        to: "/account/activity", label: "My activity",
        icon: iconAudit(),
      },
      {
        to: "/account/sessions", label: "Devices",
        icon: iconDevice(),
      },
      {
        to: "/account/referrals", label: "Referrals",
        roles: ["admin"],
        icon: iconBanner(),
      },
    ],
  },
];

export const SUPPORT_LINK: NavItem = {
  to: "/account/tickets", label: "Support", icon: iconSupport(),
};

// Filter NAV down to the groups + items that the current role
// can see. A group is dropped entirely if its `roles` excludes
// this user OR if every item gets filtered out (so we don't
// render an empty icon-only button).
export function filterNavForRole(role: string): NavGroup[] {
  const visible = (i: NavItem) => !i.roles || i.roles.includes(role);
  return NAV
    .filter((g) => !g.roles || g.roles.includes(role))
    .map((g) => ({ ...g, items: g.items.filter(visible) }))
    .filter((g) => g.items.length > 0);
}

// Inline stroke SVGs per CLAUDE.md design system: stroke-width 2,
// round caps, currentColor, no fill. Match the legacy sidebar's
// look so the SPA + Jinja site feel like one product during the
// migration.

function iconDashboard() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M4 4v16h16" />
      <path d="M8 16l3-4 3 2 4-6" />
    </svg>
  );
}
function iconPlatform() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
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
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M3 11l18-5v12l-18-5z" />
      <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
    </svg>
  );
}
function iconBell() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </svg>
  );
}
function iconDevice() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="2" y="4" width="20" height="14" rx="2" />
      <path d="M8 21h8" />
      <path d="M12 18v3" />
    </svg>
  );
}
function iconSettings() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.36.16.66.43.85.78.19.34.31.74.32 1.13V12c0 .39-.12.79-.32 1.13-.19.34-.49.61-.85.78z" />
    </svg>
  );
}

function iconHealth() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}
function iconSupport() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
      <path d="M12 17h.01" />
    </svg>
  );
}
function iconClock() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function iconCalendarStar() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 9h18" />
      <path d="M8 3v4" />
      <path d="M16 3v4" />
      <polyline points="9 14 12 17 16 13" />
    </svg>
  );
}

// Briefcase — universal HR / employer / payroll glyph.  Distinct
// from iconOwner (single person with check) + iconCustomers
// (two-person group) so the slim sidebar reads cleanly.
function iconHR() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M2 13h20" />
    </svg>
  );
}
