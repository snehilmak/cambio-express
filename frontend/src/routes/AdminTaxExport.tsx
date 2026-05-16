import { useState } from "react";

import { useTaxExportYears } from "../api/account";
import { downloadCsv } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Button, Card, Empty, ErrorState, Field, PageHeader, PageShell,
  Section, Select,
} from "../components/ui";
import styles from "./AdminTaxExport.module.css";

// /app/admin/tax-export — year-end packet picker + download.
//
// Picks a calendar year and triggers
// ``GET /api/v2/admin/tax-export.zip?year=<n>``. The download
// goes through ``downloadCsv`` (a misnamed generic blob-download
// helper) so the bearer token is attached — a plain ``<a href>``
// would do an unauthed top-level navigation and 401.

export default function AdminTaxExport() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useTaxExportYears();
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string>("");

  if (identity?.role !== "admin" && identity?.role !== "owner") {
    return (
      <PageShell maxWidth="48rem">
        <PageHeader title="Tax Export Pack" />
        <Empty>You need a store-admin sign-in to download tax packs.</Empty>
      </PageShell>
    );
  }

  const year = selectedYear ?? data?.default_year ?? new Date().getFullYear() - 1;

  async function onDownload() {
    setDownloading(true);
    setDownloadError("");
    try {
      await downloadCsv(
        `/api/v2/admin/tax-export.zip?year=${year}`,
        `tax-pack-${year}.zip`,
      );
    } catch (err) {
      setDownloadError(
        err instanceof Error ? err.message : "Download failed",
      );
    } finally {
      setDownloading(false);
    }
  }

  return (
    <PageShell maxWidth="48rem">
      <PageHeader title="Tax Export Pack" />

      <Section title="Year-end packet">
        <Card padding="1.5rem">
          <p className={styles.lead}>
            Download every transfer, every monthly P&amp;L, and every
            closed daily book for a calendar year as a single ZIP. Hand
            the ZIP to your accountant — the README inside explains
            each file.
          </p>

          {isError && (
            <ErrorState
              message={`Couldn't load the year list: ${error instanceof Error ? error.message : "unknown error"}`}
              onRetry={() => { void refetch(); }}
            />
          )}

          {downloadError && (
            <ErrorState
              message={`Couldn't build the ZIP: ${downloadError}`}
              onRetry={() => { void onDownload(); }}
            />
          )}

          <div className={styles.controls}>
            <Field label="Year" style={{ minWidth: "10rem" }}>
              <Select
                value={year}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                disabled={isLoading || !data}
              >
                {(data?.years ?? [year]).map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </Select>
            </Field>

            <Button
              type="button"
              tone="primary"
              onClick={() => { void onDownload(); }}
              disabled={downloading}
            >
              {downloading
                ? "Building ZIP…"
                : `Download ${year} pack (.zip)`}
            </Button>
          </div>

          <div className={styles.infoBox}>
            <div className={styles.infoHeading}>What's inside</div>
            <ul className={styles.list}>
              <li>
                <strong>transfers_{year}.csv</strong> — full transfer
                ledger including Canceled / Rejected rows. Use the
                Status column to filter to revenue-bearing transfers.
              </li>
              <li>
                <strong>monthly_pl_{year}.csv</strong> — month-by-month
                P&amp;L roll-up matching the Monthly P&amp;L page. Net
                Income is income − expenses for the month.
              </li>
              <li>
                <strong>daily_summary_{year}.csv</strong> — one row per
                closed daily book. Cross-check against bank deposits.
              </li>
              <li>
                <strong>customers_{year}.csv</strong> — per-customer
                totals (count, total sent, fees). Starting point for
                1099-MISC if any single customer crossed the IRS
                reporting threshold.
              </li>
              <li>
                <strong>README.txt</strong> — plain-text key explaining
                each file.
              </li>
            </ul>
          </div>

          <p className={styles.fine}>
            All money values are USD. Send amounts are what the customer
            handed over; fees are what the store retained; federal tax
            is the portion that left with the ACH withdrawal (not store
            revenue).
          </p>
        </Card>
      </Section>
    </PageShell>
  );
}
