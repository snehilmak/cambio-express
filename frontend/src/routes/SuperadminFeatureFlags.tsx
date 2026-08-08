import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  useFeatureFlags,
  useStoreOverrides,
  createFeatureFlag,
  toggleFeatureFlag,
  deleteFeatureFlag,
  setStoreOverride,
  clearStoreOverride,
  type FeatureFlagRow,
  type StoreOverrideRow,
} from "../api/featureFlags";
import { ApiError } from "../lib/api";
import { useApiErrorToast } from "../lib/useApiErrorToast";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Loading,
  PageHeader,
  PageShell,
  Pill,
  RowActions,
  Table,
  Textarea,
  useToast,
} from "../components/ui";

export default function SuperadminFeatureFlags() {
  const { data, isLoading, isError } = useFeatureFlags();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  return (
    <PageShell gap="1.25rem">
      <PageHeader
        title="Feature Flags"
        subtitle="Platform-wide flags with per-store overrides"
        actions={
          <Button onClick={() => setCreating(true)} disabled={creating}>
            + New flag
          </Button>
        }
      />

      {creating && (
        <CreateFlagForm
          onDone={() => {
            setCreating(false);
            void qc.invalidateQueries({ queryKey: ["feature-flags"] });
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      {isLoading && <Loading />}
      {isError && <Alert tone="error">Could not load feature flags.</Alert>}

      {data && data.rows.length === 0 && !creating && (
        <EmptyState
          title="No feature flags"
          body="Create a flag to gate features per-store."
        />
      )}

      {data && data.rows.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                <th>Key</th>
                <th>Label</th>
                <th>Default</th>
                <th>Created</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((flag) => (
                <FlagRow
                  key={flag.id}
                  flag={flag}
                  expanded={expandedKey === flag.key}
                  onToggleExpand={() =>
                    setExpandedKey(expandedKey === flag.key ? null : flag.key)
                  }
                  onRefresh={() =>
                    void qc.invalidateQueries({ queryKey: ["feature-flags"] })
                  }
                />
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </PageShell>
  );
}

function FlagRow({
  flag,
  expanded,
  onToggleExpand,
  onRefresh,
}: {
  flag: FeatureFlagRow;
  expanded: boolean;
  onToggleExpand: () => void;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const toastApiError = useApiErrorToast();
  const [busy, setBusy] = useState(false);

  async function handleToggle() {
    setBusy(true);
    try {
      await toggleFeatureFlag(flag.key, !flag.enabled_by_default);
      onRefresh();
      toast({ message: `${flag.key} → ${!flag.enabled_by_default ? "enabled" : "disabled"}`, tone: "success" });
    } catch (err) {
      toastApiError(err, "Toggle failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete flag "${flag.key}"? This also removes all per-store overrides.`)) return;
    setBusy(true);
    try {
      await deleteFeatureFlag(flag.key);
      onRefresh();
      toast({ message: `${flag.key} deleted`, tone: "success" });
    } catch (err) {
      toastApiError(err, "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <tr>
        <td style={{ fontFamily: "var(--db-font-mono, monospace)", fontSize: "0.85rem" }}>
          {flag.key}
        </td>
        <td>{flag.label || <span style={{ color: "var(--db-text-muted)" }}>—</span>}</td>
        <td>
          <Pill tone={flag.enabled_by_default ? "accent" : "neutral"}>
            {flag.enabled_by_default ? "ON" : "OFF"}
          </Pill>
        </td>
        <td style={{ fontSize: "0.82rem", color: "var(--db-text-muted)" }}>
          {new Date(flag.created_at).toLocaleDateString()}
        </td>
        <td style={{ textAlign: "right" }}>
          <RowActions
            title={flag.key}
            actions={[
              {
                label: flag.enabled_by_default ? "Disable" : "Enable",
                onClick: handleToggle, disabled: busy,
              },
              {
                label: expanded ? "Hide overrides" : "Overrides",
                onClick: onToggleExpand,
              },
              {
                label: "Delete", tone: "danger",
                onClick: handleDelete, disabled: busy,
              },
            ]}
          />
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5} style={{ padding: 0 }}>
            <OverridesPanel flagKey={flag.key} />
          </td>
        </tr>
      )}
    </>
  );
}

function OverridesPanel({ flagKey }: { flagKey: string }) {
  const { data, isLoading } = useStoreOverrides(flagKey);
  const qc = useQueryClient();
  const toast = useToast();
  const toastApiError = useApiErrorToast();
  const [addStoreId, setAddStoreId] = useState("");

  async function handleSet(storeId: number, enabled: boolean) {
    try {
      await setStoreOverride(flagKey, storeId, enabled);
      void qc.invalidateQueries({ queryKey: ["feature-flag-overrides", flagKey] });
      toast({ message: `Store ${storeId} override → ${enabled ? "ON" : "OFF"}`, tone: "success" });
    } catch (err) {
      toastApiError(err, "Failed");
    }
  }

  async function handleClear(storeId: number) {
    try {
      await clearStoreOverride(flagKey, storeId);
      void qc.invalidateQueries({ queryKey: ["feature-flag-overrides", flagKey] });
      toast({ message: `Override cleared for store ${storeId}`, tone: "success" });
    } catch (err) {
      toastApiError(err, "Failed");
    }
  }

  async function handleAdd() {
    const sid = parseInt(addStoreId, 10);
    if (!sid || sid < 1) return;
    await handleSet(sid, true);
    setAddStoreId("");
  }

  return (
    <div style={{ padding: "1rem 1.5rem", background: "var(--db-surface-2, rgba(255,255,255,0.03))" }}>
      <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.5rem" }}>
        Per-store overrides for <code>{flagKey}</code>
      </div>
      {isLoading && <Loading />}
      {data && data.rows.length === 0 && (
        <div style={{ fontSize: "0.82rem", color: "var(--db-text-muted)", marginBottom: "0.5rem" }}>
          No overrides — all stores use the global default.
        </div>
      )}
      {data && data.rows.length > 0 && (
        <div style={{ marginBottom: "0.75rem" }}>
          <Table style={{ fontSize: "0.85rem" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Store</th>
                <th>Override</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((o: StoreOverrideRow) => (
                <tr key={o.store_id}>
                  <td>{o.store_name} <span style={{ color: "var(--db-text-muted)" }}>({o.store_slug})</span></td>
                  <td>
                    <Pill tone={o.enabled ? "accent" : "neutral"}>
                      {o.enabled ? "ON" : "OFF"}
                    </Pill>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <RowActions
                      title={`${o.store_name} (${o.store_slug})`}
                      actions={[
                        {
                          label: "Flip",
                          onClick: () => handleSet(o.store_id, !o.enabled),
                        },
                        {
                          label: "Clear", tone: "danger",
                          onClick: () => handleClear(o.store_id),
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <Input
          style={{ width: "8rem" }}
          type="number"
          min={1}
          placeholder="Store ID"
          value={addStoreId}
          onChange={(e) => setAddStoreId(e.target.value)}
        />
        <Button size="sm" onClick={() => { void handleAdd(); }}>
          Add override
        </Button>
      </div>
    </div>
  );
}

function CreateFlagForm({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}) {
  const toast = useToast();
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!key.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createFeatureFlag({
        key: key.trim(),
        label: label.trim() || undefined,
        description: description.trim() || undefined,
        enabled_by_default: enabled,
      });
      toast({ message: `Flag "${key}" created`, tone: "success" });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create flag.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={(e) => { void handleSubmit(e); }} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <div style={{ fontWeight: 600 }}>New feature flag</div>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Key" hint="Lowercase + underscores only (e.g. addon_tv_display)">
          <Input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            pattern="^[a-z0-9_]+$"
            required
            placeholder="addon_my_feature"
          />
        </Field>
        <Field label="Label">
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="My Feature" />
        </Field>
        <Field label="Description">
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </Field>
        <label style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.88rem" }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled by default
        </label>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <Button type="submit" busy={busy}>Create</Button>
          <Button tone="secondary" onClick={onCancel} type="button">Cancel</Button>
        </div>
      </form>
    </Card>
  );
}
