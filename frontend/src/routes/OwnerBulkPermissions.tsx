import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { useOwnerLocations } from "../api/owner";
import {
  Alert, Breadcrumbs, Button, Card, Checkbox, Loading,
  PageHeader, PageShell, Pill, SectionTitle, Table, useToast,
} from "../components/ui";

interface PermissionMatrix {
  store_id: number;
  roles: string[];
  editable_roles: string[];
  resources: string[];
  actions: string[];
  matrix: Record<string, Record<string, Record<string, boolean>>>;
  has_overrides: string[];
}

const RESOURCE_LABELS: Record<string, string> = {
  transfers: "Transfers", customers: "Customers", daily_book: "Daily book",
  monthly: "Monthly P&L", batches: "ACH batches", bank_sync: "Bank sync",
  reports: "Reports", settings: "Settings", users: "Users / Team",
  time_clock: "Time clock", return_checks: "Return checks",
};

export default function OwnerBulkPermissions() {
  const { data: locations, isLoading: locsLoading } = useOwnerLocations("month");
  const toast = useToast();

  const [selectedStores, setSelectedStores] = useState<Set<number>>(new Set());
  const [templateStoreId, setTemplateStoreId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Array<{ store_id: number; status: string; changes?: number; reason?: string }> | null>(null);

  const { data: templatePerms } = useQuery<PermissionMatrix>({
    enabled: templateStoreId !== null,
    queryKey: ["owner-store-permissions", templateStoreId],
    queryFn: () => api<PermissionMatrix>(`/api/v2/owner/store/${templateStoreId}/permissions`),
  });

  function toggleStore(sid: number) {
    setSelectedStores((prev) => {
      const next = new Set(prev);
      if (next.has(sid)) next.delete(sid);
      else next.add(sid);
      return next;
    });
  }

  function selectAll() {
    if (!locations) return;
    const allIds = locations.rows.map((s) => s.store_id);
    setSelectedStores(
      selectedStores.size === allIds.length ? new Set() : new Set(allIds),
    );
  }

  async function handlePush(e: FormEvent) {
    e.preventDefault();
    if (!templatePerms || selectedStores.size === 0) return;
    setBusy(true);
    setError(null);
    setResults(null);

    const changes: Array<{ role: string; resource: string; action: string; allowed: boolean }> = [];
    for (const role of templatePerms.editable_roles) {
      for (const resource of templatePerms.resources) {
        for (const action of templatePerms.actions) {
          changes.push({
            role, resource, action,
            allowed: templatePerms.matrix[role][resource][action],
          });
        }
      }
    }

    try {
      const resp = await api<{ results: typeof results }>("/api/v2/owner/bulk-permissions", {
        method: "POST",
        json: {
          store_ids: [...selectedStores],
          changes,
        },
      });
      setResults(resp.results);
      const applied = resp.results?.filter((r) => r.status === "applied").length ?? 0;
      toast({ message: `Pushed permissions to ${applied} store(s).`, tone: "success" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to push permissions.");
    } finally {
      setBusy(false);
    }
  }

  if (locsLoading) return <PageShell gap="1.25rem"><Loading /></PageShell>;

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[
        { label: "Owner settings", to: "/owner/settings" },
        { label: "Bulk permissions" },
      ]} />
      <PageHeader
        title="Bulk Permissions"
        subtitle="Copy one store's employee permissions to other stores"
      />

      {error && <Alert tone="error">{error}</Alert>}

      <Card>
        <SectionTitle>1. Choose a source store</SectionTitle>
        <p style={{ fontSize: "0.85rem", color: "var(--db-text-muted)", margin: "0 0 0.5rem" }}>
          Pick the store whose employee permissions you want to replicate.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          {locations?.rows.map((s) => (
            <button
              key={s.store_id}
              type="button"
              onClick={() => setTemplateStoreId(s.store_id)}
              style={{
                padding: "0.4rem 0.75rem", borderRadius: "0.375rem", cursor: "pointer",
                border: templateStoreId === s.store_id
                  ? "2px solid var(--db-accent)" : "1px solid var(--db-border)",
                background: templateStoreId === s.store_id
                  ? "rgba(63,255,0,0.08)" : "var(--db-surface)",
                color: "var(--db-text)", fontWeight: templateStoreId === s.store_id ? 600 : 400,
                fontSize: "0.85rem",
              }}
            >
              {s.store_name}
            </button>
          ))}
        </div>
      </Card>

      {templatePerms && (
        <Card>
          <SectionTitle>Employee permissions at source</SectionTitle>
          <div style={{ overflowX: "auto", fontSize: "0.85rem" }}>
            <Table>
              <thead>
                <tr>
                  <th>Resource</th>
                  {templatePerms.actions.map((a) => <th key={a}>{a}</th>)}
                </tr>
              </thead>
              <tbody>
                {templatePerms.resources.map((res) => (
                  <tr key={res}>
                    <td>{RESOURCE_LABELS[res] ?? res}</td>
                    {templatePerms.actions.map((act) => (
                      <td key={act} style={{ textAlign: "center" }}>
                        {templatePerms.matrix["employee"]?.[res]?.[act] ? "✓" : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>
      )}

      <Card>
        <SectionTitle>2. Select target stores</SectionTitle>
        <p style={{ fontSize: "0.85rem", color: "var(--db-text-muted)", margin: "0 0 0.5rem" }}>
          These stores will receive the source store's employee permissions.
        </p>
        <div style={{ marginBottom: "0.5rem" }}>
          <Button size="sm" tone="secondary" onClick={selectAll} type="button">
            {selectedStores.size === (locations?.rows.length ?? 0) ? "Clear all" : "Select all"}
          </Button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          {locations?.rows.map((s) => (
            <Checkbox
              key={s.store_id}
              checked={selectedStores.has(s.store_id)}
              onChange={() => toggleStore(s.store_id)}
            >
              {s.store_name}
            </Checkbox>
          ))}
        </div>
      </Card>

      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
        <Button
          onClick={(e) => { void handlePush(e as unknown as FormEvent); }}
          busy={busy}
          disabled={!templatePerms || selectedStores.size === 0}
        >
          Push to {selectedStores.size} store{selectedStores.size === 1 ? "" : "s"}
        </Button>
      </div>

      {results && (
        <Card>
          <SectionTitle>Results</SectionTitle>
          <Table>
            <thead>
              <tr>
                <th>Store</th>
                <th>Status</th>
                <th>Changes</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.store_id}>
                  <td>{locations?.rows.find((s) => s.store_id === r.store_id)?.store_name ?? `#${r.store_id}`}</td>
                  <td>
                    <Pill tone={r.status === "applied" ? "accent" : "neutral"}>
                      {r.status}
                    </Pill>
                  </td>
                  <td>{r.changes ?? r.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </PageShell>
  );
}
