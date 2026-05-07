import { Route, Routes } from "react-router-dom";

import RequireAuth from "./components/RequireAuth";
import Customers from "./routes/Customers";
import Dashboard from "./routes/Dashboard";
import Home from "./routes/Home";
import Login from "./routes/Login";
import NotFound from "./routes/NotFound";
import TransferDetail from "./routes/TransferDetail";
import Transfers from "./routes/Transfers";

// Top-level routing for the SPA. Each new screen registers here.
//
//   /              → bounces to /login or /dashboard
//   /login         → unauthed-only login form
//   /dashboard     → authed (RequireAuth bounces if no JWT)
//   /transfers    → authed transfers list + filters
//
// As Jinja screens migrate (daily book, reports, settings)
// each lands as its own <Route /> wrapped in <RequireAuth>.
export default function App() {
  return (
    <Routes>
      <Route index element={<Home />} />
      <Route path="login" element={<Login />} />
      <Route
        path="dashboard"
        element={
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        }
      />
      <Route
        path="transfers"
        element={
          <RequireAuth>
            <Transfers />
          </RequireAuth>
        }
      />
      <Route
        path="transfers/:id"
        element={
          <RequireAuth>
            <TransferDetail />
          </RequireAuth>
        }
      />
      <Route
        path="customers"
        element={
          <RequireAuth>
            <Customers />
          </RequireAuth>
        }
      />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
