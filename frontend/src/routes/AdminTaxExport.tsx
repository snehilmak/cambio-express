import { useState } from "react";

import { useTaxExportYears } from "../api/account";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, ErrorState, PageHeader, PageShell, Section, tokens,
} from "../components/ui";

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
          <p style={leadStyle}>
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

          <div style={controlsStyle}>
            <label style={labelStyle}>
              <span style={labelTextStyle}>Year</span>
              <select
                value={year}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                disabled={isLoading || !data}
                style={selectStyle}
              >
                {(data?.years ?? [year]).map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </label>

            <ButtonLink
              href={`/admin/tax-export.zip?year=${year}`}
              tone="primary"
            >
              Download {year} pack (.zip)
            </ButtonLink>
          </div>

          <div style={infoBoxStyle}>
            <div style={{ fontWeight: 600, marginBottom: "0.4rem" }}>
              What's inside
            </div>
            <ul style={listStyle}>
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

          <p style={fineStyle}>
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


const leadStyle: React.CSSProperties = {
  margin: 0, color: tokens.textMuted,
  fontSize: "0.95rem", lineHeight: 1.55,
};

const controlsStyle: React.CSSProperties = {
  marginTop: "1.25rem", display: "flex", flexWrap: "wrap",
  gap: "0.75rem", alignItems: "flex-end",
};

const labelStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column", gap: "0.35rem",
  minWidth: "10rem",
};

const labelTextStyle: React.CSSProperties = {
  fontSize: "0.7rem", letterSpacing: "0.06em",
  textTransform: "uppercase", fontWeight: 600,
  color: tokens.textMuted,
};

const selectStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  background: "var(--db-bg-input, #0d0d0d)",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem", fontSize: "0.95rem",
};

const infoBoxStyle: React.CSSProperties = {
  marginTop: "1.5rem", padding: "1rem 1.1rem",
  background: "rgba(94,169,255,0.08)",
  border: "1px solid rgba(94,169,255,0.3)",
  borderRadius: "0.6rem", color: "var(--db-info, #5ea9ff)",
  fontSize: "0.9rem", lineHeight: 1.55,
};

const listStyle: React.CSSProperties = {
  margin: 0, paddingLeft: "1.25rem",
  color: tokens.textMuted,
  fontSize: "0.88rem", lineHeight: 1.7,
};

const fineStyle: React.CSSProperties = {
  marginTop: "1rem", color: tokens.textMuted,
  fontSize: "0.85rem", lineHeight: 1.55,
};
