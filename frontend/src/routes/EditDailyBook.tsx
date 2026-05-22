import {
  useCallback, useEffect, useMemo, useState,
  type FormEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createLineItem,
  deleteLineItem,
  lockDailyReport,
  replaceMTBreakdown,
  unlockDailyReport,
  updateDailyReport,
  useDailyReport,
  useLineItems,
  useMTBreakdown,
  type DailyReportRow,
  type DailyReportUpdateBody,
  type LineItemRow,
  type MTBreakdownRow,
  type MTBreakdownWriteRow,
} from "../api/dailybook";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Button, Card, EmptyState, Field, Input, Loading, MoneyInput,
  PageHeader, PageShell, Pill, Textarea,
} from "../components/ui";
import styles from "./EditDailyBook.module.css";

// /app/daily/edit?date=YYYY-MM-DD — the per-day editor.
//
// Layout mirrors the legacy Jinja `daily_report.html` workflow:
//   • Sticky 3-card totals strip at the top (Receipts / Disbursements / Net),
//     updates live as the cashier types.
//   • 4 tabs underneath — Receipts, Disbursements, Money Transfers,
//     and Over/Short & Notes.
//   • Each tab shows a mix of operator-editable inputs and line-item
//     widgets. Line-item widgets are disclosure rows (read-only sum
//     + an expandable list of timestamped entries with an add-row
//     beneath).
//   • Sticky save bar pinned to the viewport bottom — Save / Cancel /
//     Lock day. When locked the bar swaps to "Unlock to edit".
//
// All line-item kinds (drops, check deposits, cash purchases, etc.)
// fire through the FastAPI `/api/v2/daily/{store}/{date}/line-items`
// surface. After every add / delete we invalidate the daily-report
// query so the derived totals on the report row refresh server-side.

// ── Field definitions ────────────────────────────────────────

// Editable keys for the daily-report PUT body.  MUST be a subset
// of the backend's `EDITABLE_REPORT_FIELDS` constant in
// `api/Modules/DailyBook/Services/reports.py`.  The backend
// schema uses `extra="forbid"` so sending ANY field outside the
// allowed set returns HTTP 422 (`test_put_rejects_extra_fields`
// pins this).
//
// Specifically EXCLUDED here despite being on the form:
//   - `money_transfer` — derived from `mt_summary` rows; written
//      via the separate PUT /mt-breakdown endpoint.
//   - line-item-derived fields (cash_purchases, drops, etc.) —
//      mutated by adding / removing daily_line_item rows.
//
// See `api/Modules/DailyBook/INVARIANTS.md` before adding a key
// here.
const EDITABLE_KEYS = [
  "taxable_sales", "non_taxable", "sales_tax",
  "bill_payment_charge", "phone_recargas", "boost_mobile",
  "money_order",
  "check_cashing_fees", "return_check_hold_fees",
  "forward_balance", "from_bank", "rebates_commissions",
  "cash_deposit", "safe_balance", "payroll_expense",
  "over_short",
] as const;
// Form fields whose VALUE is a number — wider than the
// EDITABLE_KEYS list because some displayed-but-not-editable
// fields (notably `money_transfer`, which mirrors the
// mt_summary roll-up) need the same `<NumberInput>` treatment.
// The PUT builder still loops over EDITABLE_KEYS, so these
// wider keys never get sent.
type NumericFormKey = {
  [K in keyof FormState]: FormState[K] extends number ? K : never;
}[keyof FormState];

interface FormState {
  taxable_sales: number;
  non_taxable: number;
  sales_tax: number;
  bill_payment_charge: number;
  phone_recargas: number;
  boost_mobile: number;
  money_transfer: number;
  money_order: number;
  check_cashing_fees: number;
  return_check_hold_fees: number;
  forward_balance: number;
  from_bank: number;
  rebates_commissions: number;
  cash_deposit: number;
  safe_balance: number;
  payroll_expense: number;
  over_short: number;
  notes: string;
}

interface InputFieldDef {
  // `NumericFormKey` rather than `EditKey` because the form
  // displays a few derived values (notably `money_transfer`,
  // which mirrors the mt_summary roll-up) that are NOT in the
  // editable PUT body but still surface on the report.  The PUT
  // builder loops over `EDITABLE_KEYS` so it never sends these
  // derived keys.  See INVARIANTS.md.
  key: NumericFormKey;
  label: string;
}

// Line-item-derived fields — displayed as widgets (read-only total +
// disclosure with line items). The widget POSTs / DELETEs against
// the line-items endpoint; the report's derived field auto-updates
// server-side.
interface LineItemFieldDef {
  key: keyof DailyReportRow;
  label: string;
  kind: string;
  /** True for kinds the cashier may not edit directly (return_payback
   *  is auto-populated from the Return Checks page). */
  readOnly?: boolean;
}

