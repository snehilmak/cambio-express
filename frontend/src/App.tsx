import { Outlet, Route, Routes } from "react-router-dom";

import AppShell from "./components/AppShell";
import RequireAuth from "./components/RequireAuth";
import Customers from "./routes/Customers";
import DailyBook from "./routes/DailyBook";
import Dashboard from "./routes/Dashboard";
import Home from "./routes/Home";
import Login from "./routes/Login";
import NewTransfer from "./routes/NewTransfer";
import NotFound from "./routes/NotFound";
import Reports from "./routes/Reports";
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
      <Route path="login" element={<Login />} />
      <Route element={<AuthedShell />}>
        <Route path="dashboard"        element={<Dashboard />} />
        <Route path="transfers"        element={<Transfers />} />
        <Route path="transfers/new"    element={<NewTransfer />} />
        <Route path="transfers/:id"    element={<TransferDetail />} />
        <Route path="customers"        element={<Customers />} />
        <Route path="daily"            element={<DailyBook />} />
        <Route path="reports"          element={<Reports />} />
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
