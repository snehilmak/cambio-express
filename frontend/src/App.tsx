import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import AppShell from "./components/AppShell";
import RequireAuth from "./components/RequireAuth";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { Loading, ToastProvider } from "./components/ui";
import Home from "./routes/Home";
import NotFound from "./routes/NotFound";

// Eager: tiny bounce + 404 modules that should be in the entry chunk
// so the first paint never blocks on a network round-trip. Everything
// else is lazy — the bundle splits per-route via Vite's dynamic-import
// handling. Chart.js (~190KB minified) only loads for routes that
// render charts (owner dashboard + superadmin BI drilldowns).

const AccountActivity = lazy(() => import("./routes/AccountActivity"));
const AccountNotifications = lazy(() => import("./routes/AccountNotifications"));
const AccountSessions = lazy(() => import("./routes/AccountSessions"));
const AdminAuditLog = lazy(() => import("./routes/AdminAuditLog"));
const AdminCashiers = lazy(() => import("./routes/AdminCashiers"));
const AdminReferrals = lazy(() => import("./routes/AdminReferrals"));
const AdminSubscription = lazy(() => import("./routes/AdminSubscription"));
const AdminDataExport = lazy(() => import("./routes/AdminDataExport"));
const AdminTaxExport = lazy(() => import("./routes/AdminTaxExport"));
const AdminTimeClock = lazy(() => import("./routes/AdminTimeClock"));
const AdminTimeClockCredentials = lazy(
  () => import("./routes/AdminTimeClockCredentials"),
);
const AdminTimeClockSchedule = lazy(
  () => import("./routes/AdminTimeClockSchedule"),
);
const AdminUserForm = lazy(() => import("./routes/AdminUserForm"));
const AdminUsers = lazy(() => import("./routes/AdminUsers"));
const Bank = lazy(() => import("./routes/Bank"));
const BankRules = lazy(() => import("./routes/BankRules"));
const BankTransactions = lazy(() => import("./routes/BankTransactions"));
const Batches = lazy(() => import("./routes/Batches"));
const BatchForm = lazy(() => import("./routes/BatchForm"));
const Customers = lazy(() => import("./routes/Customers"));
const DailyBook = lazy(() => import("./routes/DailyBook"));
const Dashboard = lazy(() => import("./routes/Dashboard"));
const HomeHub = lazy(() => import("./routes/HomeHub"));
const EditDailyBook = lazy(() => import("./routes/EditDailyBook"));
const EditMonthly = lazy(() => import("./routes/EditMonthly"));
const EditTransfer = lazy(() => import("./routes/EditTransfer"));
const ForgotPassword = lazy(() => import("./routes/ForgotPassword"));
const Login = lazy(() => import("./routes/Login"));
const LoginStore = lazy(() => import("./routes/LoginStore"));
const Monthly = lazy(() => import("./routes/Monthly"));
const NewTransfer = lazy(() => import("./routes/NewTransfer"));
const OwnerBulkAddUser = lazy(() => import("./routes/OwnerBulkAddUser"));
const OwnerCrossStoreDefaults = lazy(
  () => import("./routes/OwnerCrossStoreDefaults"),
);
const OwnerConnect = lazy(() => import("./routes/OwnerConnect"));
const OwnerDashboard = lazy(() => import("./routes/OwnerDashboard"));
const OwnerLocations = lazy(() => import("./routes/OwnerLocations"));
const OwnerPLRollup = lazy(() => import("./routes/OwnerPLRollup"));
const OwnerReports = lazy(() => import("./routes/OwnerReports"));
const OwnerStoreDetail = lazy(() => import("./routes/OwnerStoreDetail"));
const Privacy = lazy(() => import("./routes/Privacy"));
const Reports = lazy(() => import("./routes/Reports"));
const ResetPassword = lazy(() => import("./routes/ResetPassword"));
const ReturnCheckForm = lazy(() => import("./routes/ReturnCheckForm"));
const ReturnChecks = lazy(() => import("./routes/ReturnChecks"));
const Settings = lazy(() => import("./routes/Settings"));
const SettingsProfile = lazy(
  () => import("./routes/Settings").then(
    (m) => ({ default: m.SettingsProfile }),
  ),
);
const SettingsGeneral = lazy(
  () => import("./routes/Settings").then(
    (m) => ({ default: m.SettingsGeneral }),
  ),
);
const SettingsBilling = lazy(
  () => import("./routes/Settings").then(
    (m) => ({ default: m.SettingsBilling }),
  ),
);
const SettingsSecurity = lazy(
  () => import("./routes/Settings").then(
    (m) => ({ default: m.SettingsSecurity }),
  ),
);
const Signup = lazy(() => import("./routes/Signup"));
const SignupOwner = lazy(() => import("./routes/SignupOwner"));
const Subscribe = lazy(() => import("./routes/Subscribe"));
const SubscribeSuccess = lazy(() => import("./routes/SubscribeSuccess"));
const SuperadminAnnouncements = lazy(() => import("./routes/SuperadminAnnouncements"));
const SuperadminAuditLog = lazy(() => import("./routes/SuperadminAuditLog"));
const SuperadminControls = lazy(() => import("./routes/SuperadminControls"));
const SuperadminReports = lazy(() => import("./routes/SuperadminReports"));
const SuperadminStoreForm = lazy(() => import("./routes/SuperadminStoreForm"));
const SuperadminStores = lazy(() => import("./routes/SuperadminStores"));
const TimeClock = lazy(() => import("./routes/TimeClock"));
const TimeClockPaystub = lazy(() => import("./routes/TimeClockPaystub"));
const TransferDetail = lazy(() => import("./routes/TransferDetail"));
// Receipt printing surface is hidden until we decide we need it —
// this is a ledger-only product, so customer-facing receipts don't
// belong here. The route + backend stay in place so re-enabling is
// a one-line revert. Import kept as a side-effect-free reference so
// the lazy chunk gets tree-shaken out of the build.
// const TransferReceipt = lazy(() => import("./routes/TransferReceipt"));
const Transfers = lazy(() => import("./routes/Transfers"));
const TVDisplayAdmin = lazy(() => import("./routes/TVDisplayAdmin"));
const TVDisplayOverview = lazy(
  () => import("./routes/TVDisplayAdmin").then(
    (m) => ({ default: m.TVDisplayOverview }),
  ),
);
const TVDisplayContent = lazy(
  () => import("./routes/TVDisplayAdmin").then(
    (m) => ({ default: m.TVDisplayContent }),
  ),
);
const TVDisplayDevice = lazy(
  () => import("./routes/TVDisplayAdmin").then(
    (m) => ({ default: m.TVDisplayDevice }),
  ),
);
const TVDisplayCountry = lazy(() => import("./routes/TVDisplayCountry"));

