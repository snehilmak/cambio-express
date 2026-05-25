import { useMemo, useState, type FormEvent } from "react";

import {
  bulkAddUser, useOwnerLocations,
  type OwnerBulkAddUserResultRow,
} from "../api/owner";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, Empty, ErrorState, Field, Input, Loading,
  PageHeader, PageShell, Pill, Section, Select, Table, tdStyle, thStyle,
} from "../components/ui";
import styles from "./OwnerBulkAddUser.module.css";

// /app/owner/bulk-add-user — owner-side helper to create one
// login at many of their linked stores at once. Useful for a
// regional manager who needs the same credentials across every
// store in the umbrella. Server creates N independent User rows
// (one per store) sharing the same username + password — single-
// row multi-store user is a separate architectural item.

export default function OwnerBulkAddUser() {
  const identity = getCurrentIdentity();
  const { data: locations, isLoading, isError, refetch } =
    useOwnerLocations("month", "");

  const [username, setUsername]   = useState("");
  const [password, setPassword]   = useState("");
  const [fullName, setFullName]   = useState("");
  const [role, setRole]           = useState<"admin" | "employee">("employee");
  const [storeIds, setStoreIds]   = useState<number[]>([]);
  const [busy, setBusy]           = useState(false);
  const [err, setErr]             = useState<string | null>(null);
  const [results, setResults]     =
    useState<OwnerBulkAddUserResultRow[] | null>(null);

  const allStoreIds = useMemo(
    () => locations?.rows.map((r) => r.store_id) ?? [],
    [locations],
  );
  const allSelected = storeIds.length === allStoreIds.length
    && allStoreIds.length > 0;

  if (!identity || (identity.role !== "owner"
                    && identity.role !== "superadmin")) {
    return (
      <PageShell>
        <PageHeader title="Bulk add user" />
        <Empty>This page is owner-only.</Empty>
      </PageShell>
    );
  }

  function toggleStore(id: number) {
    setStoreIds((prev) =>
      prev.includes(id)
        ? prev.filter((s) => s !== id)
        : [...prev, id],
    );
  }

  function toggleAll() {
    setStoreIds(allSelected ? [] : [...allStoreIds]);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null); setResults(null); setBusy(true);
    try {
      const out = await bulkAddUser({
        username: username.trim(),
        password,
        full_name: fullName.trim(),
        role,
        store_ids: storeIds,
      });
      setResults(out.results);
      // Wipe the password input so accidental re-submit doesn't
      // reuse it. Username + full name stay so the operator can
      // iterate on a partial-success result.
      setPassword("");
    } catch (e2) {
      setErr(
        e2 instanceof ApiError
          ? e2.message
          : "Could not create users.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell maxWidth="56rem">

      <Breadcrumbs crumbs={[{ label: "Owner" }, { label: "Bulk add user" }]} />

      <PageHeader
        title="Bulk add user"
        subtitle={
          "Create the same login (username + password) at every "
          + "store you select. Skips stores that already have a "
          + "user with this username."
        }
      />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Couldn't load your stores."
          onRetry={() => { void refetch(); }}
        />
      )}

      {locations && locations.rows.length === 0 && (
        <Empty>
          You don't have any stores connected to your umbrella yet —
          mint a connect code from <code>/app/owner/connect</code> and
          share it with a store admin first.
        </Empty>
      )}

      {locations && locations.rows.length > 0 && (
        <form onSubmit={onSubmit}>
          <Card>
            <Section>
              <div className={styles.grid}>
                <Field label="Email / username">
                  <Input
                    type="email" required maxLength={80}
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="off"
                    placeholder="manager@example.com"
                  />
                </Field>
                <Field
                  label="Password"
                  hint="Min 8 chars. Operator can rotate per-store later from each store's user list."
                >
                  <Input
                    type="password" required minLength={8} maxLength={200}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                </Field>
                <Field label="Full name (optional)">
                  <Input
                    type="text" maxLength={120}
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                  />
                </Field>
                <Field label="Role">
                  <Select
                    value={role}
                    onChange={(e) => setRole(
                      e.target.value === "admin" ? "admin" : "employee",
                    )}
                  >
                    <option value="employee">Employee (cashier)</option>
                    <option value="admin">Admin</option>
                  </Select>
                </Field>
              </div>
            </Section>

            <Section title="Apply to stores">
              <div className={styles.toolbar}>
                <Button
                  type="button"
                  tone="secondary" size="sm"
                  onClick={toggleAll}
                >
                  {allSelected ? "Clear all" : "Select all"}
                </Button>
                <span className={styles.toolbarCount}>
                  {storeIds.length} of {allStoreIds.length} selected
                </span>
              </div>
              <ul className={styles.storeList}>
                {locations.rows.map((s) => {
                  const checked = storeIds.includes(s.store_id);
                  return (
                    <li key={s.store_id}>
                      <label className={styles.storeRow}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleStore(s.store_id)}
                        />
                        <span className={styles.storeName}>{s.store_name}</span>
                        <span className={styles.storeSlug}>{s.store_slug}</span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </Section>

            {err && <Alert tone="error">{err}</Alert>}

            <div className={styles.actions}>
              <Button
                type="submit"
                busy={busy}
                disabled={
                  busy
                  || !username.trim()
                  || password.length < 8
                  || storeIds.length === 0
                }
              >
                {busy
                  ? "Creating…"
                  : `Create user at ${storeIds.length} store${storeIds.length === 1 ? "" : "s"}`}
              </Button>
            </div>
          </Card>
        </form>
      )}

      {results && <ResultsCard rows={results} />}
    </PageShell>
  );
}


function ResultsCard({ rows }: { rows: OwnerBulkAddUserResultRow[] }) {
  return (
    <Card>
      <Section title="Results">
        <Table>
          <thead>
            <tr>
              {["Store", "Status", "Notes"].map((h) => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.store_id}-${i}`}>
                <td style={tdStyle}>{r.store_name || `Store #${r.store_id}`}</td>
                <td style={tdStyle}><StatusPill status={r.status} /></td>
                <td style={tdStyle}>{r.detail || "—"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Section>
    </Card>
  );
}


function StatusPill({ status }: { status: OwnerBulkAddUserResultRow["status"] }) {
  if (status === "created") return <Pill tone="accent">Created</Pill>;
  if (status === "skipped") return <Pill tone="warning">Skipped</Pill>;
  return <Pill tone="negative">Rejected</Pill>;
}
