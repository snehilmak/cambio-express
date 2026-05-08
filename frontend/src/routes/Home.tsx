import { Navigate } from "react-router-dom";

import { getCurrentIdentity } from "../lib/auth";

// Bare /app/ landing — bounces to either the dashboard (when
// signed in) or the login page (when not). Avoids showing an
// orphan placeholder that doesn't reflect the user's auth state.
export default function Home() {
  const identity = getCurrentIdentity();
  return <Navigate to={identity ? "/dashboard" : "/login"} replace />;
}