// TwoFactor.tsx exports three named components from one file. They share
// a 2FA chrome bundle, so co-locating them in the same chunk is correct;
// we unwrap the named exports into default-shaped lazy promises.
const TwoFactorEnroll = lazy(() =>
  import("./routes/TwoFactor").then((m) => ({ default: m.TwoFactorEnroll })),
);
const TwoFactorRecover = lazy(() =>
  import("./routes/TwoFactor").then((m) => ({ default: m.TwoFactorRecover })),
);
const TwoFactorVerify = lazy(() =>
  import("./routes/TwoFactor").then((m) => ({ default: m.TwoFactorVerify })),
);

// Reports.
const AchVolume = lazy(() => import("./routes/reports/AchVolume"));
const BankChargesByAccount = lazy(() => import("./routes/reports/BankChargesByAccount"));
const BankRuleAudit = lazy(() => import("./routes/reports/BankRuleAudit"));
const BankTxnBreakdown = lazy(() => import("./routes/reports/BankTxnBreakdown"));
const ByDestinationCountry = lazy(() => import("./routes/reports/ByDestinationCountry"));
const CancelledTransfers = lazy(() => import("./routes/reports/CancelledTransfers"));
const CashierProductivity = lazy(() => import("./routes/reports/CashierProductivity"));
const CheckDeposits = lazy(() => import("./routes/reports/CheckDeposits"));
const DailyDrops = lazy(() => import("./routes/reports/DailyDrops"));
const EmployeeActivity = lazy(() => import("./routes/reports/EmployeeActivity"));
const FeesVsTax = lazy(() => import("./routes/reports/FeesVsTax"));
const HighValueTransfers = lazy(() => import("./routes/reports/HighValueTransfers"));
const NewVsReturning = lazy(() => import("./routes/reports/NewVsReturning"));
const PeriodComparison = lazy(() => import("./routes/reports/PeriodComparison"));
const PeriodPL = lazy(() => import("./routes/reports/PeriodPL"));
const ReturnedCheckStatus = lazy(() => import("./routes/reports/ReturnedCheckStatus"));
const SalesByCompany = lazy(() => import("./routes/reports/SalesByCompany"));
const SalesByEmployee = lazy(() => import("./routes/reports/SalesByEmployee"));
const SalesByService = lazy(() => import("./routes/reports/SalesByService"));
const SuperadminBIDrilldown = lazy(() => import("./routes/reports/SuperadminBIDrilldown"));
const TopCustomers = lazy(() => import("./routes/reports/TopCustomers"));
const TopRecipients = lazy(() => import("./routes/reports/TopRecipients"));
const TopSenders = lazy(() => import("./routes/reports/TopSenders"));

