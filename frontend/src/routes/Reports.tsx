import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useByDestinationCountry,
  useSalesByCompany,
  useSalesByService,
  useTopRecipients,
  type AggregatedRowBase,
  type AggregatedTotals,
  type ReportEnvelope,
} from "../api/reports";
import { getCurrentIdentity } from "../lib/auth";

// /app/reports — period-scoped sales reports. Four cards:
//   • Sales by company
//   • Sales by service type
//   • By destination country
//   • Top recipients
//
// Same date-picker scopes all four. Defaults to month-to-date.
// Each card is its own query — slow ones don't block fast ones.
//
// All endpoints already exist on /api/v2/reports/*. No backend
// change.

function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function firstOfMonthIso(): string {
  const d = new Date();
  d.setDate(1);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function Reports() {
  const identity = getCurrentIdentity();
  const [searchParams, setSearchParams] = useSearchParams();

  const fromParam = searchParams.get("from");
  const toParam   = searchParams.get("to");

  // Default to month-to-date on first paint.
  useEffect(() => {
    if (!fromParam || !toParam) {
      const params = new URLSearchParams(searchParams);
      if (!fromParam) params.set("from", firstOfMonthIso());
      if (!toParam)   params.set("to",   todayIso());
      setSearchParams(params, { replace: true });
    }
  }, [fromParam, toParam, searchParams, setSearchParams]);

  const from = fromParam ?? firstOfMonthIso();
  const to   = toParam   ?? todayIso();

  function setRange(key: "from" | "to", value: string) {
    const params = new URLSearchParams(searchParams);
    params.set(key, value);
    setSearchParams(params, { replace: true });
  }

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Reports</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to view this store's reports.
        </p>
      </main>
    );
  }

  const company  = useSalesByCompany({ from, to });
  const service  = useSalesByService({ from, to });
  const country  = useByDestinationCountry({ from, to });
  const recip    = useTopRecipients({ from, to });

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>Reports</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
            fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
            fontSize: "0.95rem",
          }}
        >
          {from} → {to}
        </p>
      </header>

      <section
        style={{
          ...cardStyle,
          marginBottom: "1rem",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.75rem",
        }}
      >
        <Field label="From">
          <input
            type="date"
            value={from}
            onChange={(e) => setRange("from", e.target.value)}
            style={inputStyle}
          />
        </Field>
        <Field label="To">
          <input
            type="date"
            value={to}
            onChange={(e) => setRange("to", e.target.value)}
            style={inputStyle}
          />
        </Field>
      </section>

      <ReportCard
        title="Sales by company"
        envelope={company.data}
        loading={company.isLoading}
        error={company.error}
        identityKey="company"
      />
      <ReportCard
        title="Sales by service type"
        envelope={service.data}
        loading={service.isLoading}
        error={service.error}
        identityKey="service_type"
      />
      <ReportCard
        title="By destination country"
        envelope={country.data}
        loading={country.isLoading}
        error={country.error}
        identityKey="country"
      />
      <ReportCard
        title="Top recipients"
        envelope={recip.data}
        loading={recip.isLoading}
        error={recip.error}
        identityKey="recipient"
      />
    </main>
  );
}

interface ReportCardProps<R extends AggregatedRowBase> {
  title: string;
  envelope: ReportEnvelope<R> | undefined;
  loading: boolean;
  error: unknown;
  identityKey: keyof R & string;
}

function ReportCard<R extends AggregatedRowBase>({
  title, envelope, loading, error, identityKey,
}: ReportCardProps<R>) {
  return (
    <section style={{ ...cardStyle, marginBottom: "1rem" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "1rem",
          gap: "1rem",
        }}
      >
        <h2 style={sectionTitleStyle}>{title}</h2>
        {envelope && (
          <TotalsLine totals={envelope.totals} />
        )}
      </header>
      {loading && <Empty>Loading…</Empty>}
      {error != null && (
        <Empty error>
          {error instanceof Error ? error.message : "Could not load"}
        </Empty>
      )}
      {envelope && envelope.rows.length === 0 && !loading && (
        <Empty>No data in this period.</Empty>
      )}
      {envelope && envelope.rows.length > 0 && (
        <ReportTable
          rows={envelope.rows}
          identityHeader={identityHeaderFor(identityKey)}
          identityKey={identityKey}
        />
      )}
    </section>
  );
}

function identityHeaderFor(key: string): string {
  switch (key) {
    case "company":      return "Company";
    case "service_type": return "Service type";
    case "country":      return "Country";
    case "recipient":    return "Recipient";
    default:             return key;
  }
}

function TotalsLine({ totals }: { totals: AggregatedTotals }) {
  return (
    <span
      style={{
        fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
        fontSize: "0.85rem",
        color: "var(--db-text-muted, #a3a3a3)",
      }}
    >
      {totals.count.toLocaleString()} txns · ${totals.sent.toFixed(2)} sent
      · ${totals.fees.toFixed(2)} fees
    </span>
  );
}

function ReportTable<R extends AggregatedRowBase>({
  rows, identityHeader, identityKey,
}: {
  rows: R[];
  identityHeader: string;
  identityKey: keyof R & string;
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}>
        <thead>
          <tr>
            {[identityHeader, "Count", "Sent", "Fees", "Tax", "Avg"].map((h, i, a) => (
              <th
                key={h}
                style={{
                  textAlign: i === 0 ? "left" : "right",
                  padding: "0.6rem 0.75rem",
                  color: "var(--db-text-muted, #a3a3a3)",
                  fontWeight: 500,
                  fontSize: "0.78rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  borderBottom: "1px solid var(--db-border, #262626)",
                }}
              >
                {h}
                {i === a.length - 1 ? "" : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={cellStyle}>
                {String(r[identityKey] || "—")}
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>{r.count}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.sent.toFixed(2)}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.fees.toFixed(2)}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.tax.toFixed(2)}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.avg.toFixed(2)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Field({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <span
        style={{
          fontSize: "0.78rem",
          color: "var(--db-text-muted, #a3a3a3)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}

function Empty({
  children, error,
}: { children: React.ReactNode; error?: boolean }) {
  return (
    <p
      style={{
        margin: 0,
        padding: "1.5rem 0",
        textAlign: "center",
        color: error
          ? "var(--db-negative, #ff3b30)"
          : "var(--db-text-muted, #a3a3a3)",
      }}
    >
      {children}
    </p>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2.5rem 1.5rem",
  maxWidth: "78rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.75rem, 4vw, 2.5rem)",
  fontWeight: 600,
  margin: 0,
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "1.05rem",
  fontWeight: 500,
  margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.9rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const cellStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const mono: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
