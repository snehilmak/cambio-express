import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createLineItem,
  deleteLineItem,
  lockDailyReport,
  unlockDailyReport,
  useDailyReport,
  useLineItems,
  type DailyReportRow,
  type LineItemRow,
} from "../api/dailybook";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, EmptyState, ErrorState, Loading, PageHeader,
  PageShell, Section, tokens,
} from "../components/ui";

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
  const { data, isLoading, isError, error, isFetching, refetch } = useDailyReport(date);
  const queryClient = useQueryClient();
  const [lockBusy, setLockBusy] = useState(false);
  const [lockError, setLockError] = useState<string | null>(null);

  async function toggleLock() {
    if (identity?.store_id == null) return;
    setLockError(null);
    setLockBusy(true);
    try {
      if (data?.locked) {
        await unlockDailyReport(identity.store_id, date);
      } else {
        await lockDailyReport(identity.store_id, date);
      }
      // Refresh the read-side hook for this day so the UI flips.
      await queryClient.invalidateQueries({
        queryKey: ["dailybook", "report", identity.store_id, date],
      });
    } catch (err) {
      setLockError(
        err instanceof ApiError
          ? err.message
          : "Could not change lock state.",
      );
    } finally {
      setLockBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="78rem" gap="1rem">
        <PageHeader title="Daily book" />
        <Empty>Sign in as a store admin to view the daily book.</Empty>
      </PageShell>
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
    <PageShell maxWidth="78rem" gap="1rem">
      <PageHeader
        title="Daily book"
        subtitle={(
          <span style={{ fontFamily: tokens.fontMono }}>
            {date}
            {data?.locked && (
              <span
                style={{
                  marginLeft: "0.75rem",
                  fontSize: "0.78rem",
                  padding: "0.15rem 0.5rem",
                  borderRadius: "999px",
                  background: "var(--db-warning-bg, #2a1a00)",
                  color: tokens.warning,
                  letterSpacing: "0.05em",
                }}
              >
                LOCKED
              </span>
            )}
          </span>
        )}
        actions={(
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
            <button
              type="button"
              onClick={toggleLock}
              disabled={lockBusy}
              style={{
                background: "transparent",
                color: tokens.text,
                border: `1px solid ${tokens.border}`,
                borderRadius: "0.5rem",
                padding: "0.45rem 0.85rem",
                fontFamily: tokens.fontBody,
                fontSize: "0.85rem",
                cursor: lockBusy ? "wait" : "pointer",
                opacity: lockBusy ? 0.6 : 1,
                marginLeft: "0.5rem",
              }}
            >
              {lockBusy ? "…" : data?.locked ? "Unlock" : "Lock"}
            </button>
            <ButtonLink
              href={`/daily/edit?date=${date}`}
              tone="primary"
              size="sm"
            >
              Edit
            </ButtonLink>
          </div>
        )}
      />
      {lockError && (
        <p
          role="alert"
          style={{
            margin: "0 0 1rem",
            color: tokens.negative,
            fontSize: "0.9rem",
          }}
        >
          {lockError}
        </p>
      )}

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load report"}
          onRetry={() => { void refetch(); }}
        />
      )}
      {!isLoading && !isError && data == null && (
        <EmptyState
          title="No daily report logged for this date."
          body={isFetching ? "Updating…" : undefined}
        />
      )}
      {data && <ReportContent r={data} />}
      {!isLoading && !isError && identity?.store_id != null && (
        <LineItemsSection
          storeId={identity.store_id}
          date={date}
          locked={Boolean(data?.locked)}
        />
      )}
    </PageShell>
  );
}

