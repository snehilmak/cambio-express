import { Navigate, useLocation } from "react-router-dom";

import { getCurrentIdentity } from "../lib/auth";

interface Props {
  children: React.ReactNode;
}

// Route guard that bounces unauthed users to /login. Designed to
// wrap the children of a <Route element={...}> entry. Preserves
// the originally-requested path in `location.state.from` so the
// login page can return the user there after a successful sign-in.
export default function RequireAuth({ children }: Props) {
  const identity = getCurrentIdentity();
  const location = useLocation();
  if (!identity) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }
  return <>{children}</>;
}