const RECEIPT_INPUTS: InputFieldDef[] = [
  { key: "taxable_sales",          label: "Taxable sales" },
  { key: "non_taxable",            label: "Non-taxable" },
  { key: "sales_tax",              label: "Sales tax" },
  { key: "bill_payment_charge",    label: "Bill payment charge" },
  { key: "phone_recargas",         label: "Phone recargas" },
  { key: "boost_mobile",           label: "Boost Mobile" },
  { key: "money_transfer",         label: "Money transfer" },
  { key: "money_order",            label: "Money order" },
  { key: "check_cashing_fees",     label: "Check cashing fees" },
  { key: "return_check_hold_fees", label: "Return check hold fees" },
  { key: "forward_balance",        label: "Forward balance" },
  { key: "from_bank",              label: "From bank" },
  { key: "rebates_commissions",    label: "Rebates / commissions" },
];

const RECEIPT_LINE_ITEMS: LineItemFieldDef[] = [
  { key: "other_cash_in",          label: "Other cash in",         kind: "other_cash_in" },
  { key: "return_check_paid_back", label: "Return check payback", kind: "return_payback", readOnly: true },
];

const DISBURSEMENT_INPUTS: InputFieldDef[] = [
  { key: "cash_deposit",     label: "Cash deposit" },
  { key: "safe_balance",     label: "Safe balance" },
  { key: "payroll_expense",  label: "Payroll expense" },
];

const DISBURSEMENT_LINE_ITEMS: LineItemFieldDef[] = [
  { key: "cash_purchases",     label: "Cash purchases",       kind: "cash_purchase" },
  { key: "cash_expense",       label: "Cash expense",         kind: "cash_expense" },
  { key: "check_purchases",    label: "Check purchases",      kind: "check_purchase" },
  { key: "check_expense",      label: "Check expense",        kind: "check_expense" },
  { key: "outside_cash_drops", label: "Outside cash & drops", kind: "drop" },
  { key: "checks_deposit",     label: "Check deposits",       kind: "check_deposit" },
  { key: "other_cash_out",     label: "Other cash out",       kind: "other_cash_out" },
];

// The page used to be tab-based (Receipts / Disbursements /
// Money Transfers / Over-Short & Notes).  Pilot called out the
// click-to-switch as too many clicks for a workflow that needs
// the operator to see + reconcile multiple sections at once.
// Switched to a single-page layout where every panel renders
// inline, top-to-bottom.  The legacy `?tab=` query param is
// ignored — links from the calendar drop the operator at the
// top of the page and they can scroll to the relevant section.

// ── Component ────────────────────────────────────────────────

