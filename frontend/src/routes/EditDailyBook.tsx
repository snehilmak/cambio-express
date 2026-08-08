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
  updateLineItem,
  useDailyReport,
  useLineItems,
  useMTBreakdown,
  type DailyReportRow,
  type DailyReportUpdateBody,
  type LineItemRow,
  type MTBreakdownRow,
  type MTBreakdownWriteRow,
} from "../api/dailybook";
import { useStoreInfo } from "../api/account";
import { fmtMoney2 } from "../lib/formatters";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs, Button, Card, ConfirmDialog, EmptyState, Field, Input,
  Loading, Modal, MoneyInput, PageHeader, PageShell, Pill, RowActions,
  TabsBar, TabsButton, Textarea,
} from "../components/ui";
import { useUnsavedChangesGuard } from "../lib/useUnsavedChangesGuard";
import styles from "./EditDailyBook.module.css";
import { ImportReportModal } from "./ImportReportModal";

// /app/daily/edit?date=YYYY-MM-DD — the per-day editor.
//
// Layout mirrors the legacy Jinja `daily_report.html` workflow:
//   • Sticky 3-card totals strip at the top (Receipts / Disbursements / Net),
//     updates live as the cashier types.
//   • 3 tabs underneath (mobile) — In (Receipts), Out
//     (Disbursements), and Over/Short & Notes. Desktop shows them
//     side-by-side.
//   • Each tab shows a mix of operator-editable inputs and widgets.
//     Line-item widgets are tile + modal (read-only sum + a list of
//     timestamped entries with an add-row). The Money transfer tile
//     in the "In" tab opens the per-company breakdown modal.
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
// Deliberately NOT here (Category 2 / 3 — never sent via this PUT):
//   - `money_transfer` — derived from `mt_summary` rows; written
//      via the separate PUT /mt-breakdown endpoint and surfaced in
//      the "In" tab through <MoneyTransferWidget>, not a form input.
//   - line-item-derived fields (cash_purchases, drops, etc.) —
//      mutated by adding / removing daily_line_item rows.
//
// See `api/Modules/DailyBook/INVARIANTS.md` before adding a key
// here.
const EDITABLE_KEYS = [
  "taxable_sales", "non_taxable", "sales_tax",
  "bill_payment_charge", "phone_recargas", "boost_mobile",
  "money_order",
  "money_order_fees", "check_cashing_fees", "return_check_hold_fees",
  "forward_balance", "rebates_commissions",
  "cash_deposit", "safe_balance", "payroll_expense",
  "over_short",
] as const;
// Form fields whose VALUE is a number. Kept as a distinct type
// from EDITABLE_KEYS (they currently coincide) so a future
// displayed-but-derived field can be added to the form without
// leaking into the PUT body — the builder always loops over
// EDITABLE_KEYS, never NumericFormKey.
type NumericFormKey = {
  [K in keyof FormState]: FormState[K] extends number ? K : never;
}[keyof FormState];

