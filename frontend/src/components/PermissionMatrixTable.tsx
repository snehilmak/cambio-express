import type { ReactNode } from "react";

import { Checkbox } from "./ui";
import styles from "./PermissionMatrixTable.module.css";

// Single source of truth for permission-matrix labels — every
// route that renders the resources × actions grid goes through
// these (StorePermissions, OwnerStorePermissions,
// SuperadminPermissions, SuperadminStoreDrill, AdminUserForm).
/* eslint-disable react-refresh/only-export-components -- the label
   maps are the component's default labelers; exporting them here
   keeps one import path for the matrix + its vocabulary.  Fast-
   refresh skip on this single file is acceptable. */
export const RESOURCE_LABELS: Record<string, string> = {
  transfers: "Money transfers",
  customers: "Customers",
  daily_book: "Daily book",
  monthly: "Monthly P&L",
  batches: "ACH batches",
  bank_sync: "Bank sync",
  reports: "Reports",
  settings: "Settings",
  users: "Users / Team",
  time_clock: "Time clock (HR)",
  return_checks: "Returned checks",
  lottery: "Lottery",
  day_close: "Store daily book",
  catalog: "Price book & purchases",
};

export const ACTION_LABELS: Record<string, string> = {
  create: "Create", read: "View", update: "Edit", delete: "Delete",
};
/* eslint-enable react-refresh/only-export-components */

const defaultResourceLabel = (r: string) => RESOURCE_LABELS[r] ?? r;
const defaultActionLabel = (a: string) => ACTION_LABELS[a] ?? a;

/** Resources × actions checkbox grid — THE permission matrix.
 *  One shared rendering for every permissions surface (see
 *  UI-STANDARDS.md §5). The component owns the overflow wrapper,
 *  the table markup and the cell checkboxes; callers supply the
 *  axes plus `checked` / `onToggle` accessors scoped to whatever
 *  entity (role, user) the surrounding card represents.
 */
export function PermissionMatrixTable({
  resources,
  actions,
  checked,
  onToggle,
  disabled = false,
  resourceLabel = defaultResourceLabel,
  actionLabel = defaultActionLabel,
  resourceHeader = "Resource",
  ariaContext,
  trailingColumn,
}: {
  resources: string[];
  actions: string[];
  /** Is the (resource, action) cell checked? */
  checked: (resource: string, action: string) => boolean;
  onToggle: (resource: string, action: string) => void;
  disabled?: boolean;
  resourceLabel?: (resource: string) => string;
  actionLabel?: (action: string) => string;
  /** First-column header text (default "Resource"). */
  resourceHeader?: string;
  /** Appended to each cell's aria-label, e.g. the role the
   *  surrounding card edits: `View — Reports (admin)`. */
  ariaContext?: string;
  /** Optional extra column after the action columns (e.g. the
   *  per-resource "all actions" checkbox on SuperadminPermissions).
   *  The rendered node is centered inside the cell. */
  trailingColumn?: {
    header: ReactNode;
    render: (resource: string) => ReactNode;
  };
}) {
  const context = ariaContext ? ` (${ariaContext})` : "";
  return (
    <div className={styles.scroll}>
      <table className={styles.matrix}>
        <thead>
          <tr>
            <th>{resourceHeader}</th>
            {actions.map((a) => <th key={a}>{actionLabel(a)}</th>)}
            {trailingColumn && <th>{trailingColumn.header}</th>}
          </tr>
        </thead>
        <tbody>
          {resources.map((resource) => (
            <tr key={resource}>
              <td>{resourceLabel(resource)}</td>
              {actions.map((action) => (
                <td key={action}>
                  <div className={styles.checkCell}>
                    <Checkbox
                      checked={checked(resource, action)}
                      onChange={() => onToggle(resource, action)}
                      disabled={disabled}
                      aria-label={`${actionLabel(action)} — ${resourceLabel(resource)}${context}`}
                    />
                  </div>
                </td>
              ))}
              {trailingColumn && (
                <td>
                  <div className={styles.checkCell}>
                    {trailingColumn.render(resource)}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
