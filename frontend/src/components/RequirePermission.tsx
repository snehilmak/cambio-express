import { Navigate } from "react-router-dom";

import { getCurrentIdentity } from "../lib/auth";
import { hasPermission } from "../lib/permissions";

interface Props {
  resource: string;
  action: string;
  children: React.ReactNode;
}

export default function RequirePermission({ resource, action, children }: Props) {
  const identity = getCurrentIdentity();
  if (!identity) return <Navigate to="/login" replace />;
  if (hasPermission(resource, action)) return <>{children}</>;
  return (
    <Navigate to="/dashboard" replace />
  );
}
