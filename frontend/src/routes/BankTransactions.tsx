import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useBankAccounts,
  useBankTransactions,
  type BankTransactionFilters,
  type BankTransactionRow,
} from "../api/bankSync";
import { getCurrentIdentity } from "../lib/auth";

// Read-only bank-transactions page at /app/bank-transactions.
// Filters: account, sign, uncategorized-only, free-text search.
// Categorize / uncategorize / move-date and rule CRUD still live
// on the legacy /bank/* pages until subsequent PRs migrate the
// write-side. The legacy /bank entry-point is still reachable
// from the topbar's "open in legacy" link below.

const PER_PAGE = 50;

export default function BankTransactions() {
  const identity = getCurrentIdentity();
  const accounts = useBankAccounts();
  const [sp, setSP] = useSearchParams();

  const filters: BankTransactionFilters = useMemo(() => ({
    posted_from:        sp.get("posted_from") ?? "",
    posted_to:          sp.get("posted_to")   ?? "",
    account_id:         sp.get("account_id")  ?? "",
    sign:               (sp.get("sign") as "" | "credit" | "debit") ?? "",
    q:                  sp.get("q")           ?? "",
    uncategorized_only: sp.get("uncategorized_only") === "1",
    page:               Number(sp.get("page") ?? 1),
    per_page:           PER_PAGE,
  }), [sp]);

  const txns = useBankTransactions(filters);
  const [qDraft, setQDraft] = useState(filters.q ?? "");

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else       next.delete(key);
    next.delete("page");  // reset paging on any filter change
    setSP(next, { replace: true });
  }

  function setPage(page: number) {
    const next = new URLSearchParams(sp);
    if (page > 1) next.set("page", String(page));
    else          next.delete("page");
    setSP(next, { replace: true });
  }

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Bank transactions</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to view bank transactions.
        </p>
      </main>
    );
  }

  const totalPages = txns.data?.total_pages ?? 1;
  const page       = txns.data?.page        ?? 1;

  return (
    <main style={pageStyle}>
      <header
        style={{
          marginBottom: "1.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={titleStyle}>Bank transactions</h1>
          <p style={{ margin: "0.35rem 0 0", color: "var(--db-text-muted, #a3a3a3)" }}>
            {txns.data
              ? `${txns.data.total.toLocaleString()} txns · ` +
                `${txns.data.uncategorized_count.toLocaleString()} uncategorized`
              : "—"}
          </p>
        </div>
        <a
          href="/bank"
          style={{
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.85rem",
            textDecoration: "underline",
          }}
        >
          Connect / sync (legacy) →
        </a>
      </header>

      <section style={cardStyle}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))",
            gap: "0.75rem",
            marginBottom: "1rem",
          }}
        >
          <Field label="Search">
            <input
              type="search"
              value={qDraft}
              placeholder="Description…"
              onChange={(e) => setQDraft(e.target.value)}
              onBlur={() => setParam("q", qDraft.trim())}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  setParam("q", qDraft.trim());
                }
              }}
              style={inputStyle}
            />
          </Field>
          <Field label="Account">
            <select
              value={filters.account_id ?? ""}
              onChange={(e) => setParam("account_id", e.target.value)}
              style={inputStyle}
            >
              <option value="">All accounts</option>
              {accounts.data?.rows.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sign">
            <select
              value={filters.sign ?? ""}
              onChange={(e) =>
                setParam("sign", e.target.value as "credit" | "debit" | "")
              }
              style={inputStyle}
            >
              <option value="">Any</option>
              <option value="credit">Credit</option>
              <option value="debit">Debit</option>
            </select>
          </Field>
          <Field label="From">
            <input
              type="date"
              value={filters.posted_from ?? ""}
              onChange={(e) => setParam("posted_from", e.target.value)}
              style={inputStyle}
            />
          </Field>
          <Field label="To">
            <input
              type="date"
              value={filters.posted_to ?? ""}
              onChange={(e) => setParam("posted_to", e.target.value)}
              style={inputStyle}
            />
          </Field>
          <Field label="Filter">
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.55rem 0",
                fontSize: "0.95rem",
              }}
            >
              <input
                type="checkbox"
                checked={filters.uncategorized_only}
                onChange={(e) =>
                  setParam("uncategorized_only", e.target.checked ? "1" : "")
                }
              />
              <span>Uncategorized only</span>
            </label>
          </Field>
        </div>

        {txns.isLoading && <Empty>Loading…</Empty>}
        {txns.isError && (
          <Empty error>
            {txns.error instanceof Error ? txns.error.message : "Could not load"}
          </Empty>
        )}
        {txns.data && txns.data.rows.length === 0 && !txns.isLoading && (
          <Empty>No transactions match these filters.</Empty>
        )}
        {txns.data && txns.data.rows.length > 0 && (
          <>
            <Table rows={txns.data.rows} />
            <Pager
              page={page}
              totalPages={totalPages}
              onPage={setPage}
              pageTotalCents={txns.data.page_total_cents}
            />
          </>
        )}
      </section>
    </main>
  );
}

