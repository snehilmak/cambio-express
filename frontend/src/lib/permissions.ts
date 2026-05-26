import { getCurrentIdentity } from "./auth";

/**
 * Check if the current user has a specific granular permission.
 * Returns true if the permission is in the JWT perms claim,
 * or if the user is superadmin (always has everything).
 */
export function hasPermission(resource: string, action: string): boolean {
  const identity = getCurrentIdentity();
  if (!identity) return false;
  if (identity.role === "superadmin") return true;
  return identity.permissions.includes(`${resource}.${action}`);
}

/**
 * React hook version — same logic, reads from identity cache.
 * Use in components for conditional rendering:
 *
 *   const canCreate = useHasPermission("transfers", "create");
 *   {canCreate && <Button>+ New transfer</Button>}
 */
export function useHasPermission(resource: string, action: string): boolean {
  return hasPermission(resource, action);
}
