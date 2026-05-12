import { Link, useSearchParams } from "react-router-dom";

import { useReturnChecks, type ReturnCheckRow } from "../api/returnChecks";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, EmptyState, ErrorState, PageHeader, PageShell,
  TableSkeleton, tokens,
} from "../components/ui";

// Bounced-check workflow list at /app/return-checks. Filter by
// status pill, click any row to edit. Status transitions
// (Mark loss / Mark fraud / Reopen) live on the edit page.

const STATUSES: Array<{ slug: string; label: string }> = [
  { slug: "",          label: "All"       },
  { slug: "pending",   label: "Pending"   },
  { slug: "recovered", label: "Recovered" },
  { slug: "loss",      label: "Loss"      },
  { slug: "fraud",     label: "Fraud"     },
];

export default function ReturnChecks() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const status = sp.get("status") ?? "";
  const { data, isLoading, isError, error, refetch } = useReturnChecks(status);

  function setStatus(next: string) {
    const params = new URLSearchParams(sp);
    if (next) params.set("status", next);
    else params.delete("status");
    setSP(params, { replace: true });
  }

  if (identity?.store_id == null) {
    return (
      <PageShell>
        <PageHeader title="Return checks" />
        <Empty>Sign in as a store admin to view return checks.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Return checks"
        subtitle={data
          ? `${data.rows.length.toLocaleString()} ${
              status || "total"
            } check${data.rows.length === 1 ? "" : "s"}`
          : "—"}
        actions={(
          <ButtonLink href="/return-checks/new" tone="primary">
            + New return check
          </ButtonLink>
        )}
      />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        {STATUSES.map((s) => {
          const active = status === s.slug;
          return (
            <button
              key={s.slug}
              type="button"
              onClick={() => setStatus(s.slug)}
              style={{
                ...filterBtn,
                background: active ? tokens.accent : "transparent",
                color: active ? tokens.onAccent : tokens.text,
                borderColor: active ? tokens.accent : tokens.border,
              }}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <Card>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState
            title={`No return checks ${status ? `with status ${status}` : "yet"}.`}
          />
        )}
        {data && data.rows.length > 0 && <Table rows={data.rows} />}
      </Card>
    </PageShell>
  );
}

function Table({ rows }: { rows: ReturnCheckRow[] }) {
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
              "Bounced",
              "Customer",
              "Check #",
              "Bank",
              "Amount",
              "Recovered",
              "Status",
            ].map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: i >= 4 && i <= 5 ? "right" : "left",
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
                <Link to={`/return-checks/${r.id}/edit`} style={rowLink}>
                  <span style={monoMuted}>{r.bounced_on}</span>
                </Link>
              </td>
              <td style={cellStyle}>{r.customer_name}</td>
              <td style={cellStyle}>
                <span style={mono}>{r.check_number || "—"}</span>
              </td>
              <td style={cellStyle}>{r.payer_bank || "—"}</td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.amount.toFixed(2)}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span
                  style={{
                    ...mono,
                    color: r.recovered_total >= r.amount ? tokens.accent : tokens.text,
                  }}
                >
                  ${r.recovered_total.toFixed(2)}
                </span>
                {r.payment_count > 0 && (
                  <span
                    style={{
                      color: tokens.textMuted,
                      marginLeft: "0.4rem",
                      fontSize: "0.85rem",
                    }}
                  >
                    ({r.payment_count})
                  </span>
                )}
              </td>
              <td style={cellStyle}>
                <StatusPill status={r.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const palette: Record<string, { bg: string; fg: string }> = {
    pending:   { bg: "rgba(255,184,0,0.15)",  fg: "#ffb800" },
    recovered: { bg: "rgba(63,255,0,0.15)",   fg: "#3fff00" },
    loss:      { bg: "rgba(255,59,48,0.15)",  fg: "#ff3b30" },
    fraud:     { bg: "rgba(255,59,48,0.20)",  fg: "#ff6b60" },
  };
  const c = palette[status] ?? { bg: "transparent", fg: "#a3a3a3" };
  return (
    <span
      style={{
        display: "inline-block",
        background: c.bg,
        color: c.fg,
        borderRadius: "999px",
        padding: "0.2rem 0.6rem",
        fontSize: "0.78rem",
        fontWeight: 600,
        textTransform: "capitalize",
      }}
    >
      {status}
    </span>
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

const rowLink: React.CSSProperties = {
  color: "inherit",
  textDecoration: "none",
};

const filterBtn: React.CSSProperties = {
  border: "1px solid",
  borderRadius: "999px",
  padding: "0.4rem 0.9rem",
  fontSize: "0.85rem",
  fontFamily: tokens.fontBody,
  cursor: "pointer",
};