function Table({ rows }: { rows: BankTransactionRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.92rem",
        }}
      >
        <thead>
          <tr>
            {[
              ["Posted",      "left"],
              ["Description", "left"],
              ["Account",     "left"],
              ["Category",    "left"],
              ["Amount",      "right"],
            ].map(([label, align], i) => (
              <th
                key={i}
                style={{
                  textAlign: align as "left" | "right",
                  padding: "0.6rem 0.75rem",
                  color: "var(--db-text-muted, #a3a3a3)",
                  fontWeight: 500,
                  fontSize: "0.78rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  borderBottom: "1px solid var(--db-border, #262626)",
                }}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={cellStyle}>
                <span style={monoMuted}>{r.posted_at.slice(0, 10)}</span>
              </td>
              <td style={cellStyle}>{r.description || "—"}</td>
              <td style={cellStyle}>
                <span
                  style={{
                    color: "var(--db-text-muted, #a3a3a3)",
                    fontSize: "0.85rem",
                  }}
                >
                  {r.account_label || `acct ${r.account_id}`}
                </span>
              </td>
              <td style={cellStyle}>
                {r.category_slug ? (
                  <span style={categoryPill}>{r.category_slug}</span>
                ) : (
                  <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>
                    uncategorized
                  </span>
                )}
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span
                  style={{
                    ...mono,
                    color:
                      r.amount_cents > 0
                        ? "var(--db-accent, #3fff00)"
                        : "var(--db-text, #f5f5f5)",
                  }}
                >
                  {r.amount_cents > 0 ? "+" : ""}${r.amount.toFixed(2)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Pager({
  page, totalPages, onPage, pageTotalCents,
}: {
  page: number;
  totalPages: number;
  onPage: (p: number) => void;
  pageTotalCents: number;
}) {
  if (totalPages <= 1 && pageTotalCents === 0) return null;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginTop: "1rem",
        gap: "1rem",
      }}
    >
      <span style={{ color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem" }}>
        Page total:{" "}
        <span style={mono}>${(pageTotalCents / 100).toFixed(2)}</span>
      </span>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          style={{
            ...pagerBtn,
            opacity: page <= 1 ? 0.4 : 1,
            cursor: page <= 1 ? "not-allowed" : "pointer",
          }}
        >
          ← Prev
        </button>
        <span
          style={{
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.85rem",
            alignSelf: "center",
          }}
        >
          {page} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
          style={{
            ...pagerBtn,
            opacity: page >= totalPages ? 0.4 : 1,
            cursor: page >= totalPages ? "not-allowed" : "pointer",
          }}
        >
          Next →
        </button>
      </div>
    </div>
  );
}

function Field({
  label, children,
}: {
  label: string;
  children: React.ReactNode;
}) {
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
  padding: "2rem 1.5rem",
  maxWidth: "82rem",
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

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
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

const categoryPill: React.CSSProperties = {
  display: "inline-block",
  background: "rgba(63,255,0,0.12)",
  color: "var(--db-accent, #3fff00)",
  borderRadius: "999px",
  padding: "0.15rem 0.55rem",
  fontSize: "0.78rem",
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const pagerBtn: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.4rem 0.9rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.85rem",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