export default function EditDailyBook() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const [searchParams] = useSearchParams();
  const date = searchParams.get("date") ?? "";
  const detail = useDailyReport(date || undefined);
  const lineItemsQuery = useLineItems(date || undefined);

  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  // Hydrate the form from the server payload — runs again after a
  // save invalidation so derived totals stay in sync.
  useEffect(() => {
    if (detail.isLoading || detail.isFetching) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable form from server-fetched daily report
    setForm(buildInitialForm(detail.data));
  }, [detail.data, detail.isLoading, detail.isFetching]);

  // Real-time totals strip — combines editable form values with the
  // line-item-derived fields on the latest server row. The derived
  // ones are updated server-side after every line-item mutation so
  // we just take them from `detail.data`.
  const totals = useMemo(
    () => computeTotals(form, detail.data),
    [form, detail.data],
  );

  const storeId = identity?.store_id;

  const set = useCallback(<K extends keyof FormState>(
    key: K, value: FormState[K],
  ) => {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }, []);


  // Invalidate after a line-item mutation so the report's derived
  // total + the entries list both re-fetch.
  const refreshAfterLineItem = useCallback(() => {
    if (storeId == null) return;
    void queryClient.invalidateQueries({
      queryKey: ["dailybook", "report", storeId, date],
    });
    void queryClient.invalidateQueries({
      queryKey: ["dailybook", "line-items", storeId, date],
    });
  }, [queryClient, storeId, date]);

  async function persistEdits(): Promise<void> {
    if (!form || !date || storeId == null) return;
    const body: DailyReportUpdateBody = { notes: form.notes };
    for (const k of EDITABLE_KEYS) {
      (body as Record<string, number>)[k] = Number(form[k]) || 0;
    }
    await updateDailyReport(storeId, date, body);
    await queryClient.invalidateQueries({
      queryKey: ["dailybook", "report", storeId, date],
    });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await persistEdits();
      setSavedAt(new Date());
    } catch (err) {
      setError(humanizeError(err, "Could not save the daily book."));
    } finally {
      setBusy(false);
    }
  }

  async function onLockToggle() {
    if (busy || !date || storeId == null) return;
    setBusy(true);
    setError(null);
    try {
      if (detail.data?.locked) {
        await unlockDailyReport(storeId, date);
      } else {
        // Save current edits before locking so the operator doesn't
        // freeze a stale snapshot.
        await persistEdits();
        await lockDailyReport(storeId, date);
      }
      await queryClient.invalidateQueries({
        queryKey: ["dailybook", "report", storeId, date],
      });
    } catch (err) {
      setError(humanizeError(err, "Could not change lock state."));
    } finally {
      setBusy(false);
    }
  }

  // ── Render guards ────────────────────────────────────────

  if (storeId == null) {
    return (
      <PageShell>
        <PageHeader title="Edit daily book" />
        <EmptyState title="Sign in as a store admin to edit the daily book." />
      </PageShell>
    );
  }
  if (!date) {
    return (
      <PageShell>
        <PageHeader title="Edit daily book" />
        <EmptyState
          title="Missing date."
          body="Pick a day from the calendar at /daily, then tap a cell to open the editor."
        />
      </PageShell>
    );
  }
  if (detail.isLoading || form == null) {
    return <PageShell><Loading /></PageShell>;
  }

  const report = detail.data;
  const locked = report?.locked === true;
  const lineItems = lineItemsQuery.data?.items ?? [];

  return (
    <PageShell maxWidth="92rem" gap="1rem">
      <PageHeader
        title="Daily book"
        subtitle={(
          <span className={styles.dateBadge}>
            {formatHumanDate(date)}{" "}
            <span className={styles.dateBadgeSep}>· {date}</span>
          </span>
        )}
        actions={(
          <div className={styles.headerActions}>
            {locked && (
              <Pill tone="warning">
                Locked · {formatLockedAt(report?.locked_at)}
              </Pill>
            )}
            {savedAt && !locked && (
              <Pill tone="accent">Saved {formatTime(savedAt)}</Pill>
            )}
            <Button tone="secondary" size="sm" onClick={() => navigate("/daily")}>
              ← Calendar
            </Button>
          </div>
        )}
      />

      <TotalsStrip
        receipts={totals.receipts}
        disbursements={totals.disbursements}
        net={totals.net}
        overShort={form.over_short}
      />

      <form onSubmit={onSubmit} className={styles.form}>
        {/* Single-page layout — every section renders inline so
            the operator never has to click-then-scroll to
            reconcile two sections.  Replaces the legacy tab
            structure (Receipts / Disbursements / Money
            Transfers / Over-Short & Notes).  Each panel keeps
            its own internal 2-column input/line-items grid. */}
        <ReceiptsPanel
          form={form}
          set={set}
          report={report}
          date={date}
          storeId={storeId}
          locked={locked}
          lineItems={lineItems}
          onLineItemChange={refreshAfterLineItem}
        />
        <DisbursementsPanel
          form={form}
          set={set}
          report={report}
          date={date}
          storeId={storeId}
          locked={locked}
          lineItems={lineItems}
          onLineItemChange={refreshAfterLineItem}
        />
        <TransfersPanel
          set={set}
          locked={locked}
          date={date}
          storeId={storeId}
          /* `onJumpReceipts` was the old "scroll to top" CTA
             when transfers were a separate tab.  In the
             stacked layout the operator can just scroll up,
             so this is a no-op now. */
          onJumpReceipts={() => {
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
        <NotesPanel form={form} set={set} locked={locked} />

        {error && <ErrorRow message={error} />}

        <StickySaveBar
          locked={locked}
          busy={busy}
          onCancel={() => navigate("/daily")}
          onLockToggle={onLockToggle}
        />
      </form>
    </PageShell>
  );
}

// ── Sticky totals strip ──────────────────────────────────────

function TotalsStrip({
  receipts, disbursements, net, overShort,
}: {
  receipts: number;
  disbursements: number;
  net: number;
  overShort: number;
}) {
  const netNeg = net < 0;
  return (
    <div className={styles.totalsStrip}>
      <TotalsCard label="Receipts" value={receipts} tone="accent" />
      <TotalsCard label="Disbursements" value={disbursements} tone="negative" />
      <TotalsCard
        label="Net position"
        value={net}
        tone={netNeg ? "negative" : "accent"}
        sub={
          Math.abs(overShort) >= 0.005
            ? `Over/short ${fmtMoney2(overShort)} included`
            : undefined
        }
      />
    </div>
  );
}

function TotalsCard({
  label, value, tone, sub,
}: {
  label: string;
  value: number;
  tone: "accent" | "negative";
  sub?: string;
}) {
  // The top-border accent is the only thing that varies between
  // tones at runtime; everything else lives in the module's
  // ``.totalsCard`` class. Inline the border-top so the tone
  // discriminator doesn't need a per-variant CSS class.
  const borderAccent =
    tone === "accent" ? "var(--db-accent, #3fff00)" : "var(--db-negative, #ff3b30)";
  const valueColor =
    tone === "negative" ? "var(--db-negative, #ff3b30)" : "var(--db-text, #f5f5f5)";
  return (
    <div
      style={{
        background: "var(--db-surface-2, #141414)",
        border: "1px solid var(--db-border, #262626)",
        borderTop: `3px solid ${borderAccent}`,
        borderRadius: "0.875rem",
        padding: "0.85rem 1.1rem",
        flex: 1,
        minWidth: "12rem",
      }}
    >
      <div className={styles.totalsLabel}>{label}</div>
      <div
        style={{
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
          fontSize: "1.55rem",
          fontWeight: 700,
          marginTop: "0.2rem",
          color: valueColor,
          letterSpacing: "-0.01em",
        }}
      >
        {fmtMoney2(value)}
      </div>
      {sub && <div className={styles.totalHint}>{sub}</div>}
    </div>
  );
}

// ── Panels ───────────────────────────────────────────────────
//
// `TabBar` component retired — the daily book renders all
// panels stacked inline now (see the render() above).  The
// per-tab totals (Receipts / Disbursements totals) still
// surface via the always-visible `<TotalsStrip>` at the top.

interface PanelProps {
  form: FormState;
  set: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  report: DailyReportRow | null | undefined;
  date: string;
  storeId: number;
  locked: boolean;
  lineItems: LineItemRow[];
  onLineItemChange: () => void;
}

function ReceiptsPanel(props: PanelProps) {
  return (
    <div className={styles.panelGrid}>
      <Card padding="1.25rem 1.5rem">
        <PanelTitle>Sales & receipts</PanelTitle>
        <InputGrid>
          {RECEIPT_INPUTS.map((f) => (
            <NumberInput
              key={f.key}
              label={f.label}
              value={props.form[f.key]}
              onChange={(v) => props.set(f.key, v)}
              disabled={props.locked}
            />
          ))}
        </InputGrid>
      </Card>

      <Card padding="1.25rem 1.5rem">
        <PanelTitle>Auto-summed entries</PanelTitle>
        <p className={styles.subText}>
          Total updates as you add or delete entries — no manual entry needed.
        </p>
        {RECEIPT_LINE_ITEMS.map((f) => (
          <LineItemWidget
            key={f.kind}
            kind={f.kind}
            label={f.label}
            readOnly={f.readOnly === true || props.locked}
            total={Number(props.report?.[f.key] ?? 0)}
            items={props.lineItems.filter((li) => li.kind === f.kind)}
            storeId={props.storeId}
            date={props.date}
            onChange={props.onLineItemChange}
          />
        ))}
      </Card>
    </div>
  );
}

function DisbursementsPanel(props: PanelProps) {
  return (
    <div className={styles.panelGrid}>
      <Card padding="1.25rem 1.5rem">
        <PanelTitle>Manual disbursements</PanelTitle>
        <InputGrid>
          {DISBURSEMENT_INPUTS.map((f) => (
            <NumberInput
              key={f.key}
              label={f.label}
              value={props.form[f.key]}
              onChange={(v) => props.set(f.key, v)}
              disabled={props.locked}
            />
          ))}
        </InputGrid>
      </Card>

      <Card padding="1.25rem 1.5rem">
        <PanelTitle>Logged entries</PanelTitle>
        <p className={styles.subText}>
          Tap a row to add a timestamped entry — totals roll up automatically.
        </p>
        {DISBURSEMENT_LINE_ITEMS.map((f) => (
          <LineItemWidget
            key={f.kind}
            kind={f.kind}
            label={f.label}
            readOnly={props.locked}
            total={Number(props.report?.[f.key] ?? 0)}
            items={props.lineItems.filter((li) => li.kind === f.kind)}
            storeId={props.storeId}
            date={props.date}
            onChange={props.onLineItemChange}
          />
        ))}
      </Card>
    </div>
  );
}

type MTCell = "amount" | "fees" | "federal_tax" | "commission";

// Editable per-company row state. Keys mirror MoneyTransferSummary
// columns 1:1.
interface MTRowDraft {
  amount: number;
  fees: number;
  federal_tax: number;
  commission: number;
}

function emptyDraft(): MTRowDraft {
  return { amount: 0, fees: 0, federal_tax: 0, commission: 0 };
}

function draftFromRow(row: MTBreakdownRow): MTRowDraft {
  // Prefer saved values (operator's last entry). Fall back to auto
  // (transfer-log aggregate) when no saved row exists, so a fresh
  // day pre-fills automatically.
  const hasSaved = row.saved_total > 0;
  return hasSaved
    ? {
        amount: row.saved_amount,
        fees: row.saved_fees,
        federal_tax: row.saved_federal_tax,
        commission: row.saved_commission,
      }
    : {
        amount: row.auto_amount,
        fees: row.auto_fees,
        federal_tax: row.auto_federal_tax,
        commission: row.auto_commission,
      };
}

function rowDraftTotal(d: MTRowDraft): number {
  return (d.amount || 0) + (d.fees || 0) + (d.federal_tax || 0) + (d.commission || 0);
}

function TransfersPanel({
  set, locked, date, storeId, onJumpReceipts,
}: {
  set: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  locked: boolean;
  date: string;
  storeId: number;
  onJumpReceipts: () => void;
}) {
  const queryClient = useQueryClient();
  const breakdown = useMTBreakdown(date || undefined);

  // Local draft state, hydrated from the server payload. Keyed by
  // company name so re-ordering doesn't lose edits.
  const [drafts, setDrafts] = useState<Map<string, MTRowDraft>>(new Map());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  // Hydrate once the server payload settles.
  useEffect(() => {
    if (breakdown.isLoading || breakdown.isFetching) return;
    const rows = breakdown.data?.rows ?? [];
    const next = new Map<string, MTRowDraft>();
    for (const r of rows) next.set(r.company, draftFromRow(r));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local draft state from server payload
    setDrafts(next);
  }, [breakdown.data, breakdown.isLoading, breakdown.isFetching]);

  const rows = breakdown.data?.rows ?? [];

  function setCell(company: string, cell: MTCell, value: number) {
    setDrafts((prev) => {
      const next = new Map(prev);
      const cur = next.get(company) ?? emptyDraft();
      next.set(company, { ...cur, [cell]: value });
      return next;
    });
  }

  function resetRowToAuto(row: MTBreakdownRow) {
    setDrafts((prev) => {
      const next = new Map(prev);
      next.set(row.company, {
        amount: row.auto_amount,
        fees: row.auto_fees,
        federal_tax: row.auto_federal_tax,
        commission: row.auto_commission,
      });
      return next;
    });
  }

  function applyAutoAll() {
    setDrafts((prev) => {
      const next = new Map(prev);
      for (const row of rows) {
        next.set(row.company, {
          amount: row.auto_amount,
          fees: row.auto_fees,
          federal_tax: row.auto_federal_tax,
          commission: row.auto_commission,
        });
      }
      return next;
    });
  }

  const draftTotal = useMemo(() => {
    let s = 0;
    for (const [, d] of drafts) s += rowDraftTotal(d);
    return s;
  }, [drafts]);

  async function onSave() {
    if (busy || locked) return;
    setErr(null);
    setBusy(true);
    try {
      const writeRows: MTBreakdownWriteRow[] = rows.map((r) => {
        const d = drafts.get(r.company) ?? emptyDraft();
        return {
          company: r.company,
          amount: Number(d.amount) || 0,
          fees: Number(d.fees) || 0,
          federal_tax: Number(d.federal_tax) || 0,
          commission: Number(d.commission) || 0,
        };
      });
      await replaceMTBreakdown(storeId, date, writeRows);
      // money_transfer was mirrored server-side; refresh the parent
      // report so the receipts tab + totals strip pick up the new value.
      await queryClient.invalidateQueries({
        queryKey: ["dailybook", "report", storeId, date],
      });
      await queryClient.invalidateQueries({
        queryKey: ["dailybook", "mt-breakdown", storeId, date],
      });
      // Sync the local receipts-tab form-state too so the user sees
      // the new money_transfer immediately on tab switch.
      set("money_transfer", Number(draftTotal.toFixed(2)));
      setSavedAt(new Date());
    } catch (e) {
      setErr(humanizeError(e, "Could not save the breakdown."));
    } finally {
      setBusy(false);
    }
  }

  const isLoading = breakdown.isLoading || breakdown.data == null;

  return (
    <div className={styles.panelGrid}>
      <Card padding="1.25rem 1.5rem">
        <div className={styles.mtPanelHeader}>
          <PanelTitle>Per-company breakdown</PanelTitle>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            {savedAt && <Pill tone="accent">Saved {formatTime(savedAt)}</Pill>}
            <Button
              type="button"
              tone="secondary"
              size="sm"
              disabled={locked || rows.length === 0}
              onClick={applyAutoAll}
            >
              Fill every row from transfer log
            </Button>
          </div>
        </div>
        <p className={styles.subText}>
          One row per active company. Inputs pre-fill from the operator's
          last save when there is one, otherwise from the day's employee
          transfer log. Saving here writes per-company rows AND syncs the
          grand total to the receipts tab's <em>Money transfer</em> line —
          one round trip.
        </p>

        {isLoading ? (
          <Loading />
        ) : rows.length === 0 ? (
          <p className={styles.emptyEntries}>
            No companies configured for this store.
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className={styles.mtTable}>
              <thead>
                <tr>
                  <th className={styles.mtTh}>Company</th>
                  <th className={`${styles.mtTh} ${styles.mtThNum}`}>Amount</th>
                  <th className={`${styles.mtTh} ${styles.mtThNum}`}>Fees</th>
                  <th className={`${styles.mtTh} ${styles.mtThNum}`}>Fed. tax</th>
                  <th className={`${styles.mtTh} ${styles.mtThNum}`}>Commission</th>
                  <th className={`${styles.mtTh} ${styles.mtThNum}`}>Total</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <MTEditableRow
                    key={r.company}
                    row={r}
                    draft={drafts.get(r.company) ?? emptyDraft()}
                    locked={locked}
                    onCellChange={(cell, value) => setCell(r.company, cell, value)}
                    onResetToAuto={() => resetRowToAuto(r)}
                  />
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className={`${styles.mtTd} ${styles.mtTdStrong}`}>TOTAL</td>
                  <td className={`${styles.mtTd} ${styles.mtTdNum} ${styles.mtTdNumMuted}`}>
                    {fmtMoney2(sumDraftField(drafts, "amount"))}
                  </td>
                  <td className={`${styles.mtTd} ${styles.mtTdNum} ${styles.mtTdNumMuted}`}>
                    {fmtMoney2(sumDraftField(drafts, "fees"))}
                  </td>
                  <td className={`${styles.mtTd} ${styles.mtTdNum} ${styles.mtTdNumMuted}`}>
                    {fmtMoney2(sumDraftField(drafts, "federal_tax"))}
                  </td>
                  <td className={`${styles.mtTd} ${styles.mtTdNum} ${styles.mtTdNumMuted}`}>
                    {fmtMoney2(sumDraftField(drafts, "commission"))}
                  </td>
                  <td className={`${styles.mtTd} ${styles.mtTdNum} ${styles.mtTdNumStrong}`}>
                    {fmtMoney2(draftTotal)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        {err && <ErrorRow message={err} />}

        <div className={styles.mtSaveRow}>
          <span className={styles.mtSaveRowLeft}>
            Grand total syncs to the receipts tab's Money transfer line on save.
          </span>
          <Button
            type="button"
            tone="ghost"
            size="sm"
            onClick={onJumpReceipts}
          >
            ← Edit the rest of the receipts
          </Button>
          <Button
            type="button"
            tone="primary"
            size="md"
            busy={busy}
            disabled={busy || locked || isLoading}
            onClick={onSave}
          >
            {busy ? "Saving…" : "Save breakdown"}
          </Button>
        </div>
      </Card>
    </div>
  );
}

function MTEditableRow({
  row, draft, locked, onCellChange, onResetToAuto,
}: {
  row: MTBreakdownRow;
  draft: MTRowDraft;
  locked: boolean;
  onCellChange: (cell: MTCell, value: number) => void;
  onResetToAuto: (row: MTBreakdownRow) => void;
}) {
  const draftTotal = rowDraftTotal(draft);
  const hasAuto = row.auto_total > 0;
  const matchesAuto = (
    Math.abs(draft.amount - row.auto_amount) < 0.005 &&
    Math.abs(draft.fees - row.auto_fees) < 0.005 &&
    Math.abs(draft.federal_tax - row.auto_federal_tax) < 0.005 &&
    Math.abs(draft.commission - row.auto_commission) < 0.005
  );
  const overridden = hasAuto && !matchesAuto;

  return (
    <tr>
      <td className={`${styles.mtTd} ${styles.mtTdStrong}`}>
        <span style={{ color: companyAccent(row.company) }}>•</span>{" "}
        {row.company}
        {overridden && (
          <button
            type="button"
            onClick={() => onResetToAuto(row)}
            disabled={locked}
            className={styles.mtResetBtn}
            title={`Reset to auto from transfer log (${fmtMoney2(row.auto_total)})`}
          >
            Reset to auto
          </button>
        )}
        {row.auto_count > 0 && (
          <span className={styles.mtRowHint}>
            {row.auto_count} {row.auto_count === 1 ? "transfer" : "transfers"} logged
          </span>
        )}
      </td>
      <MTCellInput
        value={draft.amount}
        onChange={(v) => onCellChange("amount", v)}
        locked={locked}
      />
      <MTCellInput
        value={draft.fees}
        onChange={(v) => onCellChange("fees", v)}
        locked={locked}
      />
      <MTCellInput
        value={draft.federal_tax}
        onChange={(v) => onCellChange("federal_tax", v)}
        locked={locked}
      />
      <MTCellInput
        value={draft.commission}
        onChange={(v) => onCellChange("commission", v)}
        locked={locked}
      />
      <td className={`${styles.mtTd} ${styles.mtTdNum} ${styles.mtTdNumStrong}`}>{fmtMoney2(draftTotal)}</td>
    </tr>
  );
}

function MTCellInput({
  value, onChange, locked,
}: {
  value: number;
  onChange: (next: number) => void;
  locked: boolean;
}) {
  return (
    <td className={styles.mtCellTd}>
      <input
        type="number"
        step="0.01"
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        disabled={locked}
        className={`ds-input ${styles.mtCellInput}`}
      />
    </td>
  );
}

function sumDraftField(
  drafts: Map<string, MTRowDraft>, field: keyof MTRowDraft,
): number {
  let s = 0;
  for (const [, d] of drafts) s += Number(d[field]) || 0;
  return s;
}

// Brand accent dots for the known major companies, neutral for the rest.
function companyAccent(name: string): string {
  const k = name.toLowerCase();
  if (k === "intermex") return "var(--db-co-intermex, #4a87d4)";
  if (k === "maxi")     return "var(--db-co-maxi, #9d52e0)";
  if (k === "barri")    return "var(--db-co-barri, #2cb5b0)";
  return "var(--db-text-muted, #a3a3a3)";
}

function NotesPanel({
  form, set, locked,
}: {
  form: FormState;
  set: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  locked: boolean;
}) {
  return (
    <div className={styles.panelGrid}>
      <Card padding="1.25rem 1.5rem">
        <PanelTitle>Over / short</PanelTitle>
        <p className={styles.subText}>
          Positive number means the till had more cash than expected;
          negative is short. Folded into "Net position" above.
        </p>
        <div style={{ maxWidth: "16rem" }}>
          <NumberInput
            label="Over / short"
            value={form.over_short}
            onChange={(v) => set("over_short", v)}
            disabled={locked}
          />
        </div>
      </Card>
      <Card padding="1.25rem 1.5rem">
        <PanelTitle>Notes</PanelTitle>
        <Field label="Anything the closer should know">
          <Textarea
            value={form.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            rows={6}
            disabled={locked}
            placeholder="e.g. cash drop at 2pm, register short due to refund …"
          />
        </Field>
      </Card>
    </div>
  );
}

// ── Line item widget ─────────────────────────────────────────

function LineItemWidget({
  kind, label, readOnly, total, items, storeId, date, onChange,
}: {
  kind: string;
  label: string;
  readOnly: boolean;
  total: number;
  items: LineItemRow[];
  storeId: number;
  date: string;
  onChange: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [time, setTime] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function add() {
    if (busy) return;
    setErr(null);
    const amt = Number(amount);
    if (!time) { setErr("Pick a time."); return; }
    if (!amt || amt <= 0) { setErr("Amount must be greater than zero."); return; }
    setBusy(true);
    try {
      await createLineItem(storeId, date, {
        kind, at_time: time, amount: amt, note,
      });
      setTime("");
      setAmount("");
      setNote("");
      onChange();
    } catch (e) {
      setErr(humanizeError(e, "Could not add entry."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(itemId: number) {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteLineItem(storeId, itemId);
      onChange();
    } catch (e) {
      setErr(humanizeError(e, "Could not delete entry."));
    } finally {
      setBusy(false);
    }
  }

  const count = items.length;

  return (
    <div className={styles.widget}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={styles.widgetHeader}
        aria-expanded={open}
      >
        <span className={styles.widgetLabel}>
          <span
            className={styles.widgetCaret}
            style={{ transform: open ? "rotate(90deg)" : undefined }}
          >
            ▸
          </span>
          {label}
          {readOnly && <Pill tone="info">Auto</Pill>}
          <span className={styles.widgetCount}>
            {count} {count === 1 ? "entry" : "entries"}
          </span>
        </span>
        <span className={styles.widgetTotal}>{fmtMoney2(total)}</span>
      </button>

      {open && (
        <div className={styles.widgetBody}>
          {!readOnly && (
            <div className={styles.widgetAddRow}>
              <div className={styles.addRowTime}>
                <Field label="Time">
                  <Input
                    type="time"
                    value={time}
                    onChange={(e) => setTime(e.target.value)}
                    disabled={busy}
                  />
                </Field>
              </div>
              <div className={styles.addRowAmount}>
                <Field label="Amount">
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="0.00"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    disabled={busy}
                  />
                </Field>
              </div>
              <div className={styles.addRowNote}>
                <Field label="Note (optional)">
                  <Input
                    type="text"
                    maxLength={120}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    disabled={busy}
                    placeholder="optional"
                  />
                </Field>
              </div>
              <div className={styles.addRowEnd}>
                <Button
                  type="button"
                  tone="primary"
                  size="sm"
                  busy={busy}
                  onClick={add}
                  disabled={busy}
                >
                  + Add
                </Button>
              </div>
            </div>
          )}

          {err && <ErrorRow message={err} />}

          {items.length === 0 ? (
            <p className={styles.emptyEntries}>
              {readOnly
                ? "No entries logged for this day yet."
                : "No entries yet — add one above."}
            </p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className={styles.widgetTable}>
                <thead>
                  <tr>
                    <th className={styles.widgetTh}>Time</th>
                    <th className={styles.widgetTh}>Amount</th>
                    <th className={styles.widgetTh}>Note</th>
                    {!readOnly && <th className={styles.widgetTh} aria-label="actions" />}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td className={styles.widgetTdMono}>{item.at_time || "—"}</td>
                      <td className={styles.widgetTdMono}>{fmtMoney2(item.amount)}</td>
                      <td className={styles.widgetTd}>{item.note || "—"}</td>
                      {!readOnly && (
                        <td className={styles.widgetTd}>
                          {item.return_check_id == null ? (
                            <Button
                              type="button"
                              tone="danger"
                              size="sm"
                              busy={busy}
                              onClick={() => remove(item.id)}
                            >
                              Remove
                            </Button>
                          ) : (
                            <span className={styles.widgetTdSmall}>
                              from return check
                            </span>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Save bar + helpers ──────────────────────────────────────

function StickySaveBar({
  locked, busy, onCancel, onLockToggle,
}: {
  locked: boolean;
  busy: boolean;
  onCancel: () => void;
  onLockToggle: () => void;
}) {
  return (
    <div className={styles.saveBar}>
      <div className={styles.saveBarLeft}>
        {locked
          ? "This day is locked. Unlock to edit any field."
          : "Saves apply to every field in every tab."}
      </div>
      <Button
        type="button"
        tone="secondary"
        size="md"
        onClick={onCancel}
        disabled={busy}
      >
        Back to calendar
      </Button>
      <Button
        type="button"
        tone={locked ? "secondary" : "secondary"}
        size="md"
        busy={busy}
        onClick={onLockToggle}
        disabled={busy}
      >
        {locked ? "Unlock to edit" : "Lock day"}
      </Button>
      {!locked && (
        <Button
          type="submit"
          tone="primary"
          size="md"
          busy={busy}
          disabled={busy}
        >
          {busy ? "Saving…" : "Save daily book"}
        </Button>
      )}
    </div>
  );
}

function PanelTitle({ children }: { children: React.ReactNode }) {
  return <h2 className={styles.panelTitle}>{children}</h2>;
}

function InputGrid({ children }: { children: React.ReactNode }) {
  return <div className={styles.inputGrid}>{children}</div>;
}

/** Tiny shim around the kit `<MoneyInput>` so the panel components
 *  below don't have to spread MoneyInput's full prop surface
 *  everywhere.  All dollar fields on the daily book go through
 *  this primitive — `inputMode="decimal"`, no spinner arrows,
 *  empty input means 0, optional `$` prefix.  See
 *  `frontend/src/components/ui/MoneyInput.tsx` for the contract
 *  and the linked test cases. */
function NumberInput({
  label, value, onChange, disabled,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  disabled?: boolean;
}) {
  return (
    <MoneyInput
      label={label}
      value={Number.isFinite(value) ? value : 0}
      onChange={onChange}
      disabled={disabled}
    />
  );
}

function ErrorRow({ message }: { message: string }) {
  return (
    <p role="alert" className={styles.error}>
      {message}
    </p>
  );
}

// ── Helpers ─────────────────────────────────────────────────

function buildInitialForm(r: DailyReportRow | null | undefined): FormState {
  return {
    taxable_sales:           r?.taxable_sales           ?? 0,
    non_taxable:             r?.non_taxable             ?? 0,
    sales_tax:               r?.sales_tax               ?? 0,
    bill_payment_charge:     r?.bill_payment_charge     ?? 0,
    phone_recargas:          r?.phone_recargas          ?? 0,
    boost_mobile:            r?.boost_mobile            ?? 0,
    money_transfer:          r?.money_transfer          ?? 0,
    money_order:             r?.money_order             ?? 0,
    check_cashing_fees:      r?.check_cashing_fees      ?? 0,
    return_check_hold_fees:  r?.return_check_hold_fees  ?? 0,
    forward_balance:         r?.forward_balance         ?? 0,
    from_bank:               r?.from_bank               ?? 0,
    rebates_commissions:     r?.rebates_commissions     ?? 0,
    cash_deposit:            r?.cash_deposit            ?? 0,
    safe_balance:            r?.safe_balance            ?? 0,
    payroll_expense:         r?.payroll_expense         ?? 0,
    over_short:              r?.over_short              ?? 0,
    notes:                   r?.notes                   ?? "",
  };
}

function computeTotals(form: FormState | null, report: DailyReportRow | null | undefined) {
  const receiptsEditable = form ? (
    form.taxable_sales + form.non_taxable + form.sales_tax +
    form.bill_payment_charge + form.phone_recargas + form.boost_mobile +
    form.money_transfer + form.money_order +
    form.check_cashing_fees + form.return_check_hold_fees +
    form.forward_balance + form.from_bank + form.rebates_commissions
  ) : 0;
  const receiptsDerived =
    (report?.other_cash_in ?? 0) + (report?.return_check_paid_back ?? 0);
  const receipts = receiptsEditable + receiptsDerived;

  const disbursementsEditable = form ? (
    form.cash_deposit + form.safe_balance + form.payroll_expense
  ) : 0;
  const disbursementsDerived =
    (report?.cash_purchases ?? 0) + (report?.cash_expense ?? 0) +
    (report?.check_purchases ?? 0) + (report?.check_expense ?? 0) +
    (report?.outside_cash_drops ?? 0) + (report?.checks_deposit ?? 0) +
    (report?.other_cash_out ?? 0);
  const disbursements = disbursementsEditable + disbursementsDerived;

  const overShort = form?.over_short ?? 0;
  const net = receipts - disbursements + overShort;
  return { receipts, disbursements, net };
}

// `fmtMoney` retired alongside the TabBar — was only used for the
// per-tab totals hints in the bar.  `fmtMoney2` (2-decimal form)
// stays since it backs the TotalsStrip + StickySaveBar.

function fmtMoney2(n: number): string {
  if (!Number.isFinite(n)) return "$0.00";
  return n.toLocaleString(undefined, {
    style: "currency", currency: "USD",
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}

function formatHumanDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatLockedAt(iso: string | undefined): string {
  if (!iso) return "locked";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "locked";
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function humanizeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

