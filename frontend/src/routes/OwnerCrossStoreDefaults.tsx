import { useMemo, useState, type FormEvent } from "react";

import {
  applyCrossStoreDefaults, useOwnerLocations,
  type OwnerCrossStoreDefaultsBody, type OwnerCrossStoreResultRow,
} from "../api/owner";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, Checkbox, Empty, ErrorState, Field, Input,
  Loading, PageHeader, PageShell, Pill, Section, Select, Table,
  tdStyle, thStyle,
} from "../components/ui";
import styles from "./OwnerCrossStoreDefaults.module.css";

// /app/owner/cross-store-defaults — owner pushes the same
// field defaults (fed-tax-rate, timezone, business-hours
// toggles, contact info) to every store they pick. Mirrors
// the bulk-add-user UX so the result table reads the same.
//
// The form picks fields via per-field "Apply" checkboxes —
// fields without a checked box are omitted from the request,
// keeping the per-store row untouched (different from the
// per-store settings form where every save replaces every
// editable field).

const TIMEZONE_CHOICES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Phoenix",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
  "America/Mexico_City",
  "America/Bogota",
  "America/Lima",
  "America/Santiago",
  "America/Buenos_Aires",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Madrid",
  "Asia/Manila",
  "Asia/Karachi",
  "UTC",
];

