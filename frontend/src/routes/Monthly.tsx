import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useLoggedMonths, useMonthly, type MonthlyRow } from "../api/monthly";
import { getCurrentIdentity } from "../lib/auth";

// Monthly P&L at /app/monthly?year=Y&month=M.
//
// Read-only for now; the legacy /monthly/<year>/<month> Jinja
// page handles edits + the auto-derived bank-charges/line-item
// totals. Defaults to the most recent logged month for the store.

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const INCOME_FIELDS: Array<{ key: keyof MonthlyRow; label: string }> = [
  { key: "taxable_sales",          label: "Taxable sales" },
  { key: "non_taxable",            label: "Non-taxable" },
  { key: "bill_payment_charge",    label: "Bill payment charge" },
  { key: "phone_recargas",         label: "Phone recargas" },
  { key: "boost_mobile",           label: "Boost Mobile" },
  { key: "check_cashing_fees",     label: "Check cashing fees" },
  { key: "return_check_hold_fees", label: "Return check hold fees" },
  { key: "rebates_commissions",    label: "Rebates / commissions" },
  { key: "mt_commission_in_bank",  label: "MT commission in bank" },
  { key: "other_income_1",         label: "Other income 1" },
  { key: "other_income_2",         label: "Other income 2" },
  { key: "other_income_3",         label: "Other income 3" },
];

const EXPENSE_FIELDS: Array<{ key: keyof MonthlyRow; label: string }> = [
  { key: "cash_purchases",      label: "Cash purchases" },
  { key: "check_purchases",     label: "Check purchases" },
  { key: "cash_expenses",       label: "Cash expenses" },
  { key: "check_expenses",      label: "Check expenses" },
  { key: "cash_payroll",        label: "Cash payroll" },
  { key: "bank_charges_total",  label: "Bank charges" },
  { key: "credit_card_fees",    label: "Credit card fees" },
  { key: "money_order_rent",    label: "Money order rent" },
  { key: "emaginenet_tech",     label: "EmagineNet / tech" },
  { key: "irs_payroll_tax",     label: "IRS payroll tax" },
  { key: "texas_workforce",     label: "Texas workforce" },
  { key: "other_taxes",         label: "Other taxes" },
  { key: "accounting_charges",  label: "Accounting charges" },
  { key: "return_check_gl",     label: "Return check GL" },
  { key: "other_expense_1",     label: "Other expense 1" },
  { key: "other_expense_2",     label: "Other expense 2" },
  { key: "other_expense_3",     label: "Other expense 3" },
  { key: "other_expense_4",     label: "Other expense 4" },
  { key: "other_expense_5",     label: "Other expense 5" },
  { key: "over_short",          label: "Over / short" },
  { key: "borrowed_money_return", label: "Borrowed money return" },
  { key: "profit_distributed",  label: "Profit distributed" },
];

export default function Monthly() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const months = useLoggedMonths();

  const yearParam  = sp.get("year");
  const monthParam = sp.get("month");

  // Default to the most recent logged month on first paint.
  useEffect(() => {
    if (yearParam && monthParam) return;
    const first = months.data?.months[0];
    if (!first) return;
    const params = new URLSearchParams(sp);
    params.set("year",  String(first.year));
    params.set("month", String(first.month));
    setSP(params, { replace: true });
  }, [yearParam, monthParam, months.data, sp, setSP]);

  const year  = yearParam ? Number(yearParam) : undefined;
  const month = monthParam ? Number(monthParam) : undefined;
  const detail = useMonthly(year, month);

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Monthly P&L</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to view monthly P&L.
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header
        style={{
          marginBottom: "1.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <div>
          <h1 style={titleStyle}>Monthly P&L</h1>
          <p
            style={{
              margin: "0.35rem 0 0",
              color: "var(--db-text-muted, #a3a3a3)",
              fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            {year && month
              ? `${MONTH_NAMES[month - 1]} ${year}`
              : "—"}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <select
            value={year && month ? `${year}-${month}` : ""}
            onChange={(e) => {
              const v = e.target.value;
              if (!v) return;
              const [y, m] = v.split("-").map(Number);
              const params = new URLSearchParams(sp);
              params.set("year", String(y));
              params.set("month", String(m));
              setSP(params, { replace: true });
            }}
            style={pickerStyle}
          >
            {(months.data?.months ?? []).map((m) => (
              <option
                key={`${m.year}-${m.month}`}
                value={`${m.year}-${m.month}`}
              >
                {MONTH_NAMES[m.month - 1]} {m.year}
              </option>
            ))}
          </select>
          {year && month && (
            <Link
              to={`/monthly/edit?year=${year}&month=${month}`}
              style={{
                background: "var(--db-accent, #3fff00)",
                color: "var(--db-on-accent, #0a0a0a)",
                borderRadius: "0.5rem",
                padding: "0.45rem 0.85rem",
                fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
                fontSize: "0.85rem",
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              Edit
            </Link>
          )}
        </div>
      </header>

      {(months.data?.months.length ?? 0) === 0 && !months.isLoading && (
        <p style={emptyStyle}>
          No monthly P&L logged for this store yet. Log a month
          via the legacy /monthly page first.
        </p>
      )}

      {detail.isLoading && <p style={emptyStyle}>Loading…</p>}
      {detail.isError && (
        <p style={{ ...emptyStyle, color: "var(--db-negative, #ff3b30)" }}>
          {detail.error instanceof Error
            ? detail.error.message
            : "Could not load monthly report"}
        </p>
      )}
      {detail.data === null && !detail.isLoading && year && month && (
        <p style={emptyStyle}>
          No P&L logged for {MONTH_NAMES[month - 1]} {year} yet.
        </p>
      )}
      {detail.data && <ReportContent r={detail.data} />}
    </main>
  );
}

function ReportContent({ r }: { r: MonthlyRow }) {
  return (
    <>
      <Section title="Totals">
        <Grid>
          <Stat label="Total income"     value={r.total_income}   positive />
          <Stat label="Total expenses"   value={r.total_expenses} />
          <Stat
            label="Net profit"
            value={r.net_profit}
            positive={r.net_profit >= 0}
            negative={r.net_profit < 0}
          />
          <Stat label="Cash carry forward" value={r.cash_carry_forward} />
        </Grid>
      </Section>

      <Section title="Income">
        <Grid>
          {INCOME_FIELDS.map((f) => (
            <Stat
              key={f.key}
              label={f.label}
              value={r[f.key] as number}
            />
          ))}
        </Grid>
      </Section>

      <Section title="Expenses">
        <Grid>
          {EXPENSE_FIELDS.map((f) => (
            <Stat
              key={f.key}
              label={f.label}
              value={r[f.key] as number}
            />
          ))}
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
        gap: "0.6rem",
      }}
    >
      {children}
    </div>
  );
}

function Stat({
  label, value, positive, negative,
}: {
  label: string; value: number;
  positive?: boolean; negative?: boolean;
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
        padding: "0.6rem 0.8rem",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "0.72rem",
          color: "var(--db-text-muted, #a3a3a3)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </p>
      <p
        style={{
          margin: "0.2rem 0 0",
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
          fontSize: "1.05rem",
          fontWeight: 500,
          color,
        }}
      >
        ${(value || 0).toFixed(2)}
      </p>
    </div>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "78rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
  gap: "1rem",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
};

const pickerStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.5rem 0.75rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.9rem",
  outline: "none",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
