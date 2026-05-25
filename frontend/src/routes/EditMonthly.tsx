import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  updateMonthly,
  useMonthly,
  type MonthlyUpdateBody,
} from "../api/monthly";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, FormActions, Loading, MoneyInput, PageHeader,
  PageShell, Textarea,
} from "../components/ui";
import styles from "./EditMonthly.module.css";

// Edit page for the monthly P&L at /app/monthly/edit?year=Y&month=M.
//
// Fields shown here are the operator-editable subset only —
// auto-derived rows (cash_purchases, cash_expenses, return_check_gl,
// bank_charges_total when bank-sync data exists) are excluded
// from the schema and overwritten server-side from the daily
// ledger / bank txns / return-check workflow.

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const FIELDS: Array<{
  key: keyof MonthlyUpdateBody;
  label: string;
  section: "Income" | "Expenses" | "Cash flow";
}> = [
  { key: "taxable_sales",          label: "Taxable sales",          section: "Income" },
  { key: "non_taxable",            label: "Non-taxable",            section: "Income" },
  { key: "bill_payment_charge",    label: "Bill payment charge",    section: "Income" },
  { key: "phone_recargas",         label: "Phone recargas",         section: "Income" },
  { key: "boost_mobile",           label: "Boost Mobile",           section: "Income" },
  { key: "return_check_hold_fees", label: "Return check hold fees", section: "Income" },
  { key: "rebates_commissions",    label: "Rebates / commissions",  section: "Income" },
  { key: "mt_commission_in_bank",  label: "MT commission in bank",  section: "Income" },
  { key: "other_income_1",         label: "Other income 1",         section: "Income" },
  { key: "other_income_2",         label: "Other income 2",         section: "Income" },
  { key: "other_income_3",         label: "Other income 3",         section: "Income" },

  { key: "bank_charges_total",     label: "Bank charges (manual)",  section: "Expenses" },
  { key: "credit_card_fees",       label: "Credit card fees",       section: "Expenses" },
  { key: "money_order_rent",       label: "Money order rent",       section: "Expenses" },
  { key: "emaginenet_tech",        label: "EmagineNet / tech",      section: "Expenses" },
  { key: "irs_payroll_tax",        label: "IRS payroll tax",        section: "Expenses" },
  { key: "texas_workforce",        label: "Texas workforce",        section: "Expenses" },
  { key: "other_taxes",            label: "Other taxes",            section: "Expenses" },
  { key: "accounting_charges",     label: "Accounting charges",     section: "Expenses" },
  { key: "other_expense_1",        label: "Other expense 1",        section: "Expenses" },
  { key: "other_expense_2",        label: "Other expense 2",        section: "Expenses" },
  { key: "other_expense_3",        label: "Other expense 3",        section: "Expenses" },
  { key: "other_expense_4",        label: "Other expense 4",        section: "Expenses" },
  { key: "other_expense_5",        label: "Other expense 5",        section: "Expenses" },

  { key: "over_short",             label: "Over / short",           section: "Cash flow" },
  { key: "borrowed_money_return",  label: "Borrowed money return",  section: "Cash flow" },
  { key: "profit_distributed",     label: "Profit distributed",     section: "Cash flow" },
  { key: "cash_carry_forward",     label: "Cash carry forward",     section: "Cash flow" },
];

const SECTIONS: Array<"Income" | "Expenses" | "Cash flow"> = [
  "Income", "Expenses", "Cash flow",
];

export default function EditMonthly() {
  const navigate = useNavigate();
  const identity = getCurrentIdentity();
  const [sp]     = useSearchParams();
  const year  = Number(sp.get("year"));
  const month = Number(sp.get("month"));

  const detail = useMonthly(
    Number.isFinite(year) ? year : undefined,
    Number.isFinite(month) ? month : undefined,
  );

  const [form, setForm] = useState<MonthlyUpdateBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [err,  setErr]  = useState<string | null>(null);

  useEffect(() => {
    if (detail.isLoading || detail.isFetching) return;
    const r = detail.data;
    const init: MonthlyUpdateBody = { notes: r?.notes ?? "" };
    for (const f of FIELDS) {
      const v = r ? (r as unknown as Record<string, number>)[f.key] : 0;
      (init as Record<string, number>)[f.key] = (v ?? 0) as number;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable form from server-fetched monthly P&L row once the GET resolves
    setForm(init);
  }, [detail.data, detail.isLoading, detail.isFetching]);

  function set<K extends keyof MonthlyUpdateBody>(
    key: K, value: MonthlyUpdateBody[K],
  ) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form || !Number.isFinite(year) || !Number.isFinite(month) ||
        identity?.store_id == null) {
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      const body: MonthlyUpdateBody = { notes: form.notes ?? "" };
      for (const f of FIELDS) {
        const v = form[f.key];
        if (typeof v === "number" || typeof v === "string") {
          (body as Record<string, number>)[f.key] = Number(v) || 0;
        }
      }
      await updateMonthly(year, month, body);
      navigate(`/monthly?year=${year}&month=${month}`, { replace: true });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save P&L.");
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="78rem">
        <PageHeader title="Edit monthly P&L" />
        <p>Sign in as a store admin to edit monthly P&L.</p>
      </PageShell>
    );
  }

  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return (
      <PageShell maxWidth="78rem">
        <PageHeader title="Edit monthly P&L" />
        <p>Missing year or month. Open a P&L first, then click Edit.</p>
      </PageShell>
    );
  }

  if (detail.isLoading || form == null) {
    return (
      <PageShell maxWidth="78rem">
        <Loading />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="78rem">
      <header>

        <Breadcrumbs crumbs={[{ label: "Monthly P&L", to: "/monthly" }, { label: "Edit" }]} />

        <PageHeader title="Edit monthly P&L" />
        <p className={styles.headerMono}>
          {MONTH_NAMES[month - 1]} {year}
        </p>
        <p className={styles.headerNote}>
          Auto-derived fields (cash purchases / expenses / payroll /
          check cashing fees / return-check P&L / bank charges when
          bank-sync data exists) are server-recomputed on save and
          can't be edited here.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        {SECTIONS.map((sec) => (
          <Card key={sec}>
            <h2 className={styles.sectionTitle}>{sec}</h2>
            <div className={styles.fieldGrid}>
              {FIELDS.filter((f) => f.section === sec).map((f) => (
                <MoneyInput
                  key={f.key}
                  label={f.label}
                  value={
                    typeof form[f.key] === "number"
                      ? (form[f.key] as number)
                      : 0
                  }
                  onChange={(v) => set(f.key, v as never)}
                />
              ))}
            </div>
          </Card>
        ))}

        <Card>
          <h2 className={styles.sectionTitle}>Notes</h2>
          <Textarea
            value={form.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            rows={4}
          />
        </Card>

        {err && <Alert tone="error">{err}</Alert>}

        <FormActions>
          <Button
            tone="secondary"
            onClick={() => navigate(`/monthly?year=${year}&month=${month}`)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </FormActions>
      </form>
    </PageShell>
  );
}
