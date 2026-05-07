import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { useDailyReport, type DailyReportRow } from "../api/dailybook";
import { getCurrentIdentity } from "../lib/auth";

// Daily book page at /app/daily. Read-only view of a single
// day's roll-up:
//
//   ?date=YYYY-MM-DD   active report date (defaults to today)
//
// Backed by GET /api/v2/daily/{store_id}/{date}. The save / lock
// / unlock flows still live in the legacy Jinja /daily-book
// page; write-side migration lands in SPA-N.

function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function DailyBook() {
  const identity = getCurrentIdentity();
  const [searchParams, setSearchParams] = useSearchParams();
  const dateParam = searchParams.get("date");

  // Initialize the URL with today on first paint when no ?date=
  // is set, so reload + bookmarks land on a deterministic value.
  useEffect(() => {
    if (!dateParam) {
      const params = new URLSearchParams(searchParams);
      params.set("date", todayIso());
      setSearchParams(params, { replace: true });
    }
  }, [dateParam, searchParams, setSearchParams]);

  const date = dateParam ?? todayIso();
  const { data, isLoading, isError, error, isFetching } = useDailyReport(date);

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Daily book</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to view the daily book.
        </p>
      </main>
    );
  }

  function setDate(next: string) {
    const params = new URLSearchParams(searchParams);
    params.set("date", next);
    setSearchParams(params, { replace: true });
  }

  function shiftDate(deltaDays: number) {
    const d = new Date(`${date}T12:00:00`);
    d.setDate(d.getDate() + deltaDays);
    const pad = (n: number) => n.toString().padStart(2, "0");
    setDate(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    );
  }

  return (
    <main style={pageStyle}>
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <div>
          <h1 style={titleStyle}>Daily book</h1>
          <p
            style={{
              margin: "0.35rem 0 0",
              color: "var(--db-text-muted, #a3a3a3)",
              fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            {date}
            {data?.locked && (
              <span
                style={{
                  marginLeft: "0.75rem",
                  fontSize: "0.78rem",
                  padding: "0.15rem 0.5rem",
                  borderRadius: "999px",
                  background: "var(--db-warning-bg, #2a1a00)",
                  color: "var(--db-warning, #ffb84d)",
                  letterSpacing: "0.05em",
                }}
              >
                LOCKED
              </span>
            )}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button onClick={() => shiftDate(-1)} style={dateBtnStyle}>
            ← Day
          </button>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={dateInputStyle}
          />
          <button onClick={() => shiftDate(1)} style={dateBtnStyle}>
            Day →
          </button>
        </div>
      </header>

      {isLoading && <p style={emptyStyle}>Loading…</p>}
      {isError && (
        <p style={{ ...emptyStyle, color: "var(--db-negative, #ff3b30)" }}>
          {error instanceof Error ? error.message : "Could not load report"}
        </p>
      )}
      {!isLoading && !isError && data == null && (
        <p style={emptyStyle}>
          No daily report logged for this date.
          {isFetching ? " Updating…" : ""}
        </p>
      )}
      {data && <ReportContent r={data} />}
    </main>
  );
}

function ReportContent({ r }: { r: DailyReportRow }) {
  return (
    <>
      <Section title="Totals">
        <Grid>
          <Stat label="Total receipts"     value={r.total_receipts} positive />
          <Stat label="Total disbursements" value={r.total_disbursements} />
          <Stat
            label="Net"
            value={r.net}
            positive={r.net >= 0}
            negative={r.net < 0}
          />
          <Stat label="Over / short"       value={r.over_short}
                negative={r.over_short < 0} />
          <Stat label="Safe balance"       value={r.safe_balance} />
        </Grid>
      </Section>

      <Section title="Receipts">
        <Grid>
          <Stat label="Taxable sales"  value={r.taxable_sales} />
          <Stat label="Non-taxable"    value={r.non_taxable} />
          <Stat label="Sales tax"      value={r.sales_tax} />
          <Stat label="Money transfer" value={r.money_transfer} />
          <Stat label="Money order"    value={r.money_order} />
        </Grid>
      </Section>

      <Section title="Disbursements">
        <Grid>
          <Stat label="Cash expense"    value={r.cash_expense} />
          <Stat label="Check expense"   value={r.check_expense} />
          <Stat label="Cash deposit"    value={r.cash_deposit} />
          <Stat label="Checks deposit"  value={r.checks_deposit} />
        </Grid>
      </Section>

      {r.notes && (
        <Section title="Notes">
          <p
            style={{
              margin: 0,
              color: "var(--db-text, #f5f5f5)",
              whiteSpace: "pre-wrap",
              lineHeight: 1.6,
            }}
          >
            {r.notes}
          </p>
        </Section>
      )}
    </>
  );
}

function Section({
  title, children,
}: { title: string; children: React.ReactNode }) {
  return (
    <section style={cardStyle}>
      <h2
        style={{
          fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
          fontSize: "0.95rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--db-text-muted, #a3a3a3)",
          margin: "0 0 1rem",
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))",
        gap: "0.75rem",
      }}
    >
      {children}
    </div>
  );
}

function Stat({
  label, value, positive, negative,
}: {
  label: string;
  value: number;
  positive?: boolean;
  negative?: boolean;
}) {
  const color = positive
    ? "var(--db-accent, #3fff00)"
    : negative
      ? "var(--db-negative, #ff3b30)"
      : "var(--db-text, #f5f5f5)";
  return (
    <div
      style={{
        background: "var(--db-surface, #0a0a0a)",
        border: "1px solid var(--db-border-subtle, #1f1f1f)",
        borderRadius: "0.5rem",
        padding: "0.75rem 0.9rem",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "0.78rem",
          color: "var(--db-text-muted, #a3a3a3)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </p>
      <p
        style={{
          margin: "0.25rem 0 0",
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
          fontSize: "1.2rem",
          fontWeight: 500,
          color,
        }}
      >
        ${value.toFixed(2)}
      </p>
    </div>
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
  gap: "1rem",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.75rem, 4vw, 2.5rem)",
  fontWeight: 600,
  margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
};

const dateBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.45rem 0.75rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.85rem",
  cursor: "pointer",
};

const dateInputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.45rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.9rem",
  outline: "none",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
