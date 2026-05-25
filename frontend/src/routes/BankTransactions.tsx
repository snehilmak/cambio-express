import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import {
  BANK_CATEGORY_OPTIONS,
  categorizeTransaction,
  syncBankTransactions,
  uncategorizeTransaction,
  useBankAccounts,
  useBankTransactions,
  type BankAccountRow,
  type BankTransactionFilters,
  type BankTransactionRow,
} from "../api/bankSync";
import {
  Breadcrumbs, Button, ButtonLink,
  Card, Empty, EmptyState, ErrorState, Field, Input, KpiCard, KpiGrid,
  monoStyle, PageHeader, PageShell, Pager, Select, Table, TableSkeleton,
  tdStyle, thStyle,
} from "../components/ui";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./BankTransactions.module.css";

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
  const qc = useQueryClient();
  const [sp, setSP] = useSearchParams();
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

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
      <PageShell maxWidth="80rem">
        <PageHeader title="Bank transactions" />
        <Empty>Sign in as a store admin to view bank transactions.</Empty>
      </PageShell>
    );
  }

  const totalPages = txns.data?.total_pages ?? 1;
  const page       = txns.data?.page        ?? 1;

  return (
    <PageShell maxWidth="80rem">

      <Breadcrumbs crumbs={[{ label: "Finance" }, { label: "Bank transactions" }]} />

      <PageHeader
        title="Bank transactions"
        subtitle={
          txns.data
            ? `${txns.data.total.toLocaleString()} txns · ` +
              `${txns.data.uncategorized_count.toLocaleString()} uncategorized`
            : "—"
        }
        actions={
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <Button
              tone="primary"
              size="sm"
              busy={syncing}
              disabled={syncing}
              onClick={async () => {
                setSyncing(true);
                setSyncMsg(null);
                try {
                  const r = await syncBankTransactions();
                  setSyncMsg(`Synced ${r.new_rows} new transaction${r.new_rows === 1 ? "" : "s"}.`);
                  void qc.invalidateQueries({ queryKey: ["bank"] });
                } catch (err) {
                  setSyncMsg(
                    err instanceof ApiError ? err.message : "Sync failed.",
                  );
                } finally {
                  setSyncing(false);
                  setTimeout(() => setSyncMsg(null), 5000);
                }
              }}
            >
              {syncing ? "Syncing…" : "Sync transactions"}
            </Button>
            <ButtonLink to="/bank" tone="secondary" size="sm">
              Manage accounts
            </ButtonLink>
          </div>
        }
      />

      {syncMsg && (
        <div style={{
          fontSize: "0.82rem",
          color: "var(--db-text-muted)",
          padding: "0.4rem 0",
        }}>
          {syncMsg}
        </div>
      )}

      {accounts.data && accounts.data.rows.length > 0 && (
        <BalanceCards accounts={accounts.data.rows} />
      )}

      <Card>
        <div className="ds-filter-bar">
          <Field label="Search">
            <Input
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
            />
          </Field>
          <Field label="Account">
            <Select
              value={filters.account_id ?? ""}
              onChange={(e) => setParam("account_id", e.target.value)}
            >
              <option value="">All accounts</option>
              {accounts.data?.rows.map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Sign">
            <Select
              value={filters.sign ?? ""}
              onChange={(e) => setParam("sign", e.target.value as "credit" | "debit" | "")}
            >
              <option value="">Any</option>
              <option value="credit">Credit</option>
              <option value="debit">Debit</option>
            </Select>
          </Field>
          <Field label="From">
            <Input
              type="date"
              value={filters.posted_from ?? ""}
              onChange={(e) => setParam("posted_from", e.target.value)}
            />
          </Field>
          <Field label="To">
            <Input
              type="date"
              value={filters.posted_to ?? ""}
              onChange={(e) => setParam("posted_to", e.target.value)}
            />
          </Field>
          <Field label="Filter">
            <label className={styles.checkboxRow}>
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
            <TxnTable rows={txns.data.rows} />
            <Pager
              page={page}
              totalPages={totalPages}
              onPage={setPage}
              leading={
                <span className={styles.pagerLead}>
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

function TxnTable({ rows }: { rows: BankTransactionRow[] }) {
  const qc = useQueryClient();
  const identity = getCurrentIdentity();
  function refresh() {
    qc.invalidateQueries({
      queryKey: ["bank", "transactions", identity?.store_id],
    });
  }
  return (
    <Table>
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
            <td style={tdStyle}>
              <span className={styles.dateCell}>
                {r.posted_at.slice(0, 10)}
              </span>
            </td>
            <td style={tdStyle}>{r.description || "—"}</td>
            <td style={tdStyle}>
              <span className={styles.accountCell}>
                {r.account_label || `acct ${r.account_id}`}
              </span>
            </td>
            <td style={tdStyle}>
              <CategoryCell row={r} onChanged={refresh} />
            </td>
            <td style={{ ...tdStyle, textAlign: "right" }}>
              <span className={r.amount_cents > 0 ? styles.amountPos : styles.amountNeutral}>
                {r.amount_cents > 0 ? "+" : ""}${r.amount.toFixed(2)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
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
    <div className={styles.categoryCell}>
      <Select
        value={row.category_slug}
        onChange={(e) => pick(e.target.value)}
        disabled={busy}
        className={
          row.category_slug
            ? `${styles.categorySelect} ${styles.categorySelectMono}`
            : styles.categorySelect
        }
      >
        <option value="">— uncategorized —</option>
        {BANK_CATEGORY_OPTIONS.map((c) => (
          <option key={c.slug} value={c.slug}>{c.label}</option>
        ))}
      </Select>
      {err && (
        <span title={err} className={styles.errorMark}>
          ⚠
        </span>
      )}
    </div>
  );
}


function BalanceCards({ accounts }: { accounts: BankAccountRow[] }) {
  const active = accounts.filter((a) => a.enabled && !a.disconnected_at);
  if (active.length === 0) return null;
  return (
    <KpiGrid minWidth="200px">
      {active.map((a) => (
        <KpiCard
          key={a.id}
          label={a.nickname || a.display_name || a.institution_name}
          value={`$${a.last_balance.toLocaleString(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
          })}`}
          sub={
            a.last_balance_as_of
              ? `As of ${formatBalanceDate(a.last_balance_as_of)}`
              : "Balance not yet refreshed."
          }
        />
      ))}
    </KpiGrid>
  );
}


function formatBalanceDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}
