import { Navigate } from "react-router-dom";

import { getCurrentIdentity } from "../lib/auth";

interface Props {
  roles: string[];
  children: React.ReactNode;
}

export default function RequireRole({ roles, children }: Props) {
  const identity = getCurrentIdentity();
  if (!identity) return <Navigate to="/login" replace />;
  if (roles.includes(identity.role) || identity.role === "superadmin") {
    return <>{children}</>;
  }
  return <Navigate to="/dashboard" replace />;
}
