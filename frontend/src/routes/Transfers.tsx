import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  useTransfers,
  type TransferRow,
} from "../api/transfers";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, EmptyState, ErrorState, Field, Input,
  PageHeader, PageShell, Pager, Select, TableSkeleton, tokens,
} from "../components/ui";

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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror URL search param into local debounced input when URL changes externally (browser back, link arrival)
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
      <PageShell maxWidth="78rem">
        <PageHeader title="Transfers" />
        <Empty>
          Sign in as a store admin to view this store's transfers.
          Owner umbrellas + superadmin store-picker land in a
          follow-up PR.
        </Empty>
      </PageShell>
    );
  }

  const { data, isLoading, isFetching, isError, error, refetch } = apiQuery;

  return (
    <PageShell maxWidth="78rem">
      <PageHeader
        title="Transfers"
        subtitle={data
          ? `${data.total.toLocaleString()} total · page ${data.page} of ${data.total_pages || 1}`
          : "—"}
        actions={(
          <ButtonLink href="/transfers/new" tone="primary">
            + New transfer
          </ButtonLink>
        )}
      />

      <FilterBar
        q={qDraft}
        onQChange={setQDraft}
        dateFrom={dateFrom}
        dateTo={dateTo}
        status={status}
        onSet={setFilter}
        busy={isFetching}
      />

      <Card>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load transfers"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState title="No transfers match these filters." />
        )}
        {data && data.rows.length > 0 && <TransfersTable rows={data.rows} />}
      </Card>

      {data && data.total_pages > 1 && (
        <Pager
          page={data.page}
          totalPages={data.total_pages}
          onPage={setPage}
        />
      )}
    </PageShell>
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
    <Card
      style={{
        marginBottom: "1rem",
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) 8rem 8rem 9rem",
        gap: "0.75rem",
        alignItems: "end",
      }}
    >
      <Field label="Search">
        <Input
          type="search"
          value={q}
          onChange={(e) => onQChange(e.target.value)}
          placeholder="sender, recipient, confirm #, country, batch"
        />
      </Field>
      <Field label="From">
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => onSet("date_from", e.target.value)}
        />
      </Field>
      <Field label="To">
        <Input
          type="date"
          value={dateTo}
          onChange={(e) => onSet("date_to", e.target.value)}
        />
      </Field>
      <Field label="Status">
        <Select
          value={status}
          onChange={(e) => onSet("status", e.target.value)}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </Select>
      </Field>
      {/* Subtle in-flight indicator without shifting layout. */}
      {busy && (
        <span
          style={{
            gridColumn: "1 / -1",
            color: tokens.textMuted,
            fontSize: "0.85rem",
          }}
        >
          Updating…
        </span>
      )}
    </Card>
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
                    color: tokens.textMuted,
                    fontWeight: 500,
                    fontSize: "0.78rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderBottom: `1px solid ${tokens.border}`,
                  }}
                >
                  {h}
                </th>
              ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              style={{ transition: "background 120ms ease" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = tokens.surface;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              <td style={cellStyle}>
                <Link to={`/transfers/${r.id}`} style={linkStyle}>
                  <span style={monoMuted}>{r.send_date}</span>
                </Link>
              </td>
              <td style={cellStyle}>{r.company}</td>
              <td style={cellStyle}>{r.sender_name}</td>
              <td style={cellStyle}>{r.recipient_name || "—"}</td>
              <td style={cellStyle}>{r.country || "—"}</td>
              <td style={cellStyle}>
                <Link to={`/transfers/${r.id}`} style={linkStyle}>
                  <span style={monoMuted}>{r.confirm_number || "—"}</span>
                </Link>
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

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};

const mono: React.CSSProperties = {
  fontFamily: tokens.fontMono,
};

const monoMuted: React.CSSProperties = {
  ...mono,
  fontSize: "0.85rem",
  color: tokens.textMuted,
};

const linkStyle: React.CSSProperties = {
  color: "inherit",
  textDecoration: "none",
};
