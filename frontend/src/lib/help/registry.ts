// Hand-authored Q&A registry for the help center.
//
// Each entry is a tuple of:
//   - ``title``     — what the user sees in the result list
//   - ``keywords``  — extra search-only terms (synonyms,
//                     legacy names) so "MT" finds "money
//                     transfer" and "p&l" finds "monthly P&L"
//   - ``body``      — short HTML answer.  Plain text + optional
//                     ``<code>`` / ``<p>`` allowed; the search
//                     panel renders ``<div dangerouslySetInnerHTML>``
//                     on this string.
//   - ``deepLink``  — optional ``{ label, to }`` that renders as
//                     a "Take me there →" link inside the
//                     answer card.
//   - ``weight``    — relative priority for the empty-query
//                     fallback ordering (higher = surfaces
//                     first on first open).
//
// Keep entries short.  Three-to-five sentences max — the panel
// is for "remind me", not a manual.  Each new feature ships
// with at least one entry in this file so the help center stays
// fresh.  Authoritative source for "how do I X" questions
// across the SPA.

export interface HelpEntry {
  /** Short headline.  Title-case, no trailing punctuation. */
  title:    string;
  /** Plain-text bag of synonyms / aliases.  Search uses this in
   *  addition to ``title`` and ``body`` text so "MT" can route
   *  to "money transfer" and "over short" to "over/short". */
  keywords: string;
  /** Inline HTML body.  Constrained to ``<p>``, ``<code>``,
   *  ``<strong>``, ``<em>``.  No external links — use
   *  ``deepLink`` for the in-app jump. */
  body:     string;
  /** Optional deep-link to the relevant SPA route. */
  deepLink?: { label: string; to: string };
  /** Empty-query fallback priority (higher → earlier). */
  weight?:  number;
}


