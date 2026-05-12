import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import {
  BANK_CATEGORY_OPTIONS,
  categorizeTransaction,
  uncategorizeTransaction,
  useBankAccounts,
  useBankTransactions,
  type BankTransactionFilters,
  type BankTransactionRow,
} from "../api/bankSync";
import {
  Card, Empty, EmptyState, ErrorState, Field, inputStyle, monoStyle,
  PageHeader, PageShell, Pager, TableSkeleton, tokens,
} from "../components/ui";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// Bank transactions at /app/bank-transactions. Filters: account,
// sign, uncategorized-only, free-text search. Each row's category
// cell is editable inline — pick a slug from the dropdown and the
// SPA POSTs /bank/transactions/{id}/categorize, which (for daily-
// book kinds) auto-creates the matching DailyLineItem.
//
// Connect / disconnect / sync still live on legacy /bank/* (Stripe
// Financial Connections needs Stripe.js to drive the modal). Rule
// CRUD ships in a follow-up.

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
    next.delete("page");
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
      <PageShell>
        <PageHeader title="Bank transactions" />
        <Empty>Sign in as a store admin to view bank transactions.</Empty>
      </PageShell>
    );
  }

  const totalPages = txns.data?.total_pages ?? 1;
  const page       = txns.data?.page        ?? 1;

  return (
    <PageShell>
      <PageHeader
        title="Bank transactions"
        subtitle={
          txns.data
            ? `${txns.data.total.toLocaleString()} txns · ` +
              `${txns.data.uncategorized_count.toLocaleString()} uncategorized`
            : "—"
        }
        actions={
          <a
            href="/bank"
            style={{
              color: tokens.textMuted,
              fontSize: "0.85rem",
              textDecoration: "underline",
            }}
          >
            Connect / sync (legacy) →
          </a>
        }
      />

      <Card>
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
                <option key={a.id} value={a.id}>{a.label}</option>
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

        {txns.isLoading && <TableSkeleton rows={5} cols={5} />}
        {txns.isError && (
          <ErrorState
            message={txns.error instanceof Error ? txns.error.message : "Could not load"}
            onRetry={() => { void txns.refetch(); }}
          />
        )}
        {txns.data && txns.data.rows.length === 0 && !txns.isLoading && (
          <EmptyState title="No transactions match these filters." />
        )}
        {txns.data && txns.data.rows.length > 0 && (
          <>
            <Table rows={txns.data.rows} />
            <Pager
              page={page}
              totalPages={totalPages}
              onPage={setPage}
              leading={
                <span style={{ color: tokens.textMuted, fontSize: "0.85rem" }}>
                  Page total:{" "}
                  <span style={monoStyle}>
                    ${(txns.data.page_total_cents / 100).toFixed(2)}
                  </span>
                </span>
              }
            />
          </>
        )}
      </Card>
    </PageShell>
  );
}

function Table({ rows }: { rows: BankTransactionRow[] }) {
  const qc = useQueryClient();
  const identity = getCurrentIdentity();
  function refresh() {
    qc.invalidateQueries({
      queryKey: ["bank", "transactions", identity?.store_id],
    });
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}
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
              <th key={i} style={{ ...thStyle, textAlign: align as "left" | "right" }}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={cellStyle}>
                <span style={{ ...monoStyle, fontSize: "0.85rem", color: tokens.textMuted }}>
                  {r.posted_at.slice(0, 10)}
                </span>
              </td>
              <td style={cellStyle}>{r.description || "—"}</td>
              <td style={cellStyle}>
                <span style={{ color: tokens.textMuted, fontSize: "0.85rem" }}>
                  {r.account_label || `acct ${r.account_id}`}
                </span>
              </td>
              <td style={cellStyle}>
                <CategoryCell row={r} onChanged={refresh} />
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span
                  style={{
                    ...monoStyle,
                    color: r.amount_cents > 0 ? tokens.accent : tokens.text,
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

function CategoryCell({
  row, onChanged,
}: {
  row: BankTransactionRow;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function pick(slug: string) {
    setErr(null); setBusy(true);
    try {
      if (slug === "") {
        await uncategorizeTransaction(row.id);
      } else {
        await categorizeTransaction(row.id, {
          target_kind: slug,
          // Default off — matches the legacy "tag the bank txn,
          // don't double-post into daily book unless I tick the
          // box". A future PR can add a per-row checkbox.
          post_to_daily: false,
        });
      }
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not update category.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
      <select
        value={row.category_slug}
        onChange={(e) => pick(e.target.value)}
        disabled={busy}
        style={{
          ...inputStyle,
          width: "auto",
          minWidth: "10rem",
          padding: "0.3rem 0.5rem",
          fontSize: "0.85rem",
          fontFamily: row.category_slug ? tokens.fontMono : undefined,
        }}
      >
        <option value="">— uncategorized —</option>
        {BANK_CATEGORY_OPTIONS.map((c) => (
          <option key={c.slug} value={c.slug}>{c.label}</option>
        ))}
      </select>
      {err && (
        <span title={err} style={{ color: tokens.negative, fontSize: "0.8rem" }}>
          ⚠
        </span>
      )}
    </div>
  );
}

// ── Cell + header styles (table-specific, kept local) ──────────

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};

const thStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  color: tokens.textMuted,
  fontWeight: 500,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: `1px solid ${tokens.border}`,
};
