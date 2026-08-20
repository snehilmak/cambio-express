import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { getCurrentIdentity, refreshToken } from "../lib/auth";
import { useUnsavedChangesGuard } from "../lib/useUnsavedChangesGuard";
import {
  Alert, Breadcrumbs, Button, Card, Checkbox, Loading,
  PageHeader, PageShell, Pill, SectionTitle, useToast,
} from "../components/ui";
import styles from "./StorePermissions.module.css";

interface PermissionMatrix {
  roles: string[];
  editable_roles: string[];
  resources: string[];
  actions: string[];
  matrix: Record<string, Record<string, Record<string, boolean>>>;
  has_overrides: string[];
}

const RESOURCE_LABELS: Record<string, string> = {
  transfers: "Transfers",
  customers: "Customers",
  daily_book: "Daily book",
  monthly: "Monthly P&L",
  batches: "ACH batches",
  bank_sync: "Bank sync",
  reports: "Reports",
  settings: "Settings",
  users: "Users / Team",
  time_clock: "Time clock",
  return_checks: "Returned checks",
};

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  employee: "Employee",
  owner: "Owner",
};

function useStorePermissions() {
  const identity = getCurrentIdentity();
  return useQuery<PermissionMatrix>({
    enabled: identity != null && identity.role !== "employee",
    queryKey: ["store-permissions"],
    queryFn: () => api<PermissionMatrix>("/api/v2/admin/store-permissions"),
  });
}

export default function StorePermissions() {
  const { data, isLoading, isError, error, refetch } = useStorePermissions();
  const qc = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<PermissionMatrix | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate draft from server
      setDraft(structuredClone(data));
    }
  }, [data]);

  const isDirty = data && draft
    ? JSON.stringify(data.matrix) !== JSON.stringify(draft.matrix)
    : false;
  // Warn on tab-close / refresh while the permission matrix has unsaved
  // toggles (the page saves in place — no navigating Cancel to guard).
  useUnsavedChangesGuard(isDirty);

  function toggle(role: string, resource: string, action: string) {
    if (!draft || !draft.editable_roles.includes(role)) return;
    setDraft((prev) => {
      if (!prev) return prev;
      const next = structuredClone(prev);
      next.matrix[role][resource][action] = !next.matrix[role][resource][action];
      return next;
    });
  }

  function reset() {
    if (data) setDraft(structuredClone(data));
  }

  async function save() {
    if (!data || !draft) return;
    setBusy(true);
    setSaveError(null);
    const editableMatrix: Record<string, Record<string, Record<string, boolean>>> = {};
    for (const role of draft.roles) {
      if (!draft.editable_roles.includes(role)) continue;
      editableMatrix[role] = draft.matrix[role];
    }
    try {
      const result = await api<PermissionMatrix>("/api/v2/admin/store-permissions", {
        method: "PUT",
        json: { matrix: editableMatrix },
      });
      setDraft(structuredClone(result));
      qc.setQueryData(["store-permissions"], result);
      await refreshToken();
      toast({ message: "Permissions updated for this store.", tone: "success" });
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save permissions.");
    } finally {
      setBusy(false);
    }
  }

  async function resetToGlobal(role: string) {
    setBusy(true);
    setSaveError(null);
    try {
      const result = await api<PermissionMatrix>("/api/v2/admin/store-permissions/reset", {
        method: "POST",
        json: { role },
      });
      setDraft(structuredClone(result));
      qc.setQueryData(["store-permissions"], result);
      await refreshToken();
      toast({ message: `${ROLE_LABELS[role] ?? role} permissions reset to defaults.`, tone: "success" });
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not reset.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[
        { label: "Settings", to: "/settings" },
        { label: "Store permissions" },
      ]} />

      <PageHeader
        title="Store Permissions"
        subtitle="Customize what each role can do in this store"
      />

      {isLoading && <Loading />}
      {isError && (
        <Alert tone="error">
          {error instanceof Error ? error.message : "Could not load permissions"}
          <Button tone="secondary" size="sm" onClick={() => { void refetch(); }}>Retry</Button>
        </Alert>
      )}

      {saveError && <Alert tone="error">{saveError}</Alert>}

      {draft && draft.roles.map((role) => {
        const canEdit = draft.editable_roles.includes(role);
        const hasOverride = draft.has_overrides.includes(role);
        return (
          <Card key={role}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
              <SectionTitle>
                <Pill tone={role === "admin" ? "accent" : role === "owner" ? "info" : "neutral"}>
                  {ROLE_LABELS[role] ?? role}
                </Pill>
                {hasOverride && (
                  <span className={styles.overrideBadge}>customized</span>
                )}
              </SectionTitle>
              {canEdit && hasOverride && (
                <Button
                  tone="secondary" size="sm"
                  className={styles.resetBtn}
                  onClick={() => { void resetToGlobal(role); }}
                  disabled={busy}
                >
                  Reset to defaults
                </Button>
              )}
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className={styles.matrix}>
                <thead>
                  <tr>
                    <th>Resource</th>
                    {draft.actions.map((a) => <th key={a}>{a}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {draft.resources.map((resource) => (
                    <tr key={resource}>
                      <td>{RESOURCE_LABELS[resource] ?? resource}</td>
                      {draft.actions.map((action) => (
                        <td key={action}>
                          <div className={styles.checkCell}>
                            <Checkbox
                              checked={draft.matrix[role][resource][action]}
                              onChange={() => toggle(role, resource, action)}
                              disabled={!canEdit}
                            >{""}</Checkbox>
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        );
      })}

      {draft && (
        <div className={styles.saveBar}>
          {isDirty && <span className={styles.dirty}>Unsaved changes</span>}
          <Button tone="secondary" onClick={reset} disabled={!isDirty || busy}>
            Reset
          </Button>
          <Button onClick={() => { void save(); }} busy={busy} disabled={!isDirty || busy}>
            {busy ? "Saving…" : "Save permissions"}
          </Button>
        </div>
      )}
    </PageShell>
  );
}
