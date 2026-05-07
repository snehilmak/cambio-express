import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useTransfers,
  type TransferRow,
} from "../api/transfers";
import { getCurrentIdentity } from "../lib/auth";

// Full transfers list page at /app/transfers.
//
// Mirrors the legacy /transfers Jinja page's UX: live-search box
// (debounced 300ms, 2-char minimum per CLAUDE.md), date-range
// filters, status dropdown, paginated table. URL query string
// holds the active filter state so deep-linking + back-button
// behave correctly.
//
// The actual API call is `useTransfers` from src/api/transfers —
// same controller as the dashboard's recent-transfers card, just
// with full filters + pagination wired up.
const PAGE_SIZE = 50;

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "Sent", label: "Sent" },
  { value: "Pending", label: "Pending" },
  { value: "Cancelled", label: "Cancelled" },
  { value: "Returned", label: "Returned" },
];

export default function Transfers() {
  const identity = getCurrentIdentity();
  const [searchParams, setSearchParams] = useSearchParams();

  // The form state lives in the URL — that way refresh + back
  // restore the filters, and a shared link reproduces the view.
  const q         = searchParams.get("q") ?? "";
  const dateFrom  = searchParams.get("date_from") ?? "";
  const dateTo    = searchParams.get("date_to") ?? "";
  const status    = searchParams.get("status") ?? "";
  const page      = Number(searchParams.get("page") ?? "1") || 1;

  // Local mirror of `q` with debounce — prevents a query per
  // keystroke. 300ms matches the legacy Jinja site's debounce
  // (CLAUDE.md "Table search UX" invariant).
  const [qDraft, setQDraft] = useState(q);
  useEffect(() => {
    if (qDraft === q) return;
    const id = window.setTimeout(() => {
      // 2-char minimum, also matches legacy.
      const next = qDraft.length === 0 || qDraft.length >= 2 ? qDraft : q;
      const params = new URLSearchParams(searchParams);
      if (next) params.set("q", next);
      else params.delete("q");
      params.set("page", "1");
      setSearchParams(params, { replace: true });
    }, 300);
    return () => window.clearTimeout(id);
  }, [qDraft, q, searchParams, setSearchParams]);

  // Reset local draft when URL changes from elsewhere (browser
  // back, link arrival).
  useEffect(() => {
    setQDraft(q);
  }, [q]);

  const apiQuery = useTransfers({
    page, perPage: PAGE_SIZE,
    q: q.length >= 2 ? q : undefined,
    date_from: dateFrom || undefined,
    date_to:   dateTo || undefined,
    status:    status || undefined,
  });

  function setFilter(key: string, value: string) {
    const params = new URLSearchParams(searchParams);
    if (value) params.set(key, value);
    else params.delete(key);
    params.set("page", "1");  // reset paging on filter change
    setSearchParams(params, { replace: true });
  }

  function setPage(next: number) {
    const params = new URLSearchParams(searchParams);
    params.set("page", String(next));
    setSearchParams(params);
  }

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Transfers</h1>
        <p style={{ color: "var(--db-text-muted, #a3a3a3)" }}>
          Sign in as a store admin to view this store's transfers.
          Owner umbrellas + superadmin store-picker land in a
          follow-up PR.
        </p>
      </main>
    );
  }

  const { data, isLoading, isFetching, isError, error } = apiQuery;

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>Transfers</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
          }}
        >
          {data
            ? `${data.total.toLocaleString()} total · page ${data.page} of ${
                data.total_pages || 1
              }`
            : "—"}
        </p>
      </header>

      <FilterBar
        q={qDraft}
        onQChange={setQDraft}
        dateFrom={dateFrom}
        dateTo={dateTo}
        status={status}
        onSet={setFilter}
        busy={isFetching}
      />

      <section style={cardStyle}>
        {isLoading && <Empty>Loading…</Empty>}
        {isError && (
          <Empty error>
            {error instanceof Error ? error.message : "Could not load transfers"}
          </Empty>
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <Empty>No transfers match these filters.</Empty>
        )}
        {data && data.rows.length > 0 && <TransfersTable rows={data.rows} />}
      </section>

      {data && data.total_pages > 1 && (
        <Pager
          page={data.page}
          totalPages={data.total_pages}
          onChange={setPage}
        />
      )}
    </main>
  );
}

