import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { useUnsavedChangesGuard } from "../lib/useUnsavedChangesGuard";
import {
  Alert,
  Breadcrumbs,
  Button,
  Card,
  Checkbox,
  ErrorState,
  Loading,
  PageHeader,
  PageShell,
  Pill,
  SectionTitle,
  useToast,
} from "../components/ui";
import { PermissionMatrixTable } from "../components/PermissionMatrixTable";
import styles from "./SuperadminPermissions.module.css";

interface PermissionMatrix {
  roles: string[];
  resources: string[];
  actions: string[];
  matrix: Record<string, Record<string, Record<string, boolean>>>;
}

function usePermissionMatrix() {
  const identity = getCurrentIdentity();
  return useQuery<PermissionMatrix>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "permissions"],
    queryFn: () => api<PermissionMatrix>("/api/v2/superadmin/permissions"),
  });
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  employee: "Employee",
  owner: "Owner",
};

const ROLE_TONES: Record<string, "accent" | "info" | "neutral"> = {
  admin: "accent",
  employee: "neutral",
  owner: "info",
};

export default function SuperadminPermissions() {
  const { data, isLoading, isError, error, refetch } = usePermissionMatrix();
  const qc = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<PermissionMatrix | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local draft from server-fetched matrix for controlled checkboxes
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
    if (!draft) return;
    setDraft((prev) => {
      if (!prev) return prev;
      const next = structuredClone(prev);
      next.matrix[role][resource][action] = !next.matrix[role][resource][action];
      return next;
    });
  }

  function toggleAllForRole(role: string, resource: string, value: boolean) {
    if (!draft) return;
    setDraft((prev) => {
      if (!prev) return prev;
      const next = structuredClone(prev);
      for (const action of next.actions) {
        next.matrix[role][resource][action] = value;
      }
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
    const changes: Array<{ role: string; resource: string; action: string; allowed: boolean }> = [];
    for (const role of draft.roles) {
      for (const resource of draft.resources) {
        for (const action of draft.actions) {
          const was = data.matrix[role][resource][action];
          const now = draft.matrix[role][resource][action];
          if (was !== now) {
            changes.push({ role, resource, action, allowed: now });
          }
        }
      }
    }
    if (changes.length === 0) return;
    try {
      const result = await api<PermissionMatrix>("/api/v2/superadmin/permissions", {
        method: "PUT",
        json: { changes },
      });
      setDraft(structuredClone(result));
      qc.setQueryData(["superadmin", "permissions"], result);
      toast({ message: `${changes.length} permission${changes.length === 1 ? "" : "s"} updated.`, tone: "success" });
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save permissions.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Permissions" }]} />

      <PageHeader
        title="Role Permissions"
        subtitle="Configure what each role can do across the platform"
      />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load permissions"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {saveError && <Alert tone="error">{saveError}</Alert>}

      {draft && draft.roles.map((role) => (
        <Card key={role}>
          <SectionTitle>
            <Pill tone={ROLE_TONES[role] ?? "neutral"}>{ROLE_LABELS[role] ?? role}</Pill>
          </SectionTitle>
          <PermissionMatrixTable
            resources={draft.resources}
            actions={draft.actions}
            checked={(resource, action) => draft.matrix[role][resource][action]}
            onToggle={(resource, action) => toggle(role, resource, action)}
            ariaContext={role}
            trailingColumn={{
              header: "All",
              render: (resource) => {
                const allChecked = draft.actions.every(
                  (a) => draft.matrix[role][resource][a],
                );
                return (
                  <Checkbox
                    checked={allChecked}
                    onChange={() => toggleAllForRole(role, resource, !allChecked)}
                    aria-label={`All actions — ${resource} (${role})`}
                  />
                );
              },
            }}
          />
        </Card>
      ))}

      {draft && (
        <div className={styles.saveBar}>
          {isDirty && (
            <span className={styles.dirty}>Unsaved changes</span>
          )}
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
