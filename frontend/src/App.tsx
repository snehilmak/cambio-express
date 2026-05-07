import { Route, Routes } from "react-router-dom";

import RequireAuth from "./components/RequireAuth";
import Dashboard from "./routes/Dashboard";
import Home from "./routes/Home";
import Login from "./routes/Login";
import NotFound from "./routes/NotFound";

// Top-level routing for the SPA. Each new screen registers here.
//
//   /                   → bounces to /login or /dashboard
//   /login              → unauthed-only login form
//   /dashboard          → authed (RequireAuth bounces if no JWT)
//
// As Jinja screens migrate (transfer list, daily book, reports)
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
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
