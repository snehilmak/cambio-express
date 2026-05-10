import { Outlet, Route, Routes } from "react-router-dom";

import AppShell from "./components/AppShell";
import RequireAuth from "./components/RequireAuth";
import AccountNotifications from "./routes/AccountNotifications";
import AccountProfile from "./routes/AccountProfile";
import AdminAuditLog from "./routes/AdminAuditLog";
import AdminReferrals from "./routes/AdminReferrals";
import AdminTaxExport from "./routes/AdminTaxExport";
import BankTransactions from "./routes/BankTransactions";
import Batches from "./routes/Batches";
import BatchForm from "./routes/BatchForm";
import Customers from "./routes/Customers";
import DailyBook from "./routes/DailyBook";
import Dashboard from "./routes/Dashboard";
import EditDailyBook from "./routes/EditDailyBook";
import EditMonthly from "./routes/EditMonthly";
import EditTransfer from "./routes/EditTransfer";
import ForgotPassword from "./routes/ForgotPassword";
import Home from "./routes/Home";
import Login from "./routes/Login";
import LoginStore from "./routes/LoginStore";
import Monthly from "./routes/Monthly";
import NewTransfer from "./routes/NewTransfer";
import NotFound from "./routes/NotFound";
import OwnerConnect from "./routes/OwnerConnect";
import OwnerLocations from "./routes/OwnerLocations";
import OwnerPLRollup from "./routes/OwnerPLRollup";
import Privacy from "./routes/Privacy";
import Reports from "./routes/Reports";
import ResetPassword from "./routes/ResetPassword";
import ReturnCheckForm from "./routes/ReturnCheckForm";
import ReturnChecks from "./routes/ReturnChecks";
import Settings from "./routes/Settings";
import Signup from "./routes/Signup";
import SignupOwner from "./routes/SignupOwner";
import Subscribe from "./routes/Subscribe";
import SubscribeSuccess from "./routes/SubscribeSuccess";
import {
  TwoFactorEnroll, TwoFactorRecover, TwoFactorVerify,
} from "./routes/TwoFactor";
import SuperadminAnnouncements from "./routes/SuperadminAnnouncements";
import SuperadminAuditLog from "./routes/SuperadminAuditLog";
import SuperadminStores from "./routes/SuperadminStores";
import TransferDetail from "./routes/TransferDetail";
import Transfers from "./routes/Transfers";

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
export default function App() {
  return (
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
        <Route path="dashboard"        element={<Dashboard />} />
        <Route path="transfers"        element={<Transfers />} />
        <Route path="transfers/new"      element={<NewTransfer />} />
        <Route path="transfers/:id"      element={<TransferDetail />} />
        <Route path="transfers/:id/edit" element={<EditTransfer />} />
        <Route path="customers"        element={<Customers />} />
        <Route path="daily"            element={<DailyBook />} />
        <Route path="daily/edit"       element={<EditDailyBook />} />
        <Route path="reports"          element={<Reports />} />
        <Route path="batches"          element={<Batches />} />
        <Route path="batches/new"      element={<BatchForm />} />
        <Route path="batches/:id/edit" element={<BatchForm />} />
        <Route path="bank-transactions" element={<BankTransactions />} />
        <Route path="monthly"          element={<Monthly />} />
        <Route path="monthly/edit"     element={<EditMonthly />} />
        <Route path="return-checks"          element={<ReturnChecks />} />
        <Route path="return-checks/new"      element={<ReturnCheckForm />} />
        <Route path="return-checks/:id/edit" element={<ReturnCheckForm />} />
        <Route path="owner/connect"   element={<OwnerConnect />} />
        <Route path="owner/locations" element={<OwnerLocations />} />
        <Route path="owner/pl-rollup" element={<OwnerPLRollup />} />
        <Route path="superadmin/stores"        element={<SuperadminStores />} />
        <Route path="superadmin/audit-log"     element={<SuperadminAuditLog />} />
        <Route path="superadmin/announcements" element={<SuperadminAnnouncements />} />
        <Route path="subscribe"             element={<Subscribe />} />
        <Route path="subscribe/success"     element={<SubscribeSuccess />} />
        <Route path="admin/tax-export"      element={<AdminTaxExport />} />
        <Route path="admin/audit-log"       element={<AdminAuditLog />} />
        <Route path="account/referrals"     element={<AdminReferrals />} />
        <Route path="account/profile"       element={<AccountProfile />} />
        <Route path="account/notifications" element={<AccountNotifications />} />
        <Route path="settings"         element={<Settings />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

// Layout route. Bounces unauthed users to /login (RequireAuth)
// and wraps the authed page in the sidebar + topbar shell.
// `<Outlet />` renders the matched child route inside.
function AuthedShell() {
  return (
    <RequireAuth>
      <AppShell>
        <Outlet />
      </AppShell>
    </RequireAuth>
  );
}
