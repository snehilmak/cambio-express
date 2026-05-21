import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  mergeCustomers,
  useCustomerSearch,
  type CustomerRow,
} from "../api/customers";
import { ApiError, downloadCsv } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { maskPhone } from "../lib/format";
import {
  Alert, Button, Card, Empty, EmptyState, ErrorState, Field, Input, PageHeader,
  PageShell, Section, space, Table, tdStyle, thStyle,
} from "../components/ui";
import styles from "./Customers.module.css";

// Customer search at /app/customers. Live-search box; results
// split into "exact matches" (phone/full-name match) and
// "suggestions" (fuzzy near-misses) — same shape the legacy
// /api/customers/search returns.
//
// Two interaction modes:
//   * search mode (default) — type to filter; rows are plain
//     read-only summaries.
//   * merge mode — admins / owners only. Pick exactly two rows;
//     pick a winner; confirm; the loser's transfers get re-pointed
//     and the loser row is deleted. Backed by POST
//     /api/v2/customers/{winner_id}/merge.
//
// Search query lives in the URL query string so refresh + back
// preserve state, just like the transfers list.
export default function Customers() {
  const identity = getCurrentIdentity();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";

  const [draft, setDraft] = useState(q);
  // 300ms debounce + 2-char minimum (CLAUDE.md "Table search UX").
  useEffect(() => {
    if (draft === q) return;
    const id = window.setTimeout(() => {
      const next = draft.length === 0 || draft.length >= 2 ? draft : q;
      const params = new URLSearchParams(searchParams);
      if (next) params.set("q", next);
      else params.delete("q");
      setSearchParams(params, { replace: true });
    }, 300);
    return () => window.clearTimeout(id);
  }, [draft, q, searchParams, setSearchParams]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror URL search param into local debounced input when URL changes externally (browser back, link arrival)
  useEffect(() => { setDraft(q); }, [q]);

  const { data, isFetching, isError, error, refetch } = useCustomerSearch(q);

  const [exporting, setExporting] = useState(false);

  const canExport =
    identity?.role === "admin"
    || identity?.role === "owner"
    || identity?.role === "superadmin";
  const canMerge = canExport; // same roles

  // ── Merge-mode state ────────────────────────────────────
  const [mergeMode, setMergeMode] = useState(false);
  // Index 0 = winner, index 1 = loser. Stored as the picked
  // CustomerRow so we can render side-by-side details without
  // re-querying.
  const [picks, setPicks] = useState<CustomerRow[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  function exitMergeMode() {
    setMergeMode(false);
    setPicks([]);
    setConfirmOpen(false);
    setMergeError(null);
  }

  function togglePick(row: CustomerRow) {
    setPicks((curr) => {
      const idx = curr.findIndex((p) => p.id === row.id);
      if (idx >= 0) {
        return curr.filter((p) => p.id !== row.id);
      }
      if (curr.length >= 2) return curr;
      return [...curr, row];
    });
  }

  function swapPicks() {
    setPicks((curr) =>
      curr.length === 2 ? [curr[1], curr[0]] : curr,
    );
  }

  async function onExport() {
    setExporting(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await downloadCsv(
        "/api/v2/customers/export.csv",
        `customers_${today}.csv`,
      );
    } finally {
      setExporting(false);
    }
  }

  async function onMerge() {
    if (picks.length !== 2) return;
    const [winner, loser] = picks;
    setMerging(true);
    setMergeError(null);
    try {
      const result = await mergeCustomers(winner.id, loser.id);
      setToast(
        `Merged "${loser.full_name}" into "${winner.full_name}"`
        + (result.transfers_repointed
          ? ` (${result.transfers_repointed} transfer${
              result.transfers_repointed === 1 ? "" : "s"
            } re-pointed)`
          : ""),
      );
      exitMergeMode();
      await refetch();
    } catch (e) {
      setMergeError(
        e instanceof ApiError ? e.message : "Merge failed.",
      );
    } finally {
      setMerging(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="70rem">
        <PageHeader title="Customers" />
        <Empty>Sign in as a store admin to search this store's customers.</Empty>
      </PageShell>
    );
  }

  const actions = (
    <>
      {canMerge && (
        mergeMode ? (
          <Button
            tone="secondary"
            size="sm"
            onClick={exitMergeMode}
            disabled={merging}
          >
            Cancel merge
          </Button>
        ) : (
          <Button
            tone="secondary"
            size="sm"
            onClick={() => setMergeMode(true)}
          >
            Merge duplicates
          </Button>
        )
      )}
      {canExport && (
        <Button
          tone="secondary"
          size="sm"
          busy={exporting}
          disabled={exporting}
          onClick={onExport}
        >
          {exporting ? "Exporting…" : "Export CSV"}
        </Button>
      )}
    </>
  );

  return (
    <PageShell maxWidth="70rem">
      <PageHeader
        title="Customers"
        subtitle={q.length >= 2
          ? data
            ? `${data.matches.length} match${
                data.matches.length === 1 ? "" : "es"
              } · ${data.suggestions.length} suggestion${
                data.suggestions.length === 1 ? "" : "s"
              }`
            : "Searching…"
          : "Type at least 2 characters to search."}
        actions={actions}
      />

      {toast && (
        <div style={{ marginBottom: space.lg }}>
          <Alert tone="success">
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span>{toast}</span>
              <Button
                tone="secondary"
                size="sm"
                onClick={() => setToast(null)}
              >
                Dismiss
              </Button>
            </div>
          </Alert>
        </div>
      )}

      {mergeMode && (
        <MergeBanner
          picks={picks}
          onSwap={swapPicks}
          onClear={() => setPicks([])}
          onProceed={() => setConfirmOpen(true)}
        />
      )}

      <Card style={{ marginBottom: space.lg }}>
        <Field label="Search">
          <Input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Name, phone, …"
          />
        </Field>
        {isFetching && (
          <p className={styles.searching}>Searching…</p>
        )}
      </Card>

      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Search failed"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && data.matches.length > 0 && (
        <Section title="Matches">
          <Card>
            <CustomerTable
              rows={data.matches}
              mergeMode={mergeMode}
              picks={picks}
              onTogglePick={togglePick}
            />
          </Card>
        </Section>
      )}

      {data && data.suggestions.length > 0 && (
        <Section title="Suggestions">
          <Card>
            <CustomerTable
              rows={data.suggestions}
              mergeMode={mergeMode}
              picks={picks}
              onTogglePick={togglePick}
            />
          </Card>
        </Section>
      )}

      {data &&
        data.matches.length === 0 &&
        data.suggestions.length === 0 &&
        q.length >= 2 &&
        !isFetching && (
          <EmptyState title={`No customers match "${q}".`} />
        )}

      {confirmOpen && picks.length === 2 && (
        <MergeConfirmModal
          winner={picks[0]}
          loser={picks[1]}
          busy={merging}
          error={mergeError}
          onSwap={swapPicks}
          onCancel={() => {
            setConfirmOpen(false);
            setMergeError(null);
          }}
          onConfirm={onMerge}
        />
      )}
    </PageShell>
  );
}


function MergeBanner({
  picks, onSwap, onClear, onProceed,
}: {
  picks: CustomerRow[];
  onSwap: () => void;
  onClear: () => void;
  onProceed: () => void;
}) {
  return (
    <Card style={{ marginBottom: space.lg }}>
      <div className={styles.mergeBanner}>
        <div>
          <strong>Merge mode</strong>
          <p className={styles.mergeBannerCopy}>
            Pick two customers. The first becomes the winner — its
            row stays. The second's transfers get re-pointed at the
            winner, and the row is deleted.
          </p>
          <p className={styles.mergeBannerCopy}>
            Selected: {picks.length === 0 && "none yet"}
            {picks.length === 1 && (
              <>
                <strong> {picks[0].full_name}</strong> (winner) — pick one more
              </>
            )}
            {picks.length === 2 && (
              <>
                <strong> {picks[0].full_name}</strong> (winner) ←{" "}
                <strong>{picks[1].full_name}</strong> (loser)
              </>
            )}
          </p>
        </div>
        <div className={styles.mergeBannerActions}>
          {picks.length === 2 && (
            <>
              <Button tone="secondary" size="sm" onClick={onSwap}>
                Swap winner / loser
              </Button>
              <Button tone="primary" size="sm" onClick={onProceed}>
                Review merge
              </Button>
            </>
          )}
          {picks.length > 0 && (
            <Button tone="secondary" size="sm" onClick={onClear}>
              Clear selection
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}


function MergeConfirmModal({
  winner, loser, busy, error, onSwap, onCancel, onConfirm,
}: {
  winner: CustomerRow;
  loser:  CustomerRow;
  busy:   boolean;
  error:  string | null;
  onSwap:    () => void;
  onCancel:  () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-modal-title"
      className={styles.modalBackdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <div className={styles.modalCard}>
        <h2 id="merge-modal-title" className={styles.modalTitle}>
          Merge customers
        </h2>
        <p className={styles.modalLead}>
          This will re-point every transfer logged against the loser
          to the winner, then delete the loser row. The action is
          recorded in the operator audit log and can't be undone
          from the UI.
        </p>

        <div className={styles.modalGrid}>
          <MergeColumn label="Winner (kept)" customer={winner} kept />
          <MergeColumn label="Loser (deleted)" customer={loser} kept={false} />
        </div>

        {error && (
          <Alert tone="error">{error}</Alert>
        )}

        <div className={styles.modalActions}>
          <Button tone="secondary" onClick={onSwap} disabled={busy}>
            Swap winner / loser
          </Button>
          <div style={{ flex: 1 }} />
          <Button tone="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button tone="primary" busy={busy} disabled={busy} onClick={onConfirm}>
            {busy ? "Merging…" : "Merge"}
          </Button>
        </div>
      </div>
    </div>
  );
}


function MergeColumn({
  label, customer, kept,
}: {
  label: string;
  customer: CustomerRow;
  kept: boolean;
}) {
  return (
    <div className={kept ? styles.mergeColKept : styles.mergeColDropped}>
      <p className={styles.mergeColLabel}>{label}</p>
      <p className={styles.mergeColName}>{customer.full_name}</p>
      <dl className={styles.mergeColDetails}>
        <dt>Phone</dt>
        <dd>
          {customer.phone_country} {maskPhone(customer.phone_number)}
        </dd>
        <dt>DOB</dt>
        <dd>{customer.dob || "—"}</dd>
        <dt>Address</dt>
        <dd>{customer.address || "—"}</dd>
        <dt>Home store</dt>
        <dd>{customer.home_store_name || "(this store)"}</dd>
      </dl>
    </div>
  );
}


function CustomerTable({
  rows, mergeMode, picks, onTogglePick,
}: {
  rows: CustomerRow[];
  mergeMode: boolean;
  picks: CustomerRow[];
  onTogglePick: (row: CustomerRow) => void;
}) {
  const headers = mergeMode
    ? ["Pick", "Name", "Phone", "DOB", "Address", "Home store"]
    : ["Name", "Phone", "DOB", "Address", "Home store"];
  return (
    <Table>
      <thead>
        <tr>
          {headers.map((h) => (
            <th key={h} style={thStyle}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => {
          const picked = picks.find((p) => p.id === c.id);
          const disabled = !picked && picks.length >= 2;
          return (
            <tr key={c.id} className={picked ? styles.rowPicked : undefined}>
              {mergeMode && (
                <td style={tdStyle}>
                  <input
                    type="checkbox"
                    checked={!!picked}
                    disabled={disabled}
                    onChange={() => onTogglePick(c)}
                    aria-label={`Select ${c.full_name} for merge`}
                  />
                </td>
              )}
              <td style={tdStyle}>
                <strong>{c.full_name}</strong>
                {picked && (
                  <span className={styles.pickedTag}>
                    {" "}· {picks[0]?.id === c.id ? "winner" : "loser"}
                  </span>
                )}
              </td>
              <td style={tdStyle}>
                <span
                  className={styles.phone}
                  title="Open the customer for the full number"
                >
                  {c.phone_country} {maskPhone(c.phone_number)}
                </span>
              </td>
              <td style={tdStyle}>
                <span className={styles.dob}>
                  {c.dob || "—"}
                </span>
              </td>
              <td style={tdStyle}>{c.address || "—"}</td>
              <td style={tdStyle}>
                <span className={styles.muted}>
                  {c.home_store_name || "(this store)"}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
