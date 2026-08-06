import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

import { useLoggedMonths, useMonthly, type MonthlyRow } from "../api/monthly";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  ButtonLink, Card, Empty, EmptyState, ErrorState, Loading, PageHeader,
  PageShell, Section, Select, tokens,
} from "../components/ui";
import styles from "./Monthly.module.css";

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
      <PageShell gap="1rem">
        <PageHeader title="Monthly P&L" />
        <Empty>Sign in as a store admin to view monthly P&amp;L.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell gap="1rem">

      <Breadcrumbs crumbs={[{ label: "Monthly P&L" }]} />

      <PageHeader
        title="Monthly P&L"
        subtitle={year && month ? (
          <span style={{ fontFamily: tokens.fontMono }}>
            {MONTH_NAMES[month - 1]} {year}
          </span>
        ) : "—"}
        actions={(
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <Select
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
              style={{ width: "auto" }}
            >
              {(months.data?.months ?? []).map((m) => (
                <option
                  key={`${m.year}-${m.month}`}
                  value={`${m.year}-${m.month}`}
                >
                  {MONTH_NAMES[m.month - 1]} {m.year}
                </option>
              ))}
            </Select>
            {year && month && (
              <ButtonLink
                to={`/monthly/edit?year=${year}&month=${month}`}
                tone="primary"
                size="sm"
              >
                Edit
              </ButtonLink>
            )}
          </div>
        )}
      />

      {(months.data?.months.length ?? 0) === 0 && !months.isLoading && (
        <EmptyState
          title="No monthly P&L logged yet"
          body="Log a month via the legacy /monthly page first."
        />
      )}

      {detail.isLoading && <Loading />}
      {detail.isError && (
        <ErrorState
          message={
            detail.error instanceof Error
              ? detail.error.message
              : "Could not load monthly report"
          }
          onRetry={() => { void detail.refetch(); }}
        />
      )}
      {detail.data === null && !detail.isLoading && year && month && (
        <EmptyState
          title={`No P&L logged for ${MONTH_NAMES[month - 1]} ${year} yet.`}
        />
      )}
      {detail.data && <ReportContent r={detail.data} />}
    </PageShell>
  );
}

function ReportContent({ r }: { r: MonthlyRow }) {
  return (
    <>
      <Section title="Totals">
        <Card>
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
        </Card>
      </Section>

      <Section title="Income">
        <Card>
          <Grid>
            {INCOME_FIELDS.map((f) => (
              <Stat
                key={f.key}
                label={f.label}
                value={r[f.key] as number}
              />
            ))}
          </Grid>
        </Card>
      </Section>

      <Section title="Expenses">
        <Card>
          <Grid>
            {EXPENSE_FIELDS.map((f) => (
              <Stat
                key={f.key}
                label={f.label}
                value={r[f.key] as number}
              />
            ))}
          </Grid>
        </Card>
      </Section>

      {r.notes && (
        <Section title="Notes">
          <Card>
            <p className={styles.notes}>{r.notes}</p>
          </Card>
        </Section>
      )}
    </>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return <div className={styles.grid}>{children}</div>;
}

function Stat({
  label, value, positive, negative,
}: {
  label: string; value: number;
  positive?: boolean; negative?: boolean;
}) {
  const color = positive
    ? tokens.accent
    : negative
      ? tokens.negative
      : tokens.text;
  return (
    <div className={styles.stat}>
      <p className={styles.statLabel}>{label}</p>
      <p className={styles.statValue} style={{ color }}>
        ${(value || 0).toFixed(2)}
      </p>
    </div>
  );
}