export default function OwnerCrossStoreDefaults() {
  const identity = getCurrentIdentity();
  const { data: locations, isLoading, isError, refetch } =
    useOwnerLocations("month", "");

  const [storeIds, setStoreIds] = useState<number[]>([]);
  const [results, setResults] =
    useState<OwnerCrossStoreResultRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Per-field "apply this one" toggles + values.
  const [applyTz, setApplyTz]                 = useState(false);
  const [tz, setTz]                           = useState("America/Chicago");
  const [applyFedTax, setApplyFedTax]         = useState(false);
  const [fedTaxPct, setFedTaxPct]             = useState("1.00");
  const [applyEnforceHours, setApplyEnforceHours] = useState(false);
  const [enforceHours, setEnforceHours]       = useState(false);
  const [applyPasskey, setApplyPasskey]       = useState(false);
  const [passkeyOn, setPasskeyOn]             = useState(false);
  const [applyPhone, setApplyPhone]           = useState(false);
  const [phone, setPhone]                     = useState("");
  const [applyAddress, setApplyAddress]       = useState(false);
  const [address, setAddress]                 = useState("");

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
        <PageHeader title="Cross-store defaults" />
        <Empty>This page is owner-only.</Empty>
      </PageShell>
    );
  }

  function toggleStore(id: number) {
    setStoreIds((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id],
    );
  }
  function toggleAll() {
    setStoreIds(allSelected ? [] : [...allStoreIds]);
  }

  const anyFieldChecked = applyTz || applyFedTax || applyEnforceHours
                          || applyPasskey || applyPhone || applyAddress;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null); setResults(null); setBusy(true);
    try {
      const body: OwnerCrossStoreDefaultsBody = { store_ids: storeIds };
      if (applyTz)             body.timezone               = tz;
      if (applyFedTax) {
        const v = Number(fedTaxPct);
        if (!Number.isFinite(v) || v < 0 || v > 100) {
          throw new Error("Federal tax rate must be 0-100 (percent).");
        }
        body.federal_tax_rate = v / 100;
      }
      if (applyEnforceHours)   body.enforce_business_hours    = enforceHours;
      if (applyPasskey)        body.timeclock_require_passkey = passkeyOn;
      if (applyPhone)          body.phone                     = phone;
      if (applyAddress)        body.address                   = address;
      const out = await applyCrossStoreDefaults(body);
      setResults(out.results);
    } catch (e2) {
      setErr(
        e2 instanceof ApiError ? e2.message
        : e2 instanceof Error ? e2.message
        : "Couldn't apply the cross-store defaults.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell maxWidth="60rem">

      <Breadcrumbs crumbs={[{ label: "Owner" }, { label: "Cross-store defaults" }]} />

      <PageHeader
        title="Cross-store defaults"
        subtitle="Push the same field defaults to every store you select. Pick which fields to apply with the checkboxes — unchecked fields stay untouched on every store."
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
          You don't have any stores connected to your umbrella
          yet. Mint a connect code from{" "}
          <code>/app/owner/connect</code> and share it with a
          store admin first.
        </Empty>
      )}

      {locations && locations.rows.length > 0 && (
        <form onSubmit={onSubmit}>
          <Card>
            <Section title="Fields to push">
              <Checkbox checked={applyTz} onChange={setApplyTz}>
                Timezone
                <span className={styles.fieldHint}>
                  — IANA name, e.g. <code>America/Chicago</code>
                </span>
              </Checkbox>
              {applyTz && (
                <Field label="Timezone">
                  <Select
                    value={tz}
                    onChange={(e) => setTz(e.target.value)}
                  >
                    {TIMEZONE_CHOICES.map((z) => (
                      <option key={z} value={z}>{z}</option>
                    ))}
                  </Select>
                </Field>
              )}

              <Checkbox checked={applyFedTax} onChange={setApplyFedTax}>
                Federal tax rate
                <span className={styles.fieldHint}>
                  — percent, 0-100. Server stores as a decimal
                  (1.00% → 0.01).
                </span>
              </Checkbox>
              {applyFedTax && (
                <Field label="Federal tax rate (%)">
                  <Input
                    type="number" min="0" max="100" step="0.01"
                    value={fedTaxPct}
                    onChange={(e) => setFedTaxPct(e.target.value)}
                  />
                </Field>
              )}

              <Checkbox checked={applyEnforceHours} onChange={setApplyEnforceHours}>
                Block transfers outside business hours
              </Checkbox>
              {applyEnforceHours && (
                <Field label="State">
                  <Select
                    value={enforceHours ? "on" : "off"}
                    onChange={(e) => setEnforceHours(e.target.value === "on")}
                  >
                    <option value="off">Off (default)</option>
                    <option value="on">On — refuse out-of-hours saves</option>
                  </Select>
                </Field>
              )}

              <Checkbox checked={applyPasskey} onChange={setApplyPasskey}>
                Require passkey on time-clock punches
              </Checkbox>
              {applyPasskey && (
                <Field label="State">
                  <Select
                    value={passkeyOn ? "on" : "off"}
                    onChange={(e) => setPasskeyOn(e.target.value === "on")}
                  >
                    <option value="off">Off (default)</option>
                    <option value="on">On — refuse punches without passkey</option>
                  </Select>
                </Field>
              )}

              <div className={styles.fieldGrid}>
                <div>
                  <Checkbox checked={applyPhone} onChange={setApplyPhone}>
                    Phone
                  </Checkbox>
                  {applyPhone && (
                    <Field label="Phone">
                      <Input
                        type="tel" value={phone} maxLength={40}
                        onChange={(e) => setPhone(e.target.value)}
                      />
                    </Field>
                  )}
                </div>
                <div>
                  <Checkbox checked={applyAddress} onChange={setApplyAddress}>
                    Address
                  </Checkbox>
                  {applyAddress && (
                    <Field label="Address">
                      <Input
                        type="text" value={address} maxLength={255}
                        onChange={(e) => setAddress(e.target.value)}
                      />
                    </Field>
                  )}
                </div>
              </div>
            </Section>

            <Section title="Apply to stores">
              <div className={styles.toolbar}>
                <Button
                  type="button" tone="secondary" size="sm"
                  onClick={toggleAll}
                >
                  {allSelected ? "Clear all" : "Select all"}
                </Button>
                <span className={styles.toolbarCount}>
                  {storeIds.length} of {allStoreIds.length} selected
                </span>
              </div>
              <ul className={styles.storeList}>
                {locations.rows.map((s) => (
                  <li key={s.store_id}>
                    <Checkbox
                      checked={storeIds.includes(s.store_id)}
                      onChange={() => toggleStore(s.store_id)}
                    >
                      <span className={styles.storeName}>{s.store_name}</span>
                      <span className={styles.storeSlug}>{s.store_slug}</span>
                    </Checkbox>
                  </li>
                ))}
              </ul>
            </Section>

            {err && <Alert tone="error">{err}</Alert>}

            <div className={styles.actions}>
              <Button
                type="submit"
                busy={busy}
                disabled={
                  busy
                  || storeIds.length === 0
                  || !anyFieldChecked
                }
              >
                {busy
                  ? "Applying…"
                  : `Apply to ${storeIds.length} store${storeIds.length === 1 ? "" : "s"}`}
              </Button>
            </div>
          </Card>
        </form>
      )}

      {results && <ResultsCard rows={results} />}
    </PageShell>
  );
}


function ResultsCard({ rows }: { rows: OwnerCrossStoreResultRow[] }) {
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
            {rows.map((r) => (
              <tr key={r.store_id}>
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

function StatusPill({ status }: { status: OwnerCrossStoreResultRow["status"] }) {
  if (status === "updated")  return <Pill tone="accent">Updated</Pill>;
  return <Pill tone="negative">Rejected</Pill>;
}
