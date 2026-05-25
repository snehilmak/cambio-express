import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useOwnerLocations,
  type OwnerPeriod,
  type OwnerStoreRow,
} from "../api/owner";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Card, Empty, EmptyState, ErrorState, Input, PageHeader, PageShell,
  Table, TableSkeleton, tdStyle, thStyle,
} from "../components/ui";
import styles from "./OwnerLocations.module.css";

// Owner umbrella: per-store stats grid at /app/owner/locations.
// Period selector (today/month/year) drives the date window for
// transfers, volume, over/short. Free-text search filters by
// store name (case-insensitive).
//
// Subsequent PRs add /app/owner (dashboard with KPI cards),
// /app/owner/pl-rollup, and the connect/unlink flow.

const PERIODS: Array<{ slug: OwnerPeriod; label: string }> = [
  { slug: "today", label: "Today"      },
  { slug: "month", label: "This month" },
  { slug: "year",  label: "This year"  },
];

export default function OwnerLocations() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const period = (sp.get("period") as OwnerPeriod) ?? "month";
  const q      = sp.get("q") ?? "";
  const [qDraft, setQDraft] = useState(q);

  const { data, isLoading, isError, error, refetch } = useOwnerLocations(period, q);

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else       next.delete(key);
    setSP(next, { replace: true });
  }

  const isOwner =
    identity?.role === "owner" || identity?.role === "superadmin";
  if (!isOwner) {
    return (
      <PageShell maxWidth="70rem">
        <PageHeader title="Owner locations" />
        <Empty>Sign in as an owner to view the multi-store umbrella.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="70rem">

      <Breadcrumbs crumbs={[{ label: "Locations" }]} />

      <PageHeader
        title="Locations"
        subtitle={data
          ? `${data.matched.toLocaleString()} of ${data.total.toLocaleString()} stores`
          : "—"}
      />

      <div className={styles.toolbar}>
        <div className={styles.periodGroup}>
          {PERIODS.map((p) => (
            <button
              key={p.slug}
              type="button"
              onClick={() => setParam("period", p.slug)}
              className={period === p.slug ? styles.periodBtnActive : styles.periodBtn}
            >
              {p.label}
            </button>
          ))}
        </div>
        <Input
          type="search"
          value={qDraft}
          placeholder="Search stores…"
          onChange={(e) => setQDraft(e.target.value)}
          onBlur={() => setParam("q", qDraft.trim())}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              setParam("q", qDraft.trim());
            }
          }}
          style={{ maxWidth: "20rem" }}
        />
      </div>

      <Card>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.matched === 0 && !isLoading && data.total === 0 && (
          <EmptyState
            title="No stores connected yet"
            body="Ask each store admin to redeem an owner-connect code."
          />
        )}
        {data && data.matched === 0 && !isLoading && data.total > 0 && (
          <EmptyState title={`No stores match "${q}".`} />
        )}
        {data && data.matched > 0 && <StoreTable rows={data.rows} />}
      </Card>
    </PageShell>
  );
}

function StoreTable({ rows }: { rows: OwnerStoreRow[] }) {
  return (
    <Table>
      <thead>
        <tr>
          {[
            ["Store",      "left"],
            ["Transfers",  "right"],
            ["Volume",     "right"],
            ["Over/Short", "right"],
            ["Companies",  "left"],
          ].map(([label, align], i) => (
            <th
              key={i}
              style={{ ...thStyle, textAlign: align as "left" | "right" }}
            >
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.store_id}>
            <td style={tdStyle}>
              <div className={styles.storeName}>{r.store_name}</div>
              <div className={styles.storeSlug}>{r.store_slug}</div>
            </td>
            <td style={{ ...tdStyle, textAlign: "right" }}>
              <span className={styles.mono}>{r.transfer_count.toLocaleString()}</span>
            </td>
            <td style={{ ...tdStyle, textAlign: "right" }}>
              <span className={styles.mono}>${r.volume.toFixed(2)}</span>
            </td>
            <td style={{ ...tdStyle, textAlign: "right" }}>
              <span
                className={
                  r.over_short < 0
                    ? styles.overShortNeg
                    : r.over_short > 0
                      ? styles.overShortPos
                      : styles.overShortZero
                }
              >
                {r.over_short >= 0 ? "+" : ""}${r.over_short.toFixed(2)}
              </span>
            </td>
            <td style={tdStyle}>
              <div className={styles.companyChips}>
                {r.companies.length === 0 ? (
                  <span className={styles.dash}>—</span>
                ) : (
                  r.companies.slice(0, 5).map((c) => (
                    <span key={c.company} className={styles.chip}>
                      {c.company} · {c.count}
                    </span>
                  ))
                )}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
