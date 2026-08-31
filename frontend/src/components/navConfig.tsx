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

// Slug used for the section-hub route (/hub/:key). Titles are
// unique within a single role's filtered nav, so slugifying the
// group title is a stable per-role key. Keep this the ONLY place
// the mapping is defined so the flyout header link + the hub route
// resolver never drift.
export function sectionSlug(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export const NAV: NavGroup[] = [
  {
    // Dashboard as its own top-level destination (owner directive)
    // — a direct-link group like Reports used to be, so the first
    // sidebar click lands on the numbers, not a fly-out. Per-role
    // variants because the landing route differs.
    title: "Dashboard",
    roles: ["admin", "employee"],
    icon: iconDashboard(),
    to: "/dashboard",
    items: [],
  },
  {
    title: "Dashboard",
    roles: ["owner"],
    icon: iconDashboard(),
    to: "/owner/dashboard",
    items: [],
  },
  {
    // Daily operations. The store-level retail modules (Store
    // daily book / Lottery / Price book) carry roles: superadmin is the platform
    // operator, not a store — store modules stay off their nav
    // (they can still reach any route directly for support).
    title: "Daily",
    icon: iconDaily(),
    items: [
      {
        to: "/daily", label: "MSB Daily book",
        roles: ["admin", "employee"],
        perm: "daily_book.read",
        icon: iconDaily(),
        desc: "MSB cash ledger and daily close-out.",
      },
      {
        to: "/store-book", label: "Store Daily book",
        roles: ["admin", "employee"],
        flag: "module_day_close", perm: "day_close.read",
        icon: iconRegister(),
        desc: "Sales, tenders, deposits, and the day's over/short.",
      },
      {
        // Ticket-level detail from the register. Same flag + read
        // right as the store daily book it belongs beside — a
        // cashier looking up a customer's ticket needs no more.
        to: "/transactions", label: "Transactions",
        roles: ["admin", "employee"],
        flag: "module_day_close", perm: "day_close.read",
        icon: iconReceipt(),
        desc: "Every register ticket, item by item.",
      },
      {
        to: "/lottery", label: "Lottery",
        roles: ["admin", "employee"],
        flag: "module_lottery", perm: "lottery.read",
        icon: iconLottery(),
        desc: "Games, packs, and day-close counts.",
      },
      {
        to: "/price-book", label: "Price book",
        roles: ["admin", "employee"],
        flag: "module_price_book", perm: "catalog.read",
        icon: iconPriceBook(),
        desc: "Items, prices, and vendors.",
      },
      {
        to: "/purchase-invoices", label: "Purchases",
        roles: ["admin"],
        flag: "module_price_book", perm: "catalog.read",
        icon: iconInvoice(),
        desc: "Vendor invoices and costs.",
      },
    ],
  },
  {
    // Money services — the MSB module as its own nav section
    // (P1-11): transfers + sender directory + ACH batches live
    // together, and the whole group vanishes when
    // module_money_services is off (filterNavForRole drops groups
    // whose every item filters out), keeping Daily retail-focused.
    title: "Money services",
    icon: iconTransfers(),
    items: [
      {
        to: "/transfers", label: "Transfers",
        flag: "module_money_services",
        roles: ["admin", "employee"],
        perm: "transfers.read",
        icon: iconTransfers(),
        desc: "Log and review money transfers.",
      },
      {
        to: "/customers", label: "Customers",
        flag: "module_money_services",
        roles: ["admin", "employee"],
        perm: "customers.read",
        icon: iconCustomers(),
        desc: "Sender and recipient records.",
      },
      {
        to: "/batches", label: "ACH batches",
        flag: "module_money_services",
        roles: ["admin"],
        perm: "batches.read",
        icon: iconBatches(),
        desc: "Group transfers into ACH runs.",
      },
      {
        // Check cashing is a money service — grouped here (owner
        // directive) but on its own flag: plenty of c-stores cash
        // checks without running transfers, so the group survives
        // on this item alone when module_money_services is off.
        to: "/return-checks", label: "Returned checks",
        flag: "module_check_cashing",
        roles: ["admin", "employee"],
        perm: "return_checks.read",
        icon: iconReturnChecks(),
        desc: "Track bounced checks and recovery.",
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
    title: "Team",
    icon: iconHR(),
    items: [
      {
        to: "/timeclock", label: "Time clock",
        roles: ["admin", "employee"],
        perm: "time_clock.read",
        icon: iconClock(),
        desc: "Clock in and out of shifts.",
      },
      {
        to: "/admin/timeclock", label: "Payroll",
        roles: ["admin"],
        perm: "time_clock.read",
        icon: iconReports(),
        desc: "Shift history and hours worked.",
      },
      {
        to: "/admin/timeclock/schedule", label: "Schedule",
        roles: ["admin"],
        perm: "time_clock.read",
        icon: iconCalendarStar(),
        desc: "Plan upcoming employee shifts.",
      },
      {
        to: "/admin/timeclock/credentials", label: "Punch credentials",
        roles: ["admin"],
        perm: "time_clock.read",
        icon: iconClock(),
        desc: "PINs employees use to punch.",
      },
      {
        to: "/employees", label: "Employees",
        roles: ["admin"],
        perm: "users.read",
        icon: iconCustomers(),
        desc: "Profile, payroll, and login for everyone here.",
      },
      {
        to: "/admin/store-permissions", label: "Permissions",
        roles: ["admin"],
        perm: "settings.read",
        icon: iconShield(),
        desc: "Control what each role can do.",
      },
    ],
  },
  {
    // Reports — a fly-out with the two report centers, kept fully
    // separate (owner directive: MSB and back-office must not
    // blur). Each center lists its own categories; the store
    // center is flag-gated so MSB-profile stores never see it.
    title: "Reports",
    roles: ["admin"],
    icon: iconReports(),
    items: [
      {
        to: "/reports", label: "MSB Reports",
        perm: "reports.read",
        icon: iconTransfers(),
        desc: "Money-services analytics and exports.",
      },
      {
        to: "/store-reports", label: "Store Reports",
        flag: "module_day_close",
        perm: "reports.read",
        icon: iconRegister(),
        desc: "Back-office reports for the storefront.",
      },
    ],
  },
  {
    title: "Finance",
    roles: ["admin"],
    icon: iconBank(),
    items: [
      { to: "/bank",               label: "Bank sync",   perm: "bank_sync.read", icon: iconBank(),    desc: "Connect and reconcile accounts." },
      { to: "/bank-transactions",  label: "Bank transactions",   perm: "bank_sync.read", icon: iconBank(),    desc: "Categorize imported transactions." },
    ],
  },
  {
    // Displays — every customer-facing screen the store runs.
    // TV display (rate board) today; Lottery and Restaurant
    // displays join this group as they ship.
    title: "Displays",
    roles: ["admin"],
    icon: iconDevice(),
    items: [
      {
        to: "/tv-display", label: "TV display",
        icon: iconDevice(),
        desc: "In-store rate board and pairing.",
      },
    ],
  },
  {
    title: "Owner",
    roles: ["owner"],
    icon: iconOwner(),
    items: [
      { to: "/owner/locations",             label: "Locations",             icon: iconOwner(),     desc: "Stores under your umbrella." },
      { to: "/owner/connect",               label: "Connect",               icon: iconBanner(),    desc: "Link a store via invite code." },
      { to: "/owner/users",                 label: "Team users",            icon: iconCustomers(), desc: "People across all locations." },
      { to: "/owner/bulk-add-user",         label: "Add user to stores",         icon: iconOwner(),     desc: "Add one user to many stores." },
      { to: "/owner/cross-store-defaults",  label: "Cross-store defaults",  icon: iconRollup(),    desc: "Shared settings for every store." },
      { to: "/owner/activity",              label: "Activity stream",       icon: iconReports(),   desc: "Recent actions across stores." },
      { to: "/owner/bulk-permissions",      label: "Bulk permissions",      icon: iconSettings(),  desc: "Set roles across all stores." },
      { to: "/owner/billing",               label: "Billing",               icon: iconBilling(),   desc: "Plans and costs for every store." },
      { to: "/owner/settings",              label: "Owner settings",        icon: iconSettings(),  desc: "Your owner account preferences." },
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
      { to: "/owner/pl-rollup",  label: "P&L rollup", icon: iconRollup(),  desc: "Combined P&L for all stores." },
      { to: "/owner/reports",    label: "Reports",    icon: iconReports(), desc: "Cross-store analytics." },
    ],
  },
  {
    title: "Dashboard",
    roles: ["superadmin"],
    icon: iconDashboard(),
    items: [
      { to: "/superadmin/dashboard",     label: "Dashboard",     icon: iconDashboard(), desc: "Platform-wide overview." },
    ],
  },
  {
    // Visible to the tickets-only "support" platform role too —
    // per-item roles below keep everything except Tickets
    // superadmin-only, and filterNavForRole drops the rest.
    title: "Manage",
    roles: ["superadmin", "support"],
    icon: iconPlatform(),
    items: [
      { to: "/superadmin/stores",        label: "Stores",        icon: iconPlatform(),  desc: "Every store on the platform.",   roles: ["superadmin"] },
      { to: "/superadmin/users",         label: "Users",         icon: iconCustomers(), desc: "All accounts across stores.",    roles: ["superadmin"] },
      { to: "/superadmin/tickets",       label: "Tickets",       icon: iconSupport(),   desc: "Support tickets from stores.",   roles: ["superadmin", "support"] },
      { to: "/superadmin/announcements", label: "Announcements", icon: iconBanner(),    desc: "Broadcast banners and emails.",  roles: ["superadmin"] },
      { to: "/superadmin/billing",       label: "Billing",       icon: iconBank(),      desc: "Subscriptions and account credit.", roles: ["superadmin"] },
    ],
  },
  {
    title: "Reports",
    roles: ["superadmin"],
    icon: iconReports(),
    items: [
      { to: "/superadmin/reports",       label: "Reports",       icon: iconReports(), desc: "Platform BI and drilldowns." },
      { to: "/superadmin/audit-log",     label: "Audit log",     icon: iconAudit(),   desc: "Superadmin action history." },
      { to: "/superadmin/email-log",     label: "Email log",     icon: iconBell(),    desc: "Outbound email delivery." },
    ],
  },
  {
    title: "Platform",
    roles: ["superadmin"],
    icon: iconSettings(),
    items: [
      { to: "/superadmin/controls",      label: "Controls",      icon: iconSettings(),    desc: "Global platform switches." },
      { to: "/superadmin/permissions",   label: "Permissions",   icon: iconShield(),      desc: "Default role permission matrix." },
      { to: "/superadmin/feature-flags", label: "Feature flags", icon: iconToggle(),      desc: "Per-store and global toggles." },
      { to: "/superadmin/discounts",     label: "Discounts",     icon: iconBadge(),       desc: "Promo codes and credits." },
      { to: "/superadmin/maintenance",   label: "Maintenance",   icon: iconMaintenance(), desc: "Maintenance mode and banners." },
      { to: "/superadmin/health",        label: "Health",        icon: iconHealth(),      desc: "System status checks." },
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
        desc: "Profile, store info, and theme.",
      },
      {
        to: "/account/notifications", label: "Notifications",
        icon: iconBell(),
        desc: "Choose which emails you receive.",
      },
      {
        to: "/account/activity", label: "My activity",
        icon: iconAudit(),
        desc: "Your recent actions on the account.",
      },
      {
        to: "/account/sessions", label: "Devices",
        icon: iconDevice(),
        desc: "Signed-in devices and sessions.",
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
// render an empty icon-only button) — UNLESS it's a direct-link
// group (`to` set), which is a destination in its own right and
// legitimately carries no sub-items.
export function filterNavForRole(
  role: string,
  permissions: string[] = [],
  // Module flags ON for this store (from /auth/session-status
  // `features`). `undefined` = not loaded yet → show everything,
  // matching the shell's no-flash-while-loading posture for the
  // store gate. Superadmin always sees every module.
  features?: string[],
): NavGroup[] {
  const hasPerm = (p: string) =>
    role === "superadmin" || permissions.includes(p);
  const hasModule = (f: string) =>
    role === "superadmin" || features === undefined || features.includes(f);
  const visible = (i: NavItem) => {
    if (i.roles && !i.roles.includes(role)) return false;
    if (i.perm && !hasPerm(i.perm)) return false;
    if (i.flag && !hasModule(i.flag)) return false;
    return true;
  };
  return NAV
    .filter((g) => !g.roles || g.roles.includes(role))
    .map((g) => ({ ...g, items: g.items.filter(visible) }))
    .filter((g) => g.items.length > 0 || !!g.to);
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
function iconBilling() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M2 10h20" />
      <path d="M6 15h4" />
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

function iconMaintenance() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  );
}
function iconToggle() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="1" y="5" width="22" height="14" rx="7" />
      <circle cx="16" cy="12" r="3" />
    </svg>
  );
}
function iconBadge() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
    </svg>
  );
}
function iconShield() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
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
function iconReceipt() {
  // A paper receipt: torn bottom edge + two lines of print.
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M5 3h14v18l-2.3-1.6L14.4 21l-2.4-1.6L9.6 21l-2.3-1.6L5 21z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
    </svg>
  );
}
function iconRegister() {
  // A cash register / till: drawer base + keypad top.
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <rect x="3" y="13" width="18" height="7" rx="1" />
      <path d="M6 13V8a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v5" />
      <path d="M12 7V4" />
      <path d="M9 4h6" />
      <path d="M7 17h4" />
      <path d="M16 17h1" />
    </svg>
  );
}
function iconInvoice() {
  // A receipt with a ragged bottom edge — the paper invoice.
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M5 3h14v18l-2.5-1.5L14 21l-2-1.5L10 21l-2.5-1.5L5 21z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
    </svg>
  );
}
function iconPriceBook() {
  // A price tag with a barcode — items + prices.
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M20.6 13.4L11 3H4v7l9.6 10.4a2 2 0 0 0 2.8 0l4.2-4.2a2 2 0 0 0 0-2.8z" />
      <path d="M7.5 6.5h.01" />
    </svg>
  );
}
function iconLottery() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round">
      <path d="M3 9V7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 6v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-6z" />
      <path d="M13 5v2" />
      <path d="M13 11v2" />
      <path d="M13 17v2" />
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
