import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  updateDailyReport,
  useDailyReport,
  type DailyReportUpdateBody,
} from "../api/dailybook";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Button, Card, EmptyState, Loading, PageHeader, PageShell, tokens,
} from "../components/ui";

// Edit page for the daily book at /app/daily/edit?date=YYYY-MM-DD.
//
// Saves only the editable top-level totals (the subset the
// FastAPI schema accepts). Line-item-derived fields like
// money_transfer, drops, check_deposits, cash_purchases, etc.
// are NOT in the form — they roll up from their own tables and
// keep going through the legacy /daily-book write path until a
// follow-up PR migrates them.

const FIELDS: { key: keyof DailyReportUpdateBody; label: string; section: "Sales" | "Receipts" | "Disbursements" | "Other" }[] = [
  { key: "taxable_sales",           label: "Taxable sales",           section: "Sales" },
  { key: "non_taxable",             label: "Non-taxable",             section: "Sales" },
  { key: "sales_tax",               label: "Sales tax",               section: "Sales" },

  { key: "bill_payment_charge",     label: "Bill payment charge",     section: "Receipts" },
  { key: "phone_recargas",          label: "Phone recargas",          section: "Receipts" },
  { key: "boost_mobile",            label: "Boost Mobile",            section: "Receipts" },
  { key: "money_order",             label: "Money order",             section: "Receipts" },
  { key: "check_cashing_fees",      label: "Check cashing fees",      section: "Receipts" },
  { key: "return_check_hold_fees",  label: "Return check hold fees",  section: "Receipts" },
  { key: "forward_balance",         label: "Forward balance",         section: "Receipts" },
  { key: "from_bank",               label: "From bank",               section: "Receipts" },
  { key: "rebates_commissions",     label: "Rebates / commissions",   section: "Receipts" },

  { key: "cash_deposit",            label: "Cash deposit",            section: "Disbursements" },
  { key: "payroll_expense",         label: "Payroll expense",         section: "Disbursements" },

  { key: "safe_balance",            label: "Safe balance",            section: "Other" },
  { key: "over_short",              label: "Over / short",            section: "Other" },
];

const SECTIONS: Array<"Sales" | "Receipts" | "Disbursements" | "Other"> = [
  "Sales", "Receipts", "Disbursements", "Other",
];

