import { useState } from "react";

import { useTaxExportYears } from "../api/account";
import { downloadCsv } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, Empty, Field, Input, PageHeader, PageShell,
  Section, Select,
} from "../components/ui";
import styles from "./AdminDataExport.module.css";

// /app/admin/data-export — single hub for every authed CSV /
// ZIP download the admin can pull. Catalogs the scattered
// export endpoints (customers, tax pack, transfers) with
// inline pickers so the operator doesn't have to remember
// which page hosts which download.
//
// Useful for GDPR-style data-portability requests + new-store
// onboarding ("show me what I'll be able to get back out").

export default function AdminDataExport() {
  const identity = getCurrentIdentity();
  const taxYears = useTaxExportYears();

  // Tax-pack year picker. Default to last year (matches the
  // standalone /app/admin/tax-export page).
  const [taxYear, setTaxYear] = useState<number | null>(null);
  const [taxBusy, setTaxBusy] = useState(false);
  const [taxErr, setTaxErr] = useState("");

  // Customers CSV — one-click, no picker.
  const [customersBusy, setCustomersBusy] = useState(false);
  const [customersErr, setCustomersErr] = useState("");

  // Transfers CSV — date range picker. Default to last 30 days.
  const today = new Date();
  const lastMonth = new Date(today);
  lastMonth.setDate(today.getDate() - 30);
  const [transFrom, setTransFrom] = useState(_isoDate(lastMonth));
  const [transTo,   setTransTo]   = useState(_isoDate(today));
  const [transBusy, setTransBusy] = useState(false);
  const [transErr,  setTransErr]  = useState("");

  // Time-clock entries CSV — same default window as transfers.
  const [tcFrom, setTcFrom] = useState(_isoDate(lastMonth));
  const [tcTo,   setTcTo]   = useState(_isoDate(today));
  const [tcBusy, setTcBusy] = useState(false);
  const [tcErr,  setTcErr]  = useState("");

  // Audit log CSV — one click, no picker (server applies
  // the same filters as the audit page on its own).
  const [auditBusy, setAuditBusy] = useState(false);
  const [auditErr,  setAuditErr]  = useState("");

  if (identity?.role !== "admin"
      && identity?.role !== "owner"
      && identity?.role !== "superadmin") {
    return (
      <PageShell maxWidth="56rem">
        <PageHeader title="Data export" subtitle="Download your store data as CSV or ZIP." />
        <Empty>
          You need a store-admin sign-in to pull data exports.
        </Empty>
      </PageShell>
    );
  }

  const resolvedTaxYear = taxYear
    ?? taxYears.data?.default_year
    ?? new Date().getFullYear() - 1;

  async function onDownloadTaxPack() {
    setTaxBusy(true); setTaxErr("");
    try {
      await downloadCsv(
        `/api/v2/admin/tax-export.zip?year=${resolvedTaxYear}`,
        `tax-pack-${resolvedTaxYear}.zip`,
      );
    } catch (e) {
      setTaxErr(e instanceof Error ? e.message : "Download failed.");
    } finally {
      setTaxBusy(false);
    }
  }

  async function onDownloadCustomers() {
    setCustomersBusy(true); setCustomersErr("");
    try {
      await downloadCsv(
        "/api/v2/customers/export.csv",
        `customers-${_isoDate(today)}.csv`,
      );
    } catch (e) {
      setCustomersErr(e instanceof Error ? e.message : "Download failed.");
    } finally {
      setCustomersBusy(false);
    }
  }

  async function onDownloadTransfers() {
    setTransBusy(true); setTransErr("");
    try {
      // ``store_ids`` is required by the reports CSV endpoint
      // — leave it empty so the server falls back to the JWT
      // principal's home store via owner-umbrella resolution.
      const url = `/api/v2/reports/transfers.csv`
        + `?from=${encodeURIComponent(transFrom)}`
        + `&to=${encodeURIComponent(transTo)}`
        + `&store_ids=`;
      await downloadCsv(url, `transfers-${transFrom}-to-${transTo}.csv`);
    } catch (e) {
      setTransErr(e instanceof Error ? e.message : "Download failed.");
    } finally {
      setTransBusy(false);
    }
  }

  async function onDownloadTimeClock() {
    setTcBusy(true); setTcErr("");
    try {
      const url = `/api/v2/admin/timeclock.csv`
        + `?from=${encodeURIComponent(tcFrom)}`
        + `&to=${encodeURIComponent(tcTo)}`;
      await downloadCsv(url, `timeclock-${tcFrom}-to-${tcTo}.csv`);
    } catch (e) {
      setTcErr(e instanceof Error ? e.message : "Download failed.");
    } finally {
      setTcBusy(false);
    }
  }

  async function onDownloadAuditLog() {
    setAuditBusy(true); setAuditErr("");
    try {
      await downloadCsv(
        "/api/v2/admin/audit-log.csv",
        `audit-log-${_isoDate(today)}.csv`,
      );
    } catch (e) {
      setAuditErr(e instanceof Error ? e.message : "Download failed.");
    } finally {
      setAuditBusy(false);
    }
  }

  return (
    <PageShell maxWidth="56rem">

      <Breadcrumbs crumbs={[{ label: "Finance" }, { label: "Data export" }]} />

      <PageHeader
        title="Data export"
        subtitle="Pull a single dataset or every year-end record at once. All downloads stream over your authenticated session."
      />

      <Card>
        <Section title="Year-end tax pack (ZIP)">
          <p className={styles.intro}>
            Bundles every transfer, monthly P&amp;L, and closed daily
            book for a calendar year into one ZIP. Pair with the
            included README and hand the file to your accountant.
          </p>
          {taxErr && (
            <Alert tone="error">{taxErr}</Alert>
          )}
          <div className={styles.exportRow}>
            <div className={styles.exportText}>
              <div className={styles.exportName}>Tax pack</div>
              <div className={styles.exportDesc}>
                Tax year: pick from the dropdown.
              </div>
            </div>
            <div className={styles.exportControls}>
              <Field label="Year" style={{ minWidth: "10rem" }}>
                <Select
                  value={resolvedTaxYear}
                  onChange={(e) => setTaxYear(Number(e.target.value))}
                  disabled={taxYears.isLoading || !taxYears.data}
                >
                  {(taxYears.data?.years ?? [resolvedTaxYear]).map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </Select>
              </Field>
              <Button
                tone="primary"
                onClick={() => { void onDownloadTaxPack(); }}
                busy={taxBusy} disabled={taxBusy}
              >
                {taxBusy ? "Building…" : "Download ZIP"}
              </Button>
            </div>
          </div>
        </Section>
      </Card>

      <Card>
        <Section title="Customer directory">
          <p className={styles.intro}>
            Every customer row visible across your stores
            (alphabetical), masked-phone-disabled — useful for
            CRM exports + GDPR data-portability requests.
          </p>
          {customersErr && (
            <Alert tone="error">{customersErr}</Alert>
          )}
          <div className={styles.exportRow}>
            <div className={styles.exportText}>
              <div className={styles.exportName}>Customers CSV</div>
              <div className={styles.exportDesc}>
                Full directory snapshot.
              </div>
            </div>
            <div className={styles.exportControls}>
              <Button
                tone="primary"
                onClick={() => { void onDownloadCustomers(); }}
                busy={customersBusy} disabled={customersBusy}
              >
                {customersBusy ? "Preparing…" : "Download CSV"}
              </Button>
            </div>
          </div>
        </Section>
      </Card>

      <Card>
        <Section title="Transfers (custom range)">
          <p className={styles.intro}>
            Every transfer in the window — including pending,
            sent, and canceled. Use the date pickers for narrow
            slices (last week's batch, a specific quarter, etc.).
          </p>
          {transErr && (
            <Alert tone="error">{transErr}</Alert>
          )}
          <div className={styles.exportRow}>
            <div className={styles.exportText}>
              <div className={styles.exportName}>Transfers CSV</div>
              <div className={styles.exportDesc}>
                Defaults to the last 30 days.
              </div>
            </div>
            <div className={styles.exportControls}>
              <Field label="From" style={{ minWidth: "9rem" }}>
                <Input
                  type="date"
                  value={transFrom}
                  onChange={(e) => setTransFrom(e.target.value)}
                />
              </Field>
              <Field label="To" style={{ minWidth: "9rem" }}>
                <Input
                  type="date"
                  value={transTo}
                  onChange={(e) => setTransTo(e.target.value)}
                />
              </Field>
              <Button
                tone="primary"
                onClick={() => { void onDownloadTransfers(); }}
                busy={transBusy} disabled={transBusy}
              >
                {transBusy ? "Preparing…" : "Download CSV"}
              </Button>
            </div>
          </div>
        </Section>
      </Card>

      <Card>
        <Section title="Time-clock entries (custom range)">
          <p className={styles.intro}>
            Every clock-in / clock-out in the window plus the
            derived late-minutes and adjusted-after-the-fact
            flags. Plugs straight into a payroll spreadsheet.
          </p>
          {tcErr && (
            <Alert tone="error">{tcErr}</Alert>
          )}
          <div className={styles.exportRow}>
            <div className={styles.exportText}>
              <div className={styles.exportName}>Time-clock CSV</div>
              <div className={styles.exportDesc}>
                Defaults to the last 30 days.
              </div>
            </div>
            <div className={styles.exportControls}>
              <Field label="From" style={{ minWidth: "9rem" }}>
                <Input
                  type="date"
                  value={tcFrom}
                  onChange={(e) => setTcFrom(e.target.value)}
                />
              </Field>
              <Field label="To" style={{ minWidth: "9rem" }}>
                <Input
                  type="date"
                  value={tcTo}
                  onChange={(e) => setTcTo(e.target.value)}
                />
              </Field>
              <Button
                tone="primary"
                onClick={() => { void onDownloadTimeClock(); }}
                busy={tcBusy} disabled={tcBusy}
              >
                {tcBusy ? "Preparing…" : "Download CSV"}
              </Button>
            </div>
          </div>
        </Section>
      </Card>

      <Card>
        <Section title="Audit log">
          <p className={styles.intro}>
            Every operator + transfer audit row for this store —
            who did what, when, with the before/after summary
            line. Useful for compliance or for investigating a
            disputed change.
          </p>
          {auditErr && (
            <Alert tone="error">{auditErr}</Alert>
          )}
          <div className={styles.exportRow}>
            <div className={styles.exportText}>
              <div className={styles.exportName}>Audit log CSV</div>
              <div className={styles.exportDesc}>
                Full operator + transfer audit trail.
              </div>
            </div>
            <div className={styles.exportControls}>
              <Button
                tone="primary"
                onClick={() => { void onDownloadAuditLog(); }}
                busy={auditBusy} disabled={auditBusy}
              >
                {auditBusy ? "Preparing…" : "Download CSV"}
              </Button>
            </div>
          </div>
        </Section>
      </Card>

      <Card>
        <Section title="More report CSVs">
          <p className={styles.intro}>
            Every report under <code>/app/reports</code> exposes
            a CSV export via the toolbar — open the report,
            adjust filters, click "Export CSV". This page
            consolidates the everyday downloads; specialized
            BI exports live on each report page.
          </p>
        </Section>
      </Card>
    </PageShell>
  );
}


function _isoDate(d: Date): string {
  const yy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}