// Line items grouped by kind. Add + delete inline; the daily
// report's derived fields (cash_purchases, drops, etc.) recompute
// server-side after each mutation, so the badge/total elsewhere
// on the page reflects new state on the next refetch.
const LINE_ITEM_KINDS: Array<{ kind: string; label: string }> = [
  { kind: "drop",            label: "Drops" },
  { kind: "check_deposit",   label: "Check deposits" },
  { kind: "cash_expense",    label: "Cash expenses" },
  { kind: "check_expense",   label: "Check expenses" },
  { kind: "cash_purchase",   label: "Cash purchases" },
  { kind: "check_purchase",  label: "Check purchases" },
  { kind: "other_cash_in",   label: "Other cash in" },
  { kind: "other_cash_out",  label: "Other cash out" },
  { kind: "return_payback",  label: "Return paybacks" },
];

function LineItemsSection({
  storeId, date, locked,
}: { storeId: number; date: string; locked: boolean }) {
  return (
    <Section title="Line items">
      <Card padding="1.25rem 1.5rem">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(20rem, 1fr))",
            gap: "1rem",
          }}
        >
          {LINE_ITEM_KINDS.map((k) => (
            <KindGroup
              key={k.kind}
              storeId={storeId}
              date={date}
              kind={k.kind}
              label={k.label}
              locked={locked}
            />
          ))}
        </div>
      </Card>
    </Section>
  );
}