export default function EditDailyBook() {
  const navigate = useNavigate();
  const identity = getCurrentIdentity();
  const [searchParams] = useSearchParams();
  const dateParam = searchParams.get("date");
  const date = dateParam ?? "";

  const detail = useDailyReport(date || undefined);

  const [form, setForm] = useState<DailyReportUpdateBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hydrate the form once the existing report (if any) loads.
  // Missing report → empty form (auto-create on save).
  useEffect(() => {
    // Wait for the network attempt to settle (data could be the
    // row OR null for "no report yet").
    if (detail.isLoading || detail.isFetching) return;
    const r = detail.data;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable form from server-fetched daily report (or zero-filled defaults when no report exists yet)
    setForm({
      taxable_sales:           r?.taxable_sales ?? 0,
      non_taxable:             r?.non_taxable ?? 0,
      sales_tax:               r?.sales_tax ?? 0,
      money_order:             r?.money_order ?? 0,
      cash_deposit:            r?.cash_deposit ?? 0,
      safe_balance:            r?.safe_balance ?? 0,
      over_short:              r?.over_short ?? 0,
      // Fields that aren't on the read-side row default to 0;
      // the form lets the cashier set them.
      bill_payment_charge:     0,
      phone_recargas:          0,
      boost_mobile:            0,
      check_cashing_fees:      0,
      return_check_hold_fees:  0,
      forward_balance:         0,
      from_bank:               0,
      rebates_commissions:     0,
      payroll_expense:         0,
      notes:                   r?.notes ?? "",
    });
  }, [detail.data, detail.isLoading, detail.isFetching]);

  function set<K extends keyof DailyReportUpdateBody>(
    key: K, value: DailyReportUpdateBody[K],
  ) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form || !date || identity?.store_id == null) return;
    setError(null);
    setBusy(true);
    try {
      // Coerce all numeric fields to numbers in case the inputs
      // returned strings on submit.
      const body: DailyReportUpdateBody = { notes: form.notes ?? "" };
      for (const f of FIELDS) {
        const v = form[f.key];
        if (typeof v === "number" || typeof v === "string") {
          (body as Record<string, number>)[f.key] = Number(v) || 0;
        }
      }
      await updateDailyReport(identity.store_id, date, body);
      navigate("/daily", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not save the daily book. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="70rem">
        <PageHeader title="Edit daily book" />
        <EmptyState title="Sign in as a store admin to edit the daily book." />
      </PageShell>
    );
  }
  if (!date) {
    return (
      <PageShell maxWidth="70rem">
        <PageHeader title="Edit daily book" />
        <EmptyState
          title="Missing date."
          body="Pick a day from the calendar at /daily, then tap a cell to open the editor."
        />
      </PageShell>
    );
  }
  if (detail.isLoading || form == null) {
    return (
      <PageShell maxWidth="70rem">
        <Loading />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="70rem" gap="1.25rem">
      <PageHeader
        title="Edit daily book"
        subtitle={(
          <span style={{ fontFamily: tokens.fontMono }}>
            {formatHumanDate(date)} <span style={{ color: tokens.textMuted }}>· {date}</span>
          </span>
        )}
        actions={(
          <Button
            tone="ghost"
            size="sm"
            onClick={() => navigate("/daily")}
          >
            ← Calendar
          </Button>
        )}
      />

      {detail.data?.locked && (
        <Card padding="0.85rem 1rem">
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              color: tokens.warning,
              fontSize: "0.9rem",
            }}
          >
            ⚠ This day is locked. Unlock it before editing.
          </span>
        </Card>
      )}

      <form
        onSubmit={onSubmit}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1.25rem",
        }}
      >
        {SECTIONS.map((sec) => (
          <Card key={sec} padding="1.25rem 1.5rem">
            <h2 style={sectionTitleStyle}>{sec}</h2>
            <Grid>
              {FIELDS.filter((f) => f.section === sec).map((f) => (
                <Field key={f.key} label={f.label}>
                  <input
                    type="number"
                    step="0.01"
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
                </Field>
              ))}
            </Grid>
          </Card>
        ))}

        <Card padding="1.25rem 1.5rem">
          <h2 style={sectionTitleStyle}>Notes</h2>
          <textarea
            value={form.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            rows={4}
            style={{ ...inputStyle, resize: "vertical", minHeight: "5rem" }}
          />
        </Card>

        {error && (
          <p role="alert" style={errorStyle}>
            {error}
          </p>
        )}

        <div style={actionRowStyle}>
          <Button
            type="button"
            tone="secondary"
            onClick={() => navigate("/daily")}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            tone="primary"
            disabled={busy || detail.data?.locked === true}
          >
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </PageShell>
  );
}


function formatHumanDate(iso: string): string {
  // YYYY-MM-DD → "Mon, May 12, 2026". Falls back to the raw string
  // on parse error so we never block the page.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
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

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))",
        gap: "0.75rem",
      }}
    >
      {children}
    </div>
  );
}

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: tokens.fontDisplay,
  fontSize: "0.85rem",
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: tokens.textMuted,
  margin: "0 0 1rem",
  fontWeight: 600,
};

const inputStyle: React.CSSProperties = {
  background: tokens.surface,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: tokens.text,
  fontFamily: tokens.fontMono,
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const actionRowStyle: React.CSSProperties = {
  display: "flex",
  gap: "0.75rem",
  justifyContent: "flex-end",
  position: "sticky",
  bottom: 0,
  background: tokens.surface,
  borderTop: `1px solid ${tokens.border}`,
  padding: "0.85rem 0",
  marginTop: "0.5rem",
  zIndex: 1,
};

const errorStyle: React.CSSProperties = {
  margin: 0,
  padding: "0.65rem 0.85rem",
  color: tokens.negative,
  background: "rgba(255, 59, 48, 0.08)",
  border: `1px solid ${tokens.negative}`,
  borderRadius: "0.5rem",
  fontSize: "0.9rem",
};
