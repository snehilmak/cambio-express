import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  updateMonthly,
  useMonthly,
  type MonthlyUpdateBody,
} from "../api/monthly";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>Edit monthly P&L</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to edit monthly P&L.
        </p>
      </main>
    );
  }

  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Edit monthly P&L</h1>
        <p style={emptyStyle}>
          Missing year or month. Open a P&L first, then click Edit.
        </p>
      </main>
    );
  }

  if (detail.isLoading || form == null) {
    return (
      <main style={pageStyle}>
        <p style={emptyStyle}>Loading…</p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>Edit monthly P&L</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
            fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
          }}
        >
          {MONTH_NAMES[month - 1]} {year}
        </p>
        <p
          style={{
            margin: "0.5rem 0 0",
            fontSize: "0.85rem",
            color: "var(--db-text-muted, #a3a3a3)",
            lineHeight: 1.5,
          }}
        >
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
          <section key={sec} style={cardStyle}>
            <h2 style={sectionTitleStyle}>{sec}</h2>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))",
                gap: "0.75rem",
              }}
            >
              {FIELDS.filter((f) => f.section === sec).map((f) => (
                <label
                  key={f.key}
                  style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}
                >
                  <span
                    style={{
                      fontSize: "0.78rem",
                      color: "var(--db-text-muted, #a3a3a3)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {f.label}
                  </span>
                  <input
                    type="number" step="0.01"
                    value={
                      typeof form[f.key] === "number"
                        ? (form[f.key] as number)
                        : 0
                    }
                    onChange={(e) =>
                      set(f.key, Number(e.target.value) as never)
                    }
                    style={inputStyle}
                  />
                </label>
              ))}
            </div>
          </section>
        ))}

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Notes</h2>
          <textarea
            value={form.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            rows={4}
            style={{ ...inputStyle, resize: "vertical", minHeight: "5rem" }}
          />
        </section>

        {err && (
          <p
            role="alert"
            style={{
              ...emptyStyle,
              color: "var(--db-negative, #ff3b30)",
            }}
          >
            {err}
          </p>
        )}

        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={() => navigate(`/monthly?year=${year}&month=${month}`)}
            style={cancelBtnStyle}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            style={{
              ...saveBtnStyle,
              opacity: busy ? 0.6 : 1,
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </main>
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
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--db-text-muted, #a3a3a3)",
  margin: "0 0 1rem",
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
};

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const saveBtnStyle: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "var(--db-on-accent, #0a0a0a)",
  border: "none",
  borderRadius: "0.5rem",
  padding: "0.7rem 1.25rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  fontWeight: 600,
};

const cancelBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.7rem 1.25rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
  cursor: "pointer",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
