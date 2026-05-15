import { useState } from "react";

import { useTaxExportYears } from "../api/account";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, ErrorState, Field, PageHeader, PageShell,
  Section, Select,
} from "../components/ui";
import styles from "./AdminTaxExport.module.css";

// /app/admin/tax-export — year-end packet picker + download link.
//
// Picks a calendar year, then hands off to the legacy Flask route
// `/admin/tax-export.zip` (which streams a multi-MB ZIP via
// send_file). The ZIP-build Flask route is deliberately not
// migrated yet: it composes a swathe of `_tax_pack_*_csv` helpers
// that don't pay back the porting cost yet.

export default function AdminTaxExport() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useTaxExportYears();
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  if (identity?.role !== "admin" && identity?.role !== "owner") {
    return (
      <PageShell maxWidth="48rem">
        <PageHeader title="Tax Export Pack" />
        <Empty>You need a store-admin sign-in to download tax packs.</Empty>
      </PageShell>
    );
  }

  const year = selectedYear ?? data?.default_year ?? new Date().getFullYear() - 1;

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

            <ButtonLink
              href={`/admin/tax-export.zip?year=${year}`}
              tone="primary"
            >
              Download {year} pack (.zip)
            </ButtonLink>
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