export interface FormState {
  taxable_sales: number;
  non_taxable: number;
  sales_tax: number;
  bill_payment_charge: number;
  phone_recargas: number;
  boost_mobile: number;
  money_order: number;
  money_order_fees: number;
  check_cashing_fees: number;
  return_check_hold_fees: number;
  forward_balance: number;
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

// taxable_sales / non_taxable / sales_tax are edited together in the
// <SalesWidget> modal (see the "In" tab), not as plain inputs here.
// money_order_fees / check_cashing_fees / return_check_hold_fees are
// grouped in the <FeesWidget> modal for the same reason.
// forward_balance is also NOT in this list — it renders through the
// dedicated <ForwardBalanceInput> because it's auto-carried from the
// prior day (read-only) on every day but the store's first.
const RECEIPT_INPUTS: InputFieldDef[] = [
  { key: "bill_payment_charge",    label: "Bill payment charge" },
  { key: "phone_recargas",         label: "Phone recargas" },
  { key: "boost_mobile",           label: "Boost Mobile" },
  { key: "money_order",            label: "Money order" },
  { key: "rebates_commissions",    label: "Rebates / commissions" },
];

const RECEIPT_LINE_ITEMS: LineItemFieldDef[] = [
  { key: "from_bank",              label: "Cash from bank",        kind: "from_bank" },
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

// Layout strategy:
//   - Desktop (≥60rem): all four panels render in a CSS-grid
//     layout — Receipts + Disbursements side-by-side at the top,
//     Transfers full-width below them, Notes full-width at the
//     bottom.  Operator sees everything at once and never has to
//     click to switch sections.
//   - Mobile (<60rem): the same JSX renders, but a sticky tab
//     strip at the top picks which panel is visible.  CSS hides
//     the other three (via `display:none`) so the page only
//     paints one section at a time and never scrolls past 100vh.
// The legacy `?tab=` query param is ignored — links from the
// calendar drop the operator on the Receipts tab by default.

type DailyTab = "receipts" | "disbursements" | "overshort";
const DAILY_TAB_DEFS: Array<{ id: DailyTab; label: string }> = [
  { id: "receipts",      label: "In" },
  { id: "disbursements", label: "Out" },
  { id: "overshort",     label: "Over Short" },
];

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
  // Baseline = last server-synced form; used to detect unsaved edits.
  const [baseline, setBaseline] = useState<FormState | null>(null);
  // Confirm before leaving with unsaved edits (Back to calendar).
  const [pendingLeave, setPendingLeave] = useState(false);
  const [busy, setBusy] = useState(false);
  // Mobile-only tab.  Desktop CSS ignores the data-attr and
  // shows every panel in the grid; mobile CSS hides every
  // panel except the one matching `mobileTab`.  See
  // EditDailyBook.module.css `.dailyLayout` rules.
  const [mobileTab, setMobileTab] = useState<DailyTab>("receipts");
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  // Hydrate the form from the server payload — runs again after a
  // save invalidation so derived totals stay in sync.
  useEffect(() => {
    if (detail.isLoading || detail.isFetching) return;
    const init = buildInitialForm(detail.data);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable form + dirty baseline from server-fetched daily report
    setForm(init);
    setBaseline(init);
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

  // Store-wide sales-tax rate (decimal fraction, e.g. 0.0825). When
  // > 0 the Sales widget auto-computes Sales Tax from Taxable Sales
  // and locks the field; 0 means "no rate set" → manual entry.
  const storeInfo = useStoreInfo();
  const salesTaxRate = Number(storeInfo.data?.store.sales_tax_rate ?? 0);

  // Unsaved-edit tracking for the main form fields (line-item widgets
  // persist immediately, so they're excluded). Arms the browser
  // "leave site?" prompt on close / refresh; the "Back to calendar"
  // control confirms in-app below.
  const isDirty =
    form != null && baseline != null &&
    JSON.stringify(form) !== JSON.stringify(baseline);
  useUnsavedChangesGuard(isDirty && !busy);

  function onBackToCalendar() {
    if (isDirty) setPendingLeave(true);
    else navigate("/daily");
  }

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
    <PageShell gap="1rem">
      <Breadcrumbs crumbs={[
        { label: "Daily book", to: "/daily" },
      ]} />
      <PageHeader
        title={formatHumanDate(date)}
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
          </div>
        )}
      />

      <TotalsStrip
        receipts={totals.receipts}
        disbursements={totals.disbursements}
        net={totals.net}
        overShort={form.over_short}
      />

      {/* Mobile-only tab strip.  CSS hides it at ≥60rem viewports
          (see `.mobileTabs` in EditDailyBook.module.css) so the
          desktop grid renders all four panels at once. */}
      <div className={styles.mobileTabs}>
        <TabsBar>
          {DAILY_TAB_DEFS.map((t) => (
            <TabsButton
              key={t.id}
              active={mobileTab === t.id}
              onClick={() => setMobileTab(t.id)}
            >
              {t.label}
            </TabsButton>
          ))}
        </TabsBar>
      </div>

      <form onSubmit={onSubmit} className={styles.form}>
        {/* CSS-grid layout: desktop renders all four panels in a
            grid (Receipts | Disbursements top, Transfers full-
            width, Notes full-width).  Mobile renders only the
            panel matching `mobileTab` via the `[data-tab]`
            attribute selector — see `.dailyLayout` rules. */}
        <div
          className={styles.dailyLayout}
          data-active-tab={mobileTab}
        >
          <div data-tab="receipts">
            <ReceiptsPanel
              form={form}
              set={set}
              report={report}
              date={date}
              storeId={storeId}
              locked={locked}
              lineItems={lineItems}
              onLineItemChange={refreshAfterLineItem}
              salesTaxRate={salesTaxRate}
              persist={persistEdits}
            />
          </div>
          <div data-tab="disbursements">
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
          </div>
          <div data-tab="overshort" className={styles.overShortCol}>
            <NotesPanel form={form} set={set} locked={locked} />
          </div>
        </div>

        {error && <ErrorRow message={error} />}

        <StickySaveBar
          locked={locked}
          busy={busy}
          dirty={isDirty && !locked}
          onCancel={onBackToCalendar}
          onLockToggle={onLockToggle}
        />
      </form>

      <ConfirmDialog
        open={pendingLeave}
        title="Discard unsaved changes?"
        message="You have unsaved edits on this day's book. Leave without saving?"
        confirmLabel="Leave"
        confirmTone="danger"
        onConfirm={() => navigate("/daily")}
        onCancel={() => setPendingLeave(false)}
      />
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
      <TotalsCard label="In" value={receipts} tone="accent" />
      <TotalsCard label="Out" value={disbursements} tone="negative" />
      <TotalsCard
        label="Over short"
        value={net}
        tone={netNeg ? "negative" : "accent"}
        sub={
          Math.abs(overShort) >= 0.005
            ? `Drawer: ${fmtMoney2(overShort)}`
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

function ReceiptsPanel(
  props: PanelProps & {
    salesTaxRate: number;
    persist: () => Promise<void>;
  },
) {
  const [importOpen, setImportOpen] = useState(false);
  return (
    <Card padding="1.25rem 1.5rem">
      <PanelTitle>Tap to edit</PanelTitle>
      <div className={styles.widgetGrid}>
        <SalesWidget
          form={props.form}
          set={props.set}
          locked={props.locked}
          salesTaxRate={props.salesTaxRate}
          persist={props.persist}
        />
        <FeesWidget
          form={props.form}
          set={props.set}
          locked={props.locked}
          persist={props.persist}
        />
        <MoneyTransferWidget
          total={Number(props.report?.money_transfer ?? 0)}
          storeId={props.storeId}
          date={props.date}
          locked={props.locked}
          onChange={props.onLineItemChange}
        />
      </div>

      {!props.locked && (
        <div style={{ marginTop: "0.6rem" }}>
          <Button
            type="button"
            tone="secondary"
            size="sm"
            onClick={() => setImportOpen(true)}
          >
            Import Intermex report
          </Button>
        </div>
      )}
      <ImportReportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        storeId={props.storeId}
        reportDate={props.date}
        onCommitted={props.onLineItemChange}
      />

      <div className={styles.panelDivider} />

      <PanelTitle>Other receipts</PanelTitle>
      <InputGrid>
        <ForwardBalanceInput
          value={props.form.forward_balance}
          auto={props.report?.forward_balance_auto === true}
          disabled={props.locked}
          onChange={(v) => props.set("forward_balance", v)}
        />
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

      <div className={styles.panelDivider} />

      <PanelTitle>Auto-summed entries</PanelTitle>
      <p className={styles.subText}>
        Total updates as you add or delete entries — no manual entry needed.
      </p>
      <div className={styles.widgetGrid}>
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
      </div>
    </Card>
  );
}

function DisbursementsPanel(props: PanelProps) {
  return (
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

      <div className={styles.panelDivider} />

      <PanelTitle>Logged entries</PanelTitle>
      <p className={styles.subText}>
        Tap a row to add a timestamped entry — totals roll up automatically.
      </p>
      <div className={styles.widgetGrid}>
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
      </div>
    </Card>
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
  // Manual entry only (for now): hydrate from the operator's saved
  // values, zero when there's no saved row yet. The auto-fill from
  // the transfer log (`row.auto_*`) is intentionally NOT used here —
  // the transfer-log integration isn't finished, so the operator
  // types every company's figures by hand. The backend still returns
  // `auto_*`, so re-enabling auto-fill later is a UI-only change.
  return {
    amount: row.saved_amount,
    fees: row.saved_fees,
    federal_tax: row.saved_federal_tax,
    commission: row.saved_commission,
  };
}

function rowDraftTotal(d: MTRowDraft): number {
  return (d.amount || 0) + (d.fees || 0) + (d.federal_tax || 0) + (d.commission || 0);
}

function round2(n: number): number {
  return Math.round((Number(n) || 0) * 100) / 100;
}

// Sales widget — groups Taxable sales, Non-taxable, and Sales tax
// into one tile + modal (the cash-purchase / money-transfer pattern).
//
// Sales tax behaviour depends on the store's `sales_tax_rate`:
//   • rate > 0 → Sales tax = Taxable sales × rate, auto-computed and
//     shown read-only so the operator can't mistype it.
//   • rate = 0 → no rate configured; Sales tax stays manually
//     editable, exactly as before the setting existed.
//
// These three are Category-1 report fields (in EDITABLE_KEYS), so the
// modal edits the shared form state and its Save persists through the
// normal daily-report PUT — same values, nicer grouping.
function SalesWidget({
  form, set, locked, salesTaxRate, persist,
}: {
  form: FormState;
  set: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  locked: boolean;
  salesTaxRate: number;
  persist: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const autoTax = salesTaxRate > 0;
  const computedTax = round2(form.taxable_sales * salesTaxRate);

  // Keep the stored Sales tax in step with Taxable sales whenever a
  // rate is configured and the day is editable. Guarded on the value
  // so it never loops. Locked days keep their archived figure.
  useEffect(() => {
    if (!autoTax || locked) return;
    if (Math.abs((form.sales_tax || 0) - computedTax) > 0.005) {
      set("sales_tax", computedTax);
    }
  }, [autoTax, locked, computedTax, form.sales_tax, set]);

  const total =
    (form.taxable_sales || 0) + (form.non_taxable || 0) + (form.sales_tax || 0);

  function onTaxableChange(v: number) {
    set("taxable_sales", v);
    if (autoTax && !locked) set("sales_tax", round2(v * salesTaxRate));
  }

  async function onSave() {
    if (busy || locked) return;
    setErr(null);
    setBusy(true);
    try {
      await persist();
      setOpen(false);
    } catch (e) {
      setErr(humanizeError(e, "Could not save sales."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => { setOpen(true); setErr(null); }}
        className={styles.widgetCard}
      >
        <span className={styles.widgetCardTop}>
          <span className={styles.widgetLabel}>Sales</span>
          <span className={styles.widgetTotal}>{fmtMoney2(total)}</span>
        </span>
        <span className={styles.widgetCount}>
          Taxable · Non-taxable · Sales tax
        </span>
      </button>

      <Modal
        open={open}
        title="Sales"
        onClose={() => { setOpen(false); setErr(null); }}
      >
        <div className={styles.lineModalBody}>
          <div className={styles.widgetAddRow}>
            <div className={styles.addRowAmount}>
              <MoneyInput
                label="Taxable sale"
                value={form.taxable_sales}
                onChange={onTaxableChange}
                disabled={locked}
              />
            </div>
            <div className={styles.addRowAmount}>
              <MoneyInput
                label="Non-taxable"
                value={form.non_taxable}
                onChange={(v) => set("non_taxable", v)}
                disabled={locked}
              />
            </div>
            <div className={styles.addRowAmount}>
              <MoneyInput
                label="Sales tax to be paid"
                hint={autoTax
                  ? `Auto: ${(salesTaxRate * 100).toFixed(2)}% of taxable sale`
                  : "Set a Sales tax rate in Settings to auto-calculate"}
                value={form.sales_tax}
                onChange={(v) => set("sales_tax", v)}
                disabled={locked || autoTax}
              />
            </div>
          </div>

          {err && <ErrorRow message={err} />}

          <div className={styles.mtSaveRow}>
            <span className={styles.mtSaveRowLeft}>
              Total: <strong>{fmtMoney2(total)}</strong>
            </span>
            <Button
              type="button"
              tone="primary"
              size="md"
              busy={busy}
              disabled={busy || locked}
              onClick={onSave}
            >
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

// Fees box — groups the store's fee-revenue receipt lines
// (money-order fee, check-cashing fee, return-check hold fee) behind
// one tile + modal, mirroring <SalesWidget>. Same modelling: all
// three are Category-1 report fields (in EDITABLE_KEYS), so the modal
// edits shared form state and its Save persists through the normal
// daily-report PUT. Grouping keeps the "Other receipts" grid short and
// puts the fee lines that used to be loose tiles in one place.
function FeesWidget({
  form, set, locked, persist,
}: {
  form: FormState;
  set: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  locked: boolean;
  persist: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const total =
    (form.money_order_fees || 0) +
    (form.check_cashing_fees || 0) +
    (form.return_check_hold_fees || 0);

  async function onSave() {
    if (busy || locked) return;
    setErr(null);
    setBusy(true);
    try {
      await persist();
      setOpen(false);
    } catch (e) {
      setErr(humanizeError(e, "Could not save fees."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => { setOpen(true); setErr(null); }}
        className={styles.widgetCard}
      >
        <span className={styles.widgetCardTop}>
          <span className={styles.widgetLabel}>Fees</span>
          <span className={styles.widgetTotal}>{fmtMoney2(total)}</span>
        </span>
        <span className={styles.widgetCount}>
          Money order · Check cashing · Return check hold
        </span>
      </button>

      <Modal
        open={open}
        title="Fees"
        onClose={() => { setOpen(false); setErr(null); }}
      >
        <div className={styles.lineModalBody}>
          <div className={styles.widgetAddRow}>
            <div className={styles.addRowAmount}>
              <MoneyInput
                label="Money order fee"
                value={form.money_order_fees}
                onChange={(v) => set("money_order_fees", v)}
                disabled={locked}
              />
            </div>
            <div className={styles.addRowAmount}>
              <MoneyInput
                label="Check cashing fees"
                value={form.check_cashing_fees}
                onChange={(v) => set("check_cashing_fees", v)}
                disabled={locked}
              />
            </div>
            <div className={styles.addRowAmount}>
              <MoneyInput
                label="Return check hold fees"
                value={form.return_check_hold_fees}
                onChange={(v) => set("return_check_hold_fees", v)}
                disabled={locked}
              />
            </div>
          </div>

          {err && <ErrorRow message={err} />}

          <div className={styles.mtSaveRow}>
            <span className={styles.mtSaveRowLeft}>
              Total: <strong>{fmtMoney2(total)}</strong>
            </span>
            <Button
              type="button"
              tone="primary"
              size="md"
              busy={busy}
              disabled={busy || locked}
              onClick={onSave}
            >
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

// Money-transfer breakdown — a tile + modal that mirrors the
// LineItemWidget pattern (cash purchases / expenses).  The tile
// lives in the "In" tab and shows the current `money_transfer`
// total; tapping it opens the per-company breakdown where the
// operator enters amount / fees / federal tax / commission by
// hand.  Manual entry only for now — the transfer-log auto-fill is
// intentionally omitted until that integration is finished (the
// backend still returns `auto_*`, so re-enabling it is UI-only).
function MoneyTransferWidget({
  total, storeId, date, locked, onChange,
}: {
  total: number;
  storeId: number;
  date: string;
  locked: boolean;
  onChange: () => void;
}) {
  const queryClient = useQueryClient();
  const breakdown = useMTBreakdown(date || undefined);

  const [open, setOpen] = useState(false);
  // Local draft state, hydrated from the server payload. Keyed by
  // company name so re-ordering doesn't lose edits.
  const [drafts, setDrafts] = useState<Map<string, MTRowDraft>>(new Map());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

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
  const enteredCount = rows.filter((r) => r.saved_total > 0).length;

  function setCell(company: string, cell: MTCell, value: number) {
    setDrafts((prev) => {
      const next = new Map(prev);
      const cur = next.get(company) ?? emptyDraft();
      next.set(company, { ...cur, [cell]: value });
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
      // money_transfer was mirrored server-side; refresh the report
      // (drives the tile total + Money In) and the breakdown query
      // (re-hydrates the modal from the saved rows).
      await queryClient.invalidateQueries({
        queryKey: ["dailybook", "report", storeId, date],
      });
      await queryClient.invalidateQueries({
        queryKey: ["dailybook", "mt-breakdown", storeId, date],
      });
      onChange();
      setOpen(false);
    } catch (e) {
      setErr(humanizeError(e, "Could not save the breakdown."));
    } finally {
      setBusy(false);
    }
  }

  const isLoading = breakdown.isLoading || breakdown.data == null;

  return (
    <>
      <button
        type="button"
        onClick={() => { setOpen(true); setErr(null); }}
        className={styles.widgetCard}
      >
        <span className={styles.widgetCardTop}>
          <span className={styles.widgetLabel}>Money transfer</span>
          <span className={styles.widgetTotal}>{fmtMoney2(total)}</span>
        </span>
        <span className={styles.widgetCount}>
          {enteredCount > 0
            ? `${enteredCount} ${enteredCount === 1 ? "company" : "companies"}`
            : "Tap to enter breakdown"}
        </span>
      </button>

      <Modal
        open={open}
        size="lg"
        title="Money transfer — per-company breakdown"
        onClose={() => { setOpen(false); setErr(null); }}
      >
        <div className={styles.lineModalBody}>
          <p className={styles.subText}>
            Enter each company's amount, fees, federal tax, and
            commission. The grand total saves to this day's
            <em> Money transfer</em> line and flows into Money In.
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
              Grand total: <strong>{fmtMoney2(draftTotal)}</strong>
            </span>
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
        </div>
      </Modal>
    </>
  );
}

function MTEditableRow({
  row, draft, locked, onCellChange,
}: {
  row: MTBreakdownRow;
  draft: MTRowDraft;
  locked: boolean;
  onCellChange: (cell: MTCell, value: number) => void;
}) {
  const draftTotal = rowDraftTotal(draft);
  return (
    <tr>
      <td className={`${styles.mtTd} ${styles.mtTdStrong}`}>
        <span style={{ color: companyAccent(row.company) }}>•</span>{" "}
        {row.company}
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
  // MoneyInput with prefix="" drops the $ chrome so the cell stays
  // table-tight; the kit's empty-means-zero + wheel-blur + decimal-
  // keypad behaviour carries over from the rest of the SPA.
  return (
    <td className={styles.mtCellTd}>
      <MoneyInput
        value={Number.isFinite(value) ? value : 0}
        onChange={onChange}
        disabled={locked}
        prefix=""
        fullWidth
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
  const [amount, setAmount] = useState(0);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Inline-edit state.  `editingId` is null when no row is being
  // edited.  When set, the row shows three inputs (time / amount /
  // note) + Save / Cancel actions instead of the static cell text.
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTime, setEditTime] = useState("");
  const [editAmount, setEditAmount] = useState(0);
  const [editNote, setEditNote] = useState("");

  function startEdit(item: LineItemRow) {
    setEditingId(item.id);
    setEditTime(item.at_time || "");
    setEditAmount(item.amount);
    setEditNote(item.note || "");
    setErr(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setErr(null);
  }

  async function saveEdit() {
    if (editingId == null || busy) return;
    if (!editAmount || editAmount <= 0) {
      setErr("Amount must be greater than zero.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await updateLineItem(storeId, editingId, {
        at_time: editTime,
        amount: editAmount,
        note: editNote,
      });
      setEditingId(null);
      onChange();
    } catch (e) {
      setErr(humanizeError(e, "Could not save entry."));
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (busy) return;
    setErr(null);
    if (!amount || amount <= 0) {
      setErr("Amount must be greater than zero."); return;
    }
    setBusy(true);
    try {
      await createLineItem(storeId, date, {
        kind, at_time: time, amount, note,
      });
      setTime("");
      setAmount(0);
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
    <>
      <button
        type="button"
        onClick={() => { setOpen(true); setErr(null); }}
        className={styles.widgetCard}
      >
        <span className={styles.widgetCardTop}>
          <span className={styles.widgetLabel}>
            {label}
            {readOnly && <Pill tone="info">Auto</Pill>}
          </span>
          <span className={styles.widgetTotal}>{fmtMoney2(total)}</span>
        </span>
        <span className={styles.widgetCount}>
          {count} {count === 1 ? "entry" : "entries"}
        </span>
      </button>

      <Modal
        open={open}
        title={label}
        size="lg"
        onClose={() => { setOpen(false); cancelEdit(); setErr(null); }}
      >
        <div className={styles.lineModalBody}>
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
                <MoneyInput
                  label="Amount"
                  value={amount}
                  onChange={setAmount}
                  disabled={busy}
                />
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
                  {items.map((item) => {
                    const isEditing = editingId === item.id;
                    const fromReturnCheck = item.return_check_id != null;
                    if (isEditing) {
                      // Inline edit row — three inputs replace the
                      // static cells, with Save / Cancel buttons in
                      // the actions column.  Validation errors flash
                      // above the table via the shared `err` state.
                      return (
                        <tr key={item.id}>
                          <td className={styles.widgetTd}>
                            <Input
                              type="time"
                              value={editTime}
                              onChange={(e) => setEditTime(e.target.value)}
                              disabled={busy}
                            />
                          </td>
                          <td className={styles.widgetTd}>
                            <MoneyInput
                              value={editAmount}
                              onChange={setEditAmount}
                              disabled={busy}
                            />
                          </td>
                          <td className={styles.widgetTd}>
                            <Input
                              type="text"
                              maxLength={120}
                              value={editNote}
                              onChange={(e) => setEditNote(e.target.value)}
                              disabled={busy}
                              placeholder="optional"
                            />
                          </td>
                          <td className={styles.widgetTd}>
                            <div className={styles.editRowActions}>
                              <Button
                                type="button" tone="primary" size="sm"
                                busy={busy} disabled={busy}
                                onClick={() => { void saveEdit(); }}
                              >
                                Save
                              </Button>
                              <Button
                                type="button" tone="secondary" size="sm"
                                disabled={busy} onClick={cancelEdit}
                              >
                                Cancel
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    }
                    return (
                      <tr key={item.id}>
                        <td className={styles.widgetTdMono}>{item.at_time || "—"}</td>
                        <td className={styles.widgetTdMono}>{fmtMoney2(item.amount)}</td>
                        <td className={styles.widgetTd}>{item.note || "—"}</td>
                        {!readOnly && (
                          <td className={styles.widgetTd}>
                            {fromReturnCheck ? (
                              <span className={styles.widgetTdSmall}>
                                from return check
                              </span>
                            ) : (
                              <RowActions
                                label="Actions"
                                actions={[
                                  {
                                    label: "Edit",
                                    onClick: () => startEdit(item),
                                  },
                                  {
                                    label: "Remove",
                                    tone: "danger",
                                    onClick: () => { void remove(item.id); },
                                  },
                                ]}
                              />
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}

// ── Save bar + helpers ──────────────────────────────────────

function StickySaveBar({
  locked, busy, dirty, onCancel, onLockToggle,
}: {
  locked: boolean;
  busy: boolean;
  dirty: boolean;
  onCancel: () => void;
  onLockToggle: () => void;
}) {
  return (
    <div className={styles.saveBar}>
      <div className={styles.saveBarLeft}>
        {locked
          ? "This day is locked. Unlock to edit any field."
          : dirty
            ? <Pill tone="warning" dot>Unsaved changes</Pill>
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

/** Forward balance (opening cash carried from the previous day).
 *  Auto-carried = previous logged day's (Outside cash drops + Safe
 *  balance); the server forces that value on save, so the field is
 *  read-only whenever `auto` is true (every day but the store's very
 *  first). On the first day there's no prior report — the operator
 *  seeds the opening balance once and it carries forward from then
 *  on. Same auto-lock pattern as the sales-tax field. */
function ForwardBalanceInput({
  value, auto, disabled, onChange,
}: {
  value: number;
  auto: boolean;
  disabled?: boolean;
  onChange: (next: number) => void;
}) {
  return (
    <MoneyInput
      label="Forward balance"
      hint={auto
        ? "Auto: yesterday's cash drops + safe balance"
        : "Opening balance — set once; it carries forward automatically."}
      value={Number.isFinite(value) ? value : 0}
      onChange={onChange}
      disabled={disabled || auto}
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
    money_order:             r?.money_order             ?? 0,
    money_order_fees:        r?.money_order_fees        ?? 0,
    check_cashing_fees:      r?.check_cashing_fees      ?? 0,
    return_check_hold_fees:  r?.return_check_hold_fees  ?? 0,
    forward_balance:         r?.forward_balance         ?? 0,
    rebates_commissions:     r?.rebates_commissions     ?? 0,
    cash_deposit:            r?.cash_deposit            ?? 0,
    safe_balance:            r?.safe_balance            ?? 0,
    payroll_expense:         r?.payroll_expense         ?? 0,
    over_short:              r?.over_short              ?? 0,
    notes:                   r?.notes                   ?? "",
  };
}

export function computeTotals(form: FormState | null, report: DailyReportRow | null | undefined) {
  const receiptsEditable = form ? (
    form.taxable_sales + form.non_taxable + form.sales_tax +
    form.bill_payment_charge + form.phone_recargas + form.boost_mobile +
    form.money_order + form.money_order_fees +
    form.check_cashing_fees + form.return_check_hold_fees +
    form.forward_balance + form.rebates_commissions
  ) : 0;
  // `money_transfer` is Category-3 (derived from the mt_summary
  // per-company breakdown, mirrored onto the report). It is NOT an
  // editable form field — reading it from the report row is what
  // keeps Money In in sync with the saved breakdown instead of an
  // unpersisted input.
  const receiptsDerived =
    (report?.money_transfer ?? 0) + (report?.from_bank ?? 0) +
    (report?.other_cash_in ?? 0) + (report?.return_check_paid_back ?? 0);
  const receipts = receiptsEditable + receiptsDerived;

  // NOTE: `safe_balance` is deliberately NOT summed here. The server's
  // DailyReport.total_disbursements excludes it (see
  // api/Modules/DailyBook/INVARIANTS.md) because safe balance is cash
  // RETAINED overnight — it becomes the next day's opening
  // `forward_balance` (carry = prior.outside_cash_drops +
  // prior.safe_balance). Counting it as a disbursement here overstated
  // "Out" and understated the day's position, so the editor disagreed
  // with the calendar/period views (which use the server's net).
  const disbursementsEditable = form ? (
    form.cash_deposit + form.payroll_expense
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
// fmtMoney2 imported from lib/formatters (was local, consolidated).

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