function KindGroup({
  storeId, date, kind, label, locked,
}: {
  storeId: number; date: string; kind: string; label: string;
  locked: boolean;
}) {
  const queryClient = useQueryClient();
  const { data } = useLineItems(date, kind);
  const items = data?.items ?? [];
  const total = items.reduce((s, r) => s + (r.amount || 0), 0);

  const [time, setTime] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function refetch() {
    queryClient.invalidateQueries({
      queryKey: ["dailybook", "line-items", storeId, date, kind],
    });
    queryClient.invalidateQueries({
      queryKey: ["dailybook", "report", storeId, date],
    });
  }

  async function add() {
    setErr(null);
    setBusy(true);
    try {
      await createLineItem(storeId, date, {
        kind, at_time: time, amount: Number(amount), note,
      });
      setTime(""); setAmount(""); setNote("");
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't add row");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: LineItemRow) {
    setErr(null);
    try {
      await deleteLineItem(storeId, row.id);
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't delete");
    }
  }

  return (
    <div
      style={{
        background: tokens.surface,
        border: `1px solid ${tokens.borderSubtle}`,
        borderRadius: "0.5rem",
        padding: "0.75rem 1rem",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "0.5rem",
        }}
      >
        <h3
          style={{
            fontFamily: tokens.fontBody,
            fontSize: "0.95rem",
            fontWeight: 500,
            margin: 0,
          }}
        >
          {label}
        </h3>
        <span
          style={{
            fontFamily: tokens.fontMono,
            fontSize: "0.85rem",
            color: tokens.textMuted,
          }}
        >
          ${total.toFixed(2)}
        </span>
      </header>

      {items.length === 0 ? (
        <p
          style={{
            margin: "0.25rem 0 0.75rem",
            fontSize: "0.85rem",
            color: tokens.textMuted,
          }}
        >
          No entries yet.
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0 0 0.5rem" }}>
          {items.map((r) => (
            <li
              key={r.id}
              style={{
                display: "flex",
                gap: "0.5rem",
                alignItems: "baseline",
                padding: "0.35rem 0",
                borderBottom: `1px solid ${tokens.borderSubtle}`,
                fontSize: "0.9rem",
              }}
            >
              <span
                style={{
                  fontFamily: tokens.fontMono,
                  color: tokens.textMuted,
                  minWidth: "3.5rem",
                }}
              >
                {r.at_time}
              </span>
              <span
                style={{
                  fontFamily: tokens.fontMono,
                  minWidth: "5rem",
                }}
              >
                ${r.amount.toFixed(2)}
              </span>
              <span style={{ flex: 1, color: tokens.textMuted }}>
                {r.note || "—"}
              </span>
              <button
                type="button"
                onClick={() => remove(r)}
                disabled={locked || r.return_check_id != null}
                title={
                  r.return_check_id != null
                    ? "Linked to a return check; remove from Books → Return Checks"
                    : locked ? "Day is locked" : "Delete"
                }
                style={{
                  background: "transparent",
                  color: tokens.textMuted,
                  border: "none",
                  cursor:
                    locked || r.return_check_id != null
                      ? "not-allowed" : "pointer",
                  fontSize: "0.85rem",
                }}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {!locked && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "5rem 6rem 1fr auto",
            gap: "0.4rem",
            marginTop: "0.4rem",
          }}
        >
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            placeholder="HH:MM"
            style={miniInputStyle}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Amount"
            style={miniInputStyle}
          />
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional)"
            style={miniInputStyle}
          />
          <button
            type="button"
            onClick={add}
            disabled={busy || !time || !amount}
            style={{
              background: tokens.accent,
              color: tokens.onAccent,
              border: "none",
              borderRadius: "0.4rem",
              padding: "0.35rem 0.75rem",
              fontSize: "0.85rem",
              fontWeight: 600,
              cursor: busy ? "wait" : "pointer",
              opacity: busy || !time || !amount ? 0.6 : 1,
            }}
          >
            {busy ? "…" : "+ Add"}
          </button>
        </div>
      )}
      {err && (
        <p
          role="alert"
          style={{
            margin: "0.4rem 0 0",
            fontSize: "0.8rem",
            color: tokens.negative,
          }}
        >
          {err}
        </p>
      )}
    </div>
  );
}

const miniInputStyle: React.CSSProperties = {
  background: tokens.surface2,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.4rem",
  padding: "0.35rem 0.5rem",
  color: tokens.text,
  fontFamily: tokens.fontBody,
  fontSize: "0.85rem",
  outline: "none",
};

function ReportContent({ r }: { r: DailyReportRow }) {
  return (
    <>
      <Section title="Totals">
        <Card>
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
        </Card>
      </Section>

      <Section title="Receipts">
        <Card>
          <Grid>
            <Stat label="Taxable sales"  value={r.taxable_sales} />
            <Stat label="Non-taxable"    value={r.non_taxable} />
            <Stat label="Sales tax"      value={r.sales_tax} />
            <Stat label="Money transfer" value={r.money_transfer} />
            <Stat label="Money order"    value={r.money_order} />
          </Grid>
        </Card>
      </Section>

      <Section title="Disbursements">
        <Card>
          <Grid>
            <Stat label="Cash expense"    value={r.cash_expense} />
            <Stat label="Check expense"   value={r.check_expense} />
            <Stat label="Cash deposit"    value={r.cash_deposit} />
            <Stat label="Checks deposit"  value={r.checks_deposit} />
          </Grid>
        </Card>
      </Section>

      {r.notes && (
        <Section title="Notes">
          <Card>
            <p
              style={{
                margin: 0,
                color: tokens.text,
                whiteSpace: "pre-wrap",
                lineHeight: 1.6,
              }}
            >
              {r.notes}
            </p>
          </Card>
        </Section>
      )}
    </>
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
    ? tokens.accent
    : negative
      ? tokens.negative
      : tokens.text;
  return (
    <div
      style={{
        background: tokens.surface,
        border: `1px solid ${tokens.borderSubtle}`,
        borderRadius: "0.5rem",
        padding: "0.75rem 0.9rem",
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: "0.78rem",
          color: tokens.textMuted,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </p>
      <p
        style={{
          margin: "0.25rem 0 0",
          fontFamily: tokens.fontMono,
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

const dateBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.45rem 0.75rem",
  fontFamily: tokens.fontBody,
  fontSize: "0.85rem",
  cursor: "pointer",
};

const dateInputStyle: React.CSSProperties = {
  background: tokens.surface,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.45rem 0.75rem",
  color: tokens.text,
  fontFamily: tokens.fontMono,
  fontSize: "0.9rem",
  outline: "none",
};