interface FilterBarProps {
  q: string;
  onQChange: (q: string) => void;
  dateFrom: string;
  dateTo: string;
  status: string;
  onSet: (key: string, value: string) => void;
  busy: boolean;
}

function FilterBar({
  q, onQChange, dateFrom, dateTo, status, onSet, busy,
}: FilterBarProps) {
  return (
    <section
      style={{
        ...cardStyle,
        marginBottom: "1rem",
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) 8rem 8rem 9rem",
        gap: "0.75rem",
        alignItems: "end",
      }}
    >
      <Field label="Search">
        <input
          type="search"
          value={q}
          onChange={(e) => onQChange(e.target.value)}
          placeholder="sender, recipient, confirm #, country, batch"
          style={inputStyle}
        />
      </Field>
      <Field label="From">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onSet("date_from", e.target.value)}
          style={inputStyle}
        />
      </Field>
      <Field label="To">
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onSet("date_to", e.target.value)}
          style={inputStyle}
        />
      </Field>
      <Field label="Status">
        <select
          value={status}
          onChange={(e) => onSet("status", e.target.value)}
          style={inputStyle}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </Field>
      {/* Subtle in-flight indicator without shifting layout. */}
      {busy && (
        <span
          style={{
            gridColumn: "1 / -1",
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.85rem",
          }}
        >
          Updating…
        </span>
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
      <span style={fieldLabelStyle}>{label}</span>
      {children}
    </label>
  );
}

function TransfersTable({ rows }: { rows: TransferRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}>
        <thead>
          <tr>
            {["Date", "Company", "Sender", "Recipient", "Country", "Confirm #", "Status", "Total"]
              .map((h, i, a) => (
                <th
                  key={h}
                  style={{
                    textAlign: i === a.length - 1 ? "right" : "left",
                    padding: "0.6rem 0.75rem",
                    color: "var(--db-text-muted, #a3a3a3)",
                    fontWeight: 500,
                    fontSize: "0.78rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderBottom: "1px solid var(--db-border, #262626)",
                  }}
                >
                  {h}
                </th>
              ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={cellStyle}>
                <span style={monoMuted}>{r.send_date}</span>
              </td>
              <td style={cellStyle}>{r.company}</td>
              <td style={cellStyle}>{r.sender_name}</td>
              <td style={cellStyle}>{r.recipient_name || "—"}</td>
              <td style={cellStyle}>{r.country || "—"}</td>
              <td style={cellStyle}>
                <span style={monoMuted}>{r.confirm_number || "—"}</span>
              </td>
              <td style={cellStyle}>{r.status}</td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.total_collected.toFixed(2)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pager({
  page, totalPages, onChange,
}: {
  page: number; totalPages: number; onChange: (p: number) => void;
}) {
  return (
    <nav
      style={{
        marginTop: "1rem",
        display: "flex",
        gap: "0.5rem",
        justifyContent: "center",
      }}
    >
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        style={pagerBtnStyle(page <= 1)}
      >
        ← Previous
      </button>
      <span
        style={{
          alignSelf: "center",
          color: "var(--db-text-muted, #a3a3a3)",
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
          fontSize: "0.9rem",
        }}
      >
        {page} / {totalPages}
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        style={pagerBtnStyle(page >= totalPages)}
      >
        Next →
      </button>
    </nav>
  );
}

function Empty({
  children, error,
}: { children: React.ReactNode; error?: boolean }) {
  return (
    <p
      style={{
        margin: 0,
        padding: "2rem 0",
        textAlign: "center",
        color: error
          ? "var(--db-negative, #ff3b30)"
          : "var(--db-text-muted, #a3a3a3)",
      }}
    >
      {children}
    </p>
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
  padding: "1.25rem",
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "var(--db-text-muted, #a3a3a3)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const mono: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const monoMuted: React.CSSProperties = {
  ...mono,
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
};

const pagerBtnStyle = (disabled: boolean): React.CSSProperties => ({
  background: "transparent",
  color: disabled
    ? "var(--db-text-muted, #a3a3a3)"
    : "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.45rem 0.85rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.9rem",
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.5 : 1,
});
