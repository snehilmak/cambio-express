import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import AppShell from "./components/AppShell";
import RequireAuth from "./components/RequireAuth";
import RequirePermission from "./components/RequirePermission";
import RequireRole from "./components/RequireRole";
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
const AdminSubscription = lazy(() => import("./routes/AdminSubscription"));
const AdminDataExport = lazy(() => import("./routes/AdminDataExport"));
const SupportTickets = lazy(() => import("./routes/SupportTickets"));
const SuperadminTickets = lazy(() => import("./routes/SuperadminTickets"));
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
const OwnerUsers = lazy(() => import("./routes/OwnerUsers"));
const OwnerStorePermissions = lazy(
  () => import("./routes/OwnerStorePermissions"),
);
const OwnerSettings = lazy(() => import("./routes/OwnerSettings"));
const OwnerActivity = lazy(() => import("./routes/OwnerActivity"));
const OwnerBulkPermissions = lazy(
  () => import("./routes/OwnerBulkPermissions"),
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
const SectionHub = lazy(() => import("./routes/SectionHub"));
const Settings = lazy(() => import("./routes/Settings"));
const StorePermissions = lazy(() => import("./routes/StorePermissions"));
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
const SettingsReferrals = lazy(() => import("./routes/AdminReferrals"));
const Signup = lazy(() => import("./routes/Signup"));
const SignupOwner = lazy(() => import("./routes/SignupOwner"));
const Subscribe = lazy(() => import("./routes/Subscribe"));
const SubscribeSuccess = lazy(() => import("./routes/SubscribeSuccess"));
const SuperadminAnnouncements = lazy(() => import("./routes/SuperadminAnnouncements"));
const SuperadminAuditLog = lazy(() => import("./routes/SuperadminAuditLog"));
const SuperadminControls = lazy(() => import("./routes/SuperadminControls"));
const SuperadminDashboard = lazy(() => import("./routes/SuperadminDashboard"));
const SuperadminDiscounts = lazy(() => import("./routes/SuperadminDiscounts"));
const SuperadminFeatureFlags = lazy(() => import("./routes/SuperadminFeatureFlags"));
const SuperadminBilling = lazy(() => import("./routes/SuperadminBilling"));
const SuperadminEmailLog = lazy(() => import("./routes/SuperadminEmailLog"));
const SuperadminHealth = lazy(() => import("./routes/SuperadminHealth"));
const SuperadminMaintenance = lazy(() => import("./routes/SuperadminMaintenance"));
const SuperadminStoreDrill = lazy(() => import("./routes/SuperadminStoreDrill"));
const SuperadminPermissions = lazy(() => import("./routes/SuperadminPermissions"));
const SuperadminReports = lazy(() => import("./routes/SuperadminReports"));
const SuperadminStoreForm = lazy(() => import("./routes/SuperadminStoreForm"));
const SuperadminStores = lazy(() => import("./routes/SuperadminStores"));
const SuperadminUsers = lazy(() => import("./routes/SuperadminUsers"));
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
          <Route path="home"             element={<Navigate to="/dashboard" replace />} />
          {/* Section-hub tile landings — one per nav section, driven
              by the same role-filtered NAV the sidebar uses. */}
          <Route path="hub/:key"         element={<SectionHub />} />
          <Route path="dashboard"        element={<Dashboard />} />
          <Route path="transfers"        element={<RequirePermission resource="transfers" action="read"><Transfers /></RequirePermission>} />
          <Route path="transfers/new"      element={<RequirePermission resource="transfers" action="create"><NewTransfer /></RequirePermission>} />
          <Route path="transfers/:id"         element={<RequirePermission resource="transfers" action="read"><TransferDetail /></RequirePermission>} />
          <Route path="transfers/:id/edit"    element={<RequirePermission resource="transfers" action="update"><EditTransfer /></RequirePermission>} />
          {/* Receipt printing surface hidden — see lazy-import comment above. */}
          <Route path="customers"        element={<RequirePermission resource="customers" action="read"><Customers /></RequirePermission>} />
          <Route path="daily"            element={<RequirePermission resource="daily_book" action="read"><DailyBook /></RequirePermission>} />
          <Route path="daily/edit"       element={<RequirePermission resource="daily_book" action="update"><EditDailyBook /></RequirePermission>} />
          <Route path="reports"          element={<RequirePermission resource="reports" action="read"><Reports /></RequirePermission>} />
          <Route path="reports/sales-by-company"      element={<RequirePermission resource="reports" action="read"><SalesByCompany /></RequirePermission>} />
          <Route path="reports/sales-by-service-type" element={<RequirePermission resource="reports" action="read"><SalesByService /></RequirePermission>} />
          <Route path="reports/sales-by-employee"     element={<RequirePermission resource="reports" action="read"><SalesByEmployee /></RequirePermission>} />
          <Route path="reports/cashier-productivity"  element={<RequirePermission resource="reports" action="read"><CashierProductivity /></RequirePermission>} />
          <Route path="reports/top-customers"   element={<RequirePermission resource="reports" action="read"><TopCustomers /></RequirePermission>} />
          <Route path="reports/top-senders"     element={<RequirePermission resource="reports" action="read"><TopSenders /></RequirePermission>} />
          <Route path="reports/top-recipients"  element={<RequirePermission resource="reports" action="read"><TopRecipients /></RequirePermission>} />
          <Route path="reports/new-vs-returning"       element={<RequirePermission resource="reports" action="read"><NewVsReturning /></RequirePermission>} />
          <Route path="reports/by-destination-country" element={<RequirePermission resource="reports" action="read"><ByDestinationCountry /></RequirePermission>} />
          <Route path="reports/fees-vs-tax"            element={<RequirePermission resource="reports" action="read"><FeesVsTax /></RequirePermission>} />
          <Route path="reports/high-value-transfers"   element={<RequirePermission resource="reports" action="read"><HighValueTransfers /></RequirePermission>} />
          <Route path="reports/cancelled-transfers"    element={<RequirePermission resource="reports" action="read"><CancelledTransfers /></RequirePermission>} />
          <Route path="reports/ach-volume"             element={<RequirePermission resource="reports" action="read"><AchVolume /></RequirePermission>} />
          <Route path="reports/returned-check-status"       element={<RequirePermission resource="reports" action="read"><ReturnedCheckStatus /></RequirePermission>} />
          <Route path="reports/bank-transactions-breakdown" element={<RequirePermission resource="reports" action="read"><BankTxnBreakdown /></RequirePermission>} />
          <Route path="reports/daily-drops"                 element={<RequirePermission resource="reports" action="read"><DailyDrops /></RequirePermission>} />
          <Route path="reports/check-deposits"              element={<RequirePermission resource="reports" action="read"><CheckDeposits /></RequirePermission>} />
          <Route path="reports/bank-rule-audit"             element={<RequirePermission resource="reports" action="read"><BankRuleAudit /></RequirePermission>} />
          <Route path="reports/bank-charges-by-account"     element={<RequirePermission resource="reports" action="read"><BankChargesByAccount /></RequirePermission>} />
          <Route path="reports/period-comparison"           element={<RequirePermission resource="reports" action="read"><PeriodComparison /></RequirePermission>} />
          <Route path="reports/employee-activity"           element={<RequirePermission resource="reports" action="read"><EmployeeActivity /></RequirePermission>} />
          <Route path="reports/period-pl"                   element={<RequirePermission resource="reports" action="read"><PeriodPL /></RequirePermission>} />
          <Route path="superadmin/reports/:slug"            element={<RequireRole roles={["superadmin"]}><SuperadminBIDrilldown /></RequireRole>} />
          <Route path="owner/reports/sales-by-company"      element={<RequireRole roles={["owner"]}><SalesByCompany /></RequireRole>} />
          <Route path="owner/reports/sales-by-service-type" element={<RequireRole roles={["owner"]}><SalesByService /></RequireRole>} />
          <Route path="owner/reports/sales-by-employee"     element={<RequireRole roles={["owner"]}><SalesByEmployee /></RequireRole>} />
          <Route path="owner/reports/cashier-productivity"  element={<RequireRole roles={["owner"]}><CashierProductivity /></RequireRole>} />
          <Route path="owner/reports/top-customers"  element={<RequireRole roles={["owner"]}><TopCustomers /></RequireRole>} />
          <Route path="owner/reports/top-senders"    element={<RequireRole roles={["owner"]}><TopSenders /></RequireRole>} />
          <Route path="owner/reports/top-recipients"        element={<RequireRole roles={["owner"]}><TopRecipients /></RequireRole>} />
          <Route path="owner/reports/new-vs-returning"       element={<RequireRole roles={["owner"]}><NewVsReturning /></RequireRole>} />
          <Route path="owner/reports/by-destination-country" element={<RequireRole roles={["owner"]}><ByDestinationCountry /></RequireRole>} />
          <Route path="owner/reports/fees-vs-tax"            element={<RequireRole roles={["owner"]}><FeesVsTax /></RequireRole>} />
          <Route path="owner/reports/high-value-transfers"   element={<RequireRole roles={["owner"]}><HighValueTransfers /></RequireRole>} />
          <Route path="owner/reports/cancelled-transfers"    element={<RequireRole roles={["owner"]}><CancelledTransfers /></RequireRole>} />
          <Route path="owner/reports/ach-volume"             element={<RequireRole roles={["owner"]}><AchVolume /></RequireRole>} />
          <Route path="owner/reports/returned-check-status"       element={<RequireRole roles={["owner"]}><ReturnedCheckStatus /></RequireRole>} />
          <Route path="owner/reports/bank-transactions-breakdown" element={<RequireRole roles={["owner"]}><BankTxnBreakdown /></RequireRole>} />
          <Route path="owner/reports/daily-drops"                 element={<RequireRole roles={["owner"]}><DailyDrops /></RequireRole>} />
          <Route path="owner/reports/check-deposits"              element={<RequireRole roles={["owner"]}><CheckDeposits /></RequireRole>} />
          <Route path="owner/reports/bank-rule-audit"             element={<RequireRole roles={["owner"]}><BankRuleAudit /></RequireRole>} />
          <Route path="owner/reports/bank-charges-by-account"     element={<RequireRole roles={["owner"]}><BankChargesByAccount /></RequireRole>} />
          <Route path="owner/reports/period-comparison"           element={<RequireRole roles={["owner"]}><PeriodComparison /></RequireRole>} />
          <Route path="owner/reports/employee-activity"           element={<RequireRole roles={["owner"]}><EmployeeActivity /></RequireRole>} />
          <Route path="owner/reports/period-pl"                   element={<RequireRole roles={["owner"]}><PeriodPL /></RequireRole>} />
          <Route path="batches"          element={<RequirePermission resource="batches" action="read"><Batches /></RequirePermission>} />
          <Route path="batches/new"      element={<RequirePermission resource="batches" action="create"><BatchForm /></RequirePermission>} />
          <Route path="batches/:id/edit" element={<RequirePermission resource="batches" action="update"><BatchForm /></RequirePermission>} />
          <Route path="bank"             element={<RequirePermission resource="bank_sync" action="read"><Bank /></RequirePermission>} />
          <Route path="bank/rules"       element={<RequirePermission resource="bank_sync" action="read"><BankRules /></RequirePermission>} />
          <Route path="bank-transactions" element={<RequirePermission resource="bank_sync" action="read"><BankTransactions /></RequirePermission>} />
          <Route path="monthly"          element={<RequirePermission resource="monthly" action="read"><Monthly /></RequirePermission>} />
          <Route path="monthly/edit"     element={<RequirePermission resource="monthly" action="update"><EditMonthly /></RequirePermission>} />
          <Route path="return-checks"          element={<RequirePermission resource="return_checks" action="read"><ReturnChecks /></RequirePermission>} />
          <Route path="return-checks/new"      element={<RequirePermission resource="return_checks" action="create"><ReturnCheckForm /></RequirePermission>} />
          <Route path="return-checks/:id/edit" element={<RequirePermission resource="return_checks" action="update"><ReturnCheckForm /></RequirePermission>} />
          <Route path="owner/connect"        element={<RequireRole roles={["owner"]}><OwnerConnect /></RequireRole>} />
          <Route path="owner/dashboard"      element={<RequireRole roles={["owner"]}><OwnerDashboard /></RequireRole>} />
          <Route path="owner/locations"      element={<RequireRole roles={["owner"]}><OwnerLocations /></RequireRole>} />
          <Route path="owner/pl-rollup"      element={<RequireRole roles={["owner"]}><OwnerPLRollup /></RequireRole>} />
          <Route path="owner/reports"        element={<RequireRole roles={["owner"]}><OwnerReports /></RequireRole>} />
          <Route path="owner/bulk-add-user"          element={<RequireRole roles={["owner"]}><OwnerBulkAddUser /></RequireRole>} />
          <Route path="owner/cross-store-defaults"   element={<RequireRole roles={["owner"]}><OwnerCrossStoreDefaults /></RequireRole>} />
          <Route path="owner/users"                  element={<RequireRole roles={["owner"]}><OwnerUsers /></RequireRole>} />
          <Route path="owner/settings"               element={<RequireRole roles={["owner"]}><OwnerSettings /></RequireRole>} />
          <Route path="owner/activity"               element={<RequireRole roles={["owner"]}><OwnerActivity /></RequireRole>} />
          <Route path="owner/bulk-permissions"        element={<RequireRole roles={["owner"]}><OwnerBulkPermissions /></RequireRole>} />
          <Route path="owner/store/:storeId/permissions" element={<RequireRole roles={["owner"]}><OwnerStorePermissions /></RequireRole>} />
          <Route path="owner/store/:storeId" element={<RequireRole roles={["owner"]}><OwnerStoreDetail /></RequireRole>} />
          <Route path="superadmin/dashboard"     element={<RequireRole roles={["superadmin"]}><SuperadminDashboard /></RequireRole>} />
          <Route path="superadmin/billing"       element={<RequireRole roles={["superadmin"]}><SuperadminBilling /></RequireRole>} />
          <Route path="superadmin/email-log"     element={<RequireRole roles={["superadmin"]}><SuperadminEmailLog /></RequireRole>} />
          <Route path="superadmin/health"        element={<RequireRole roles={["superadmin"]}><SuperadminHealth /></RequireRole>} />
          <Route path="superadmin/maintenance"   element={<RequireRole roles={["superadmin"]}><SuperadminMaintenance /></RequireRole>} />
          <Route path="superadmin/stores/:id/drill" element={<RequireRole roles={["superadmin"]}><SuperadminStoreDrill /></RequireRole>} />
          <Route path="superadmin/permissions"   element={<RequireRole roles={["superadmin"]}><SuperadminPermissions /></RequireRole>} />
          <Route path="superadmin/stores"        element={<RequireRole roles={["superadmin"]}><SuperadminStores /></RequireRole>} />
          <Route path="superadmin/users"         element={<RequireRole roles={["superadmin"]}><SuperadminUsers /></RequireRole>} />
          <Route path="superadmin/stores/new"    element={<RequireRole roles={["superadmin"]}><SuperadminStoreForm /></RequireRole>} />
          <Route path="superadmin/stores/:id/edit" element={<RequireRole roles={["superadmin"]}><SuperadminStoreForm /></RequireRole>} />
          <Route path="superadmin/audit-log"     element={<RequireRole roles={["superadmin"]}><SuperadminAuditLog /></RequireRole>} />
          <Route path="superadmin/announcements" element={<RequireRole roles={["superadmin"]}><SuperadminAnnouncements /></RequireRole>} />
          <Route path="superadmin/tickets"       element={<RequireRole roles={["superadmin"]}><SuperadminTickets /></RequireRole>} />
          <Route path="superadmin/controls"      element={<RequireRole roles={["superadmin"]}><SuperadminControls /></RequireRole>} />
          <Route path="superadmin/feature-flags" element={<RequireRole roles={["superadmin"]}><SuperadminFeatureFlags /></RequireRole>} />
          <Route path="superadmin/discounts"     element={<RequireRole roles={["superadmin"]}><SuperadminDiscounts /></RequireRole>} />
          <Route path="superadmin/reports"       element={<RequireRole roles={["superadmin"]}><SuperadminReports /></RequireRole>} />
          <Route path="subscribe"             element={<Subscribe />} />
          <Route path="subscribe/success"     element={<SubscribeSuccess />} />
          <Route path="admin/subscription"    element={<RequirePermission resource="settings" action="read"><AdminSubscription /></RequirePermission>} />
          <Route path="admin/data-export"     element={<RequirePermission resource="reports" action="read"><AdminDataExport /></RequirePermission>} />
          <Route path="admin/timeclock"               element={<RequirePermission resource="time_clock" action="read"><AdminTimeClock /></RequirePermission>} />
          <Route path="admin/timeclock/credentials"   element={<RequirePermission resource="time_clock" action="read"><AdminTimeClockCredentials /></RequirePermission>} />
          <Route path="admin/timeclock/schedule"      element={<RequirePermission resource="time_clock" action="read"><AdminTimeClockSchedule /></RequirePermission>} />
          <Route path="admin/timeclock/paystub/:id"   element={<RequirePermission resource="time_clock" action="read"><TimeClockPaystub /></RequirePermission>} />
          <Route path="admin/audit-log"       element={<RequirePermission resource="reports" action="read"><AdminAuditLog /></RequirePermission>} />
          <Route path="admin/store-permissions" element={<RequirePermission resource="settings" action="read"><StorePermissions /></RequirePermission>} />
          <Route path="admin/users"             element={<RequirePermission resource="users" action="read"><AdminUsers /></RequirePermission>} />
          <Route path="admin/users/new"         element={<RequirePermission resource="users" action="create"><AdminUserForm /></RequirePermission>} />
          <Route path="admin/users/:uid/edit"   element={<RequirePermission resource="users" action="update"><AdminUserForm /></RequirePermission>} />
          {/* Cashier roster — lifted out of the /settings/team tab
              when HR became its own sidebar group.  The old URL
              redirects below for bookmarks. */}
          <Route path="admin/cashiers"          element={<RequirePermission resource="users" action="read"><AdminCashiers /></RequirePermission>} />
          <Route path="timeclock"             element={<RequirePermission resource="time_clock" action="read"><TimeClock /></RequirePermission>} />
          <Route path="account/referrals"     element={<Navigate to="/settings/referrals" replace />} />
          <Route path="account/tickets"      element={<SupportTickets />} />
          {/* Legacy /account/profile — profile is now the first
              tab inside /settings (see the consolidation that
              moved the standalone page into Settings).  Keep a
              redirect for bookmarks + the rare deep link. */}
          <Route path="account/profile"       element={<Navigate to="/settings/profile" replace />} />
          <Route path="account/notifications" element={<AccountNotifications />} />
          <Route path="account/activity"      element={<AccountActivity />} />
          <Route path="account/sessions"      element={<AccountSessions />} />
          <Route path="tv-display" element={<RequirePermission resource="settings" action="read"><TVDisplayAdmin /></RequirePermission>}>
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
            <Route path="referrals" element={<SettingsReferrals />} />
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
  const location = useLocation();
  return (
    <RequireAuth>
      <ToastProvider>
        <AppShell>
          <RouteErrorBoundary routeName="authed-route">
            {/* key={pathname} remounts the page on every route
                change, re-triggering the ds-page fade-up animation
                on the PageShell inside each route. The shell
                (sidebar + topbar) stays mounted. */}
            <div key={location.pathname}>
              <Outlet />
            </div>
          </RouteErrorBoundary>
        </AppShell>
      </ToastProvider>
    </RequireAuth>
  );
}