export const HELP_REGISTRY: readonly HelpEntry[] = [
  // ── Daily workflow ──────────────────────────────────────
  {
    title: "Log a new transfer",
    keywords: "transfer money send wire mt intermex maxi barri remittance",
    body:
      "<p>Open Transfers → click <strong>+ New Transfer</strong>. "
      + "Pick the company (Intermex / Maxi / Barri), enter the send "
      + "amount, customer info, and recipient details. The fee + "
      + "federal tax compute automatically based on the store's "
      + "settings.</p>",
    deepLink: { label: "Open transfers", to: "/transfers" },
    weight: 10,
  },
  {
    title: "Edit an existing transfer",
    keywords: "edit fix change correct transfer mistake",
    body:
      "<p>From the Transfers list, click any row to open it, then "
      + "tap <strong>Edit</strong>. Edits are audited — the change "
      + "history appears below the form for any admin to review.</p>",
    deepLink: { label: "Open transfers", to: "/transfers" },
  },
  {
    title: "Cancel a transfer",
    keywords: "cancel void reject undo refund transfer",
    body:
      "<p>Open the transfer's detail page and use the Cancel action "
      + "in the row actions menu. Cancellation reason is required "
      + "and goes into the audit log. Once cancelled the transfer "
      + "is excluded from the ACH batch totals.</p>",
  },
  {
    title: "What does over/short mean?",
    keywords: "over short variance balance close out drawer cash",
    body:
      "<p><strong>Over/short</strong> is the difference between "
      + "what the day's transactions say should be in the drawer "
      + "and what's actually there at close-out. A positive number "
      + "is over (too much cash); negative is short (missing cash). "
      + "It rolls into the daily book's totals row.</p>",
    deepLink: { label: "Open daily book", to: "/daily" },
  },
  {
    title: "Lock a daily book",
    keywords: "lock close out close-out daily book day end",
    body:
      "<p>From the daily book page, click <strong>Lock day</strong> "
      + "once the over/short is reconciled. Once locked the row's "
      + "monetary fields go read-only, the locked-day digest emails "
      + "fire, and the date counts toward monthly P&L.</p>",
    deepLink: { label: "Open daily book", to: "/daily" },
  },

  // ── Reports & money ─────────────────────────────────────
  {
    title: "View monthly P&L",
    keywords: "monthly profit loss p&l pnl income statement report",
    body:
      "<p>Monthly P&L pulls revenue from every transfer + daily "
      + "book line and subtracts expenses (cash purchases, payroll, "
      + "bank charges, etc.). Bank charges in the 210 / 230 "
      + "accounts auto-feed from bank sync; the rest is operator-"
      + "entered.</p>",
    deepLink: { label: "Open monthly P&L", to: "/monthly" },
  },
  {
    title: "What's the difference between fee and federal tax?",
    keywords: "fee federal tax irs commission revenue",
    body:
      "<p><strong>Fee</strong> is store revenue — what the customer "
      + "pays you to send the transfer. <strong>Federal tax</strong> "
      + "is the IRS levy on money sent abroad, which leaves with "
      + "the ACH withdrawal and never belongs to the store. The "
      + "total collected at the counter = send amount + fee + "
      + "federal tax.</p>",
  },
  {
    title: "ACH batch reconciliation",
    keywords: "ach batch reconcile bank deposit pull transfers",
    body:
      "<p>An ACH batch groups transfers the company will withdraw "
      + "in one go. The batch total = sum of (send amount + federal "
      + "tax) — the store fee stays with the store. The Variance "
      + "column flags drift between the company's ACH amount and "
      + "your tracked total.</p>",
    deepLink: { label: "Open ACH batches", to: "/batches" },
  },

  // ── Time clock ─────────────────────────────────────────
  {
    title: "Clock in or out",
    keywords: "time clock punch shift hours payroll",
    body:
      "<p>Open Time clock, pick your roster name from the "
      + "dropdown, then click <strong>Clock in</strong>. To end "
      + "the shift, pick the same name and click "
      + "<strong>Clock out</strong>. Notes are optional but "
      + "encouraged — they survive in the audit log.</p>",
    deepLink: { label: "Open time clock", to: "/timeclock" },
    weight: 8,
  },
  {
    title: "Schedule a shift",
    keywords: "schedule shift plan roster weekly calendar",
    body:
      "<p>Open Schedule (under Finance), pick the week, then click "
      + "<strong>+ Add shift</strong> on the day you want. "
      + "Scheduled shifts power the late-arrival pill and the "
      + "missed-shift digest — neither fires for unscheduled "
      + "punches.</p>",
    deepLink: { label: "Open schedule", to: "/admin/timeclock/schedule" },
  },
  {
    title: "Why is my cashier showing 'Late'?",
    keywords: "late tardy minutes pill payroll",
    body:
      "<p>A clock-in is flagged Late when it lags the planned "
      + "shift's start time by more than the store's threshold "
      + "(default 5 minutes). Adjust the threshold under Settings "
      + "→ Time clock if 5 is too strict for your storefront.</p>",
    deepLink: { label: "Open settings", to: "/settings" },
  },
  {
    title: "Anti-buddy-punching (passkey + geofence)",
    keywords: "buddy punch passkey webauthn geofence location anti-fraud",
    body:
      "<p>Two opt-in gates on Settings → Time clock prevent "
      + "cashier A from punching for cashier B: the "
      + "<strong>passkey</strong> gate makes every punch require "
      + "a fresh Windows Hello / Touch ID prompt against the "
      + "cashier's registered device; the <strong>geofence</strong> "
      + "gate refuses punches outside the store's GPS radius.</p>",
    deepLink: { label: "Open settings", to: "/settings" },
  },
  {
    title: "Enroll a cashier's passkey",
    keywords: "passkey enrollment register fingerprint face id",
    body:
      "<p>Open Finance → Punch credentials, pick the cashier from "
      + "the dropdown, then click <strong>Register</strong>. The "
      + "browser will prompt for Touch ID / Windows Hello / a "
      + "security key. One passkey per cashier — re-register to "
      + "swap devices.</p>",
    deepLink: {
      label: "Open punch credentials",
      to: "/admin/timeclock/credentials",
    },
  },

  // ── Customers / data ───────────────────────────────────
  {
    title: "Find or add a customer",
    keywords: "customer sender add lookup phone search",
    body:
      "<p>On the New Transfer form, start typing the sender's name "
      + "or phone. Matches across every store the owner runs "
      + "(\"sibling stores\"), so a repeat sender at Store A "
      + "auto-populates at Store B. New customers get created "
      + "automatically when the form is saved.</p>",
    deepLink: { label: "Open customers", to: "/customers" },
  },
  {
    title: "Export transfers to CSV",
    keywords: "csv export download tax report transfer data",
    body:
      "<p>Go to Reports → pick the report you want, set the date "
      + "range, then click <strong>Download CSV</strong>. The same "
      + "endpoint works under <code>/owner/reports/*</code> for "
      + "multi-store owners.</p>",
    deepLink: { label: "Open reports", to: "/reports" },
  },
  {
    title: "Tax export (yearly)",
    keywords: "tax export 1099 year end statement irs annual",
    body:
      "<p>Settings → Data export → pick a year. Generates a "
      + "single zip per store with every transfer, daily book "
      + "line, and monthly P&L for the year. Useful for the "
      + "accountant at year-end.</p>",
    deepLink: { label: "Open data export", to: "/admin/data-export" },
  },

  // ── Notifications ──────────────────────────────────────
  {
    title: "Enable browser notifications",
    keywords: "push notification browser enable subscribe alerts",
    body:
      "<p>Open Account → Notifications → click <strong>Enable "
      + "browser notifications</strong>. Allow the permission "
      + "prompt. After that, platform announcements + future "
      + "delivery alerts will surface as system notifications "
      + "while the browser is closed.</p>",
    deepLink: { label: "Open notifications", to: "/account/notifications" },
  },
  {
    title: "Turn off a specific email",
    keywords: "email opt out unsubscribe stop notification settings",
    body:
      "<p>Account → Notifications has a 2-column matrix per "
      + "notification kind (Email | Push). Uncheck the column you "
      + "want to silence for that kind. Trial reminders, "
      + "announcements, daily summary, and locked-day digest all "
      + "toggle independently.</p>",
    deepLink: { label: "Open notifications", to: "/account/notifications" },
  },

  // ── Admin / account ────────────────────────────────────
  {
    title: "Add a user to your store",
    keywords: "user add admin employee team invite",
    body:
      "<p>Settings → Users → <strong>+ Add user</strong>. Pick "
      + "the role (admin or employee), set a password. Admins see "
      + "everything; employees see Daily + Time clock only.</p>",
    deepLink: { label: "Open users", to: "/admin/users" },
  },
  {
    title: "Switch between light and dark mode",
    keywords: "theme dark light color mode appearance",
    body:
      "<p>Click the sun/moon icon in the topbar. The choice "
      + "syncs to your account so other browsers pick up the "
      + "same theme next time you sign in.</p>",
  },
  {
    title: "Install the app on my phone or desktop",
    keywords: "pwa install app standalone home screen mobile",
    body:
      "<p>Click <strong>Install app</strong> in the topbar (only "
      + "appears when your browser supports PWA install — Chrome, "
      + "Edge, Brave on desktop + Android). On iOS Safari, use "
      + "the Share menu → Add to Home Screen.</p>",
  },
  {
    title: "Reset my password",
    keywords: "password forgot reset email recover lost login",
    body:
      "<p>From the login page, click <strong>Forgot password?</strong> "
      + "and enter the email on your account. You'll get a one-"
      + "time link valid for an hour. Superadmin accounts can't "
      + "reset by email — that's a deliberate security choice; "
      + "run <code>python -m scripts.reset_superadmin</code> on the "
      + "Render shell instead.</p>",
  },
  {
    title: "What's the dashboard?",
    keywords: "home dashboard landing",
    body:
      "<p>The dashboard is the first page you see after sign-in. "
      + "It shows today's store activity at a glance — transfers, "
      + "daily book status, and recent activity.</p>",
    deepLink: { label: "Open dashboard", to: "/dashboard" },
  },

  // ── Billing / plans ────────────────────────────────────
  {
    title: "Upgrade my plan",
    keywords: "plan upgrade subscribe basic pro stripe billing",
    body:
      "<p>Settings → Subscription → pick a plan and click "
      + "<strong>Subscribe</strong>. We use Stripe Checkout for "
      + "the hosted flow. Coupon / referral codes go in the "
      + "Stripe page if you have one.</p>",
    deepLink: { label: "Open subscription", to: "/admin/subscription" },
  },
  {
    title: "What happens when my trial ends?",
    keywords: "trial expire end grace period data retention plan",
    body:
      "<p>You get a 7-day trial, then a 4-day grace period where "
      + "the books go read-only but the data stays. Subscribe "
      + "within the grace window to flip the books back to fully "
      + "editable. After grace ends, data is purged after 180 days "
      + "if no subscription is started.</p>",
  },
];