// Top-level routing for the SPA.
//
//   /              → bounces to /login or /dashboard
//   /login         → unauthed-only login form (no shell)
//   <AuthedShell>  → applies RequireAuth + AppShell (sidebar +
//                     topbar) to every nested route
//     /dashboard, /transfers, /transfers/:id, /customers,
//     /daily, /reports
//
// Adding a new authed screen = adding one nested <Route> under
// the AuthedShell layout — no need to repeat RequireAuth +
// AppShell wrappers per page.
//
// Every <Route> element is a lazy() chunk; the global <Suspense>
// boundary below renders <Loading /> during the chunk fetch. Per-
// route error boundaries are tracked separately as BACKLOG C4.
export default function App() {
  return (
    <RouteErrorBoundary routeName="spa-root">
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route index element={<Home />} />
        <Route path="login"               element={<Login />} />
        <Route path="login/2fa"           element={<TwoFactorVerify />} />
        <Route path="login/2fa/enroll"    element={<TwoFactorEnroll />} />
        <Route path="login/2fa/recover"   element={<TwoFactorRecover />} />
        <Route path="login/:slug"         element={<LoginStore />} />
        <Route path="signup"           element={<Signup />} />
        <Route path="signup/owner"     element={<SignupOwner />} />
        <Route path="forgot-password"  element={<ForgotPassword />} />
        <Route path="reset-password"   element={<ResetPassword />} />
        <Route path="privacy"          element={<Privacy />} />
        <Route element={<AuthedShell />}>
          <Route path="home"             element={<HomeHub />} />
          <Route path="dashboard"        element={<Dashboard />} />
          <Route path="transfers"        element={<Transfers />} />
          <Route path="transfers/new"      element={<NewTransfer />} />
          <Route path="transfers/:id"         element={<TransferDetail />} />
          <Route path="transfers/:id/edit"    element={<EditTransfer />} />
          {/* Receipt printing surface hidden — see lazy-import comment above. */}
          <Route path="customers"        element={<Customers />} />
          <Route path="daily"            element={<DailyBook />} />
          <Route path="daily/edit"       element={<EditDailyBook />} />
          <Route path="reports"          element={<Reports />} />
          <Route path="reports/sales-by-company"      element={<SalesByCompany />} />
          <Route path="reports/sales-by-service-type" element={<SalesByService />} />
          <Route path="reports/sales-by-employee"     element={<SalesByEmployee />} />
          <Route path="reports/cashier-productivity"  element={<CashierProductivity />} />
          <Route path="reports/top-customers"   element={<TopCustomers />} />
          <Route path="reports/top-senders"     element={<TopSenders />} />
          <Route path="reports/top-recipients"  element={<TopRecipients />} />
          <Route path="reports/new-vs-returning"       element={<NewVsReturning />} />
          <Route path="reports/by-destination-country" element={<ByDestinationCountry />} />
          <Route path="reports/fees-vs-tax"            element={<FeesVsTax />} />
          <Route path="reports/high-value-transfers"   element={<HighValueTransfers />} />
          <Route path="reports/cancelled-transfers"    element={<CancelledTransfers />} />
          <Route path="reports/ach-volume"             element={<AchVolume />} />
          <Route path="reports/returned-check-status"       element={<ReturnedCheckStatus />} />
          <Route path="reports/bank-transactions-breakdown" element={<BankTxnBreakdown />} />
          <Route path="reports/daily-drops"                 element={<DailyDrops />} />
          <Route path="reports/check-deposits"              element={<CheckDeposits />} />
          <Route path="reports/bank-rule-audit"             element={<BankRuleAudit />} />
          <Route path="reports/bank-charges-by-account"     element={<BankChargesByAccount />} />
          <Route path="reports/period-comparison"           element={<PeriodComparison />} />
          <Route path="reports/employee-activity"           element={<EmployeeActivity />} />
          <Route path="reports/period-pl"                   element={<PeriodPL />} />
          <Route path="superadmin/reports/:slug"            element={<SuperadminBIDrilldown />} />
          <Route path="owner/reports/sales-by-company"      element={<SalesByCompany />} />
          <Route path="owner/reports/sales-by-service-type" element={<SalesByService />} />
          <Route path="owner/reports/sales-by-employee"     element={<SalesByEmployee />} />
          <Route path="owner/reports/cashier-productivity"  element={<CashierProductivity />} />
          <Route path="owner/reports/top-customers"  element={<TopCustomers />} />
          <Route path="owner/reports/top-senders"    element={<TopSenders />} />
          <Route path="owner/reports/top-recipients"        element={<TopRecipients />} />
          <Route path="owner/reports/new-vs-returning"       element={<NewVsReturning />} />
          <Route path="owner/reports/by-destination-country" element={<ByDestinationCountry />} />
          <Route path="owner/reports/fees-vs-tax"            element={<FeesVsTax />} />
          <Route path="owner/reports/high-value-transfers"   element={<HighValueTransfers />} />
          <Route path="owner/reports/cancelled-transfers"    element={<CancelledTransfers />} />
          <Route path="owner/reports/ach-volume"             element={<AchVolume />} />
          <Route path="owner/reports/returned-check-status"       element={<ReturnedCheckStatus />} />
          <Route path="owner/reports/bank-transactions-breakdown" element={<BankTxnBreakdown />} />
          <Route path="owner/reports/daily-drops"                 element={<DailyDrops />} />
          <Route path="owner/reports/check-deposits"              element={<CheckDeposits />} />
          <Route path="owner/reports/bank-rule-audit"             element={<BankRuleAudit />} />
          <Route path="owner/reports/bank-charges-by-account"     element={<BankChargesByAccount />} />
          <Route path="owner/reports/period-comparison"           element={<PeriodComparison />} />
          <Route path="owner/reports/employee-activity"           element={<EmployeeActivity />} />
          <Route path="owner/reports/period-pl"                   element={<PeriodPL />} />
          <Route path="batches"          element={<Batches />} />
          <Route path="batches/new"      element={<BatchForm />} />
          <Route path="batches/:id/edit" element={<BatchForm />} />
          <Route path="bank"             element={<Bank />} />
          <Route path="bank/rules"       element={<BankRules />} />
          <Route path="bank-transactions" element={<BankTransactions />} />
          <Route path="monthly"          element={<Monthly />} />
          <Route path="monthly/edit"     element={<EditMonthly />} />
          <Route path="return-checks"          element={<ReturnChecks />} />
          <Route path="return-checks/new"      element={<ReturnCheckForm />} />
          <Route path="return-checks/:id/edit" element={<ReturnCheckForm />} />
          <Route path="owner/connect"        element={<OwnerConnect />} />
          <Route path="owner/dashboard"      element={<OwnerDashboard />} />
          <Route path="owner/locations"      element={<OwnerLocations />} />
          <Route path="owner/pl-rollup"      element={<OwnerPLRollup />} />
          <Route path="owner/reports"        element={<OwnerReports />} />
          <Route path="owner/bulk-add-user"          element={<OwnerBulkAddUser />} />
          <Route path="owner/cross-store-defaults"   element={<OwnerCrossStoreDefaults />} />
          <Route path="owner/store/:storeId" element={<OwnerStoreDetail />} />
          <Route path="superadmin/stores"        element={<SuperadminStores />} />
          <Route path="superadmin/stores/new"    element={<SuperadminStoreForm />} />
          <Route path="superadmin/stores/:id/edit" element={<SuperadminStoreForm />} />
          <Route path="superadmin/audit-log"     element={<SuperadminAuditLog />} />
          <Route path="superadmin/announcements" element={<SuperadminAnnouncements />} />
          <Route path="superadmin/controls"      element={<SuperadminControls />} />
          <Route path="superadmin/reports"       element={<SuperadminReports />} />
          <Route path="subscribe"             element={<Subscribe />} />
          <Route path="subscribe/success"     element={<SubscribeSuccess />} />
          <Route path="admin/subscription"    element={<AdminSubscription />} />
          <Route path="admin/data-export"     element={<AdminDataExport />} />
          <Route path="admin/tax-export"      element={<AdminTaxExport />} />
          <Route path="admin/timeclock"               element={<AdminTimeClock />} />
          <Route path="admin/timeclock/credentials"   element={<AdminTimeClockCredentials />} />
          <Route path="admin/timeclock/schedule"      element={<AdminTimeClockSchedule />} />
          <Route path="admin/timeclock/paystub/:id"   element={<TimeClockPaystub />} />
          <Route path="admin/audit-log"       element={<AdminAuditLog />} />
          <Route path="admin/users"             element={<AdminUsers />} />
          <Route path="admin/users/new"         element={<AdminUserForm />} />
          <Route path="admin/users/:uid/edit"   element={<AdminUserForm />} />
          {/* Cashier roster — lifted out of the /settings/team tab
              when HR became its own sidebar group.  The old URL
              redirects below for bookmarks. */}
          <Route path="admin/cashiers"          element={<AdminCashiers />} />
          <Route path="timeclock"             element={<TimeClock />} />
          <Route path="account/referrals"     element={<AdminReferrals />} />
          {/* Legacy /account/profile — profile is now the first
              tab inside /settings (see the consolidation that
              moved the standalone page into Settings).  Keep a
              redirect for bookmarks + the rare deep link. */}
          <Route path="account/profile"       element={<Navigate to="/settings/profile" replace />} />
          <Route path="account/notifications" element={<AccountNotifications />} />
          <Route path="account/activity"      element={<AccountActivity />} />
          <Route path="account/sessions"      element={<AccountSessions />} />
          <Route path="tv-display" element={<TVDisplayAdmin />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<TVDisplayOverview />} />
            <Route path="content" element={<TVDisplayContent />} />
            <Route path="device" element={<TVDisplayDevice />} />
          </Route>
          <Route path="tv-display/countries/:countryId" element={<TVDisplayCountry />} />
          <Route path="settings" element={<Settings />}>
            {/* Profile is the first tab — landing on /settings
                with no sub-path drops you into Profile so you
                see "your stuff" first, not the store-wide
                General tab.  /account/profile redirects here
                for back-compat. */}
            <Route index element={<Navigate to="profile" replace />} />
            <Route path="profile" element={<SettingsProfile />} />
            <Route path="general" element={<SettingsGeneral />} />
            {/* Legacy /settings/team — cashier roster moved to
                /admin/cashiers when HR became its own sidebar
                section.  Keep a redirect for bookmarks. */}
            <Route path="team" element={<Navigate to="/admin/cashiers" replace />} />
            <Route path="billing" element={<SettingsBilling />} />
            <Route path="security" element={<SettingsSecurity />} />
          </Route>
          {/* Authed catch-all keeps the AppShell chrome around the 404
              so a stray click doesn't make the user think they got
              signed out (the old top-level catch-all rendered NotFound
              outside the shell, which strips the sidebar + topbar). */}
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
    </RouteErrorBoundary>
  );
}

// Layout route. Bounces unauthed users to /login (RequireAuth)
// and wraps the authed page in the sidebar + topbar shell.
// `<Outlet />` renders the matched child route inside.
function AuthedShell() {
  return (
    <RequireAuth>
      {/* ToastProvider mounts inside RequireAuth so the toast
          region only renders for signed-in users (the marketing
          landing + auth pages don't need it). */}
      <ToastProvider>
        <AppShell>
          {/* Inner boundary keeps the shell intact when a single
              route crashes — sidebar + topbar stay, only the
              content column shows the fallback. */}
          <RouteErrorBoundary routeName="authed-route">
            <Outlet />
          </RouteErrorBoundary>
        </AppShell>
      </ToastProvider>
    </RequireAuth>
  );
}
