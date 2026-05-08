import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
          <button
            type="button"
            onClick={toggleLock}
            disabled={lockBusy}
            style={{
              background: "transparent",
              color: "var(--db-text, #f5f5f5)",
              border: "1px solid var(--db-border, #262626)",
              borderRadius: "0.5rem",
              padding: "0.45rem 0.85rem",
              fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
              fontSize: "0.85rem",
              cursor: lockBusy ? "wait" : "pointer",
              opacity: lockBusy ? 0.6 : 1,
              marginLeft: "0.5rem",
            }}
          >
            {lockBusy ? "…" : data?.locked ? "Unlock" : "Lock"}
          </button>
          <Link
            to={`/daily/edit?date=${date}`}
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
        </div>
      </header>
      {lockError && (
        <p
          role="alert"
          style={{
            margin: "0 0 1rem",
            color: "var(--db-negative, #ff3b30)",
            fontSize: "0.9rem",
          }}
        >
          {lockError}
        </p>
      )}

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
      {!isLoading && !isError && identity?.store_id != null && (
        <LineItemsSection
          storeId={identity.store_id}
          date={date}
          locked={Boolean(data?.locked)}
        />
      )}
    </main>
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
    <section
      style={{
        background: "var(--db-surface-2, #141414)",
        border: "1px solid var(--db-border, #262626)",
        borderRadius: "0.75rem",
        padding: "1.25rem 1.5rem",
      }}
    >
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
        Line items
      </h2>
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
    </section>
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
        background: "var(--db-surface, #0a0a0a)",
        border: "1px solid var(--db-border-subtle, #1f1f1f)",
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
            fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
            fontSize: "0.95rem",
            fontWeight: 500,
            margin: 0,
          }}
        >
          {label}
        </h3>
        <span
          style={{
            fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
            fontSize: "0.85rem",
            color: "var(--db-text-muted, #a3a3a3)",
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
            color: "var(--db-text-muted, #a3a3a3)",
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
                borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
                fontSize: "0.9rem",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
                  color: "var(--db-text-muted, #a3a3a3)",
                  minWidth: "3.5rem",
                }}
              >
                {r.at_time}
              </span>
              <span
                style={{
                  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
                  minWidth: "5rem",
                }}
              >
                ${r.amount.toFixed(2)}
              </span>
              <span style={{ flex: 1, color: "var(--db-text-muted, #a3a3a3)" }}>
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
                  color: "var(--db-text-muted, #a3a3a3)",
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
              background: "var(--db-accent, #3fff00)",
              color: "var(--db-on-accent, #0a0a0a)",
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
            color: "var(--db-negative, #ff3b30)",
          }}
        >
          {err}
        </p>
      )}
    </div>
  );
}

const miniInputStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.4rem",
  padding: "0.35rem 0.5rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.85rem",
  outline: "none",
};

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
