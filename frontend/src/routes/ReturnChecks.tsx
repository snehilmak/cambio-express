import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useReturnChecks, type ReturnCheckRow } from "../api/returnChecks";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Button, ButtonLink, Card, Empty, PageHeader,
  PageShell, Pill, Table as KitTable, TableStates, tdStyle,
  thStyle, tokens, type PillTone,
} from "../components/ui";
import styles from "./ReturnChecks.module.css";

// Bounced-check workflow list at /app/return-checks. Filter by
// status pill, click any row (or the explicit Edit button) to
// open the edit page where you can update fields, record partial
// payments, or transition the status (Mark loss / Mark fraud /
// Reopen).

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

      <Breadcrumbs crumbs={[{ label: "Return checks" }]} />

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

      <div className={styles.filters}>
        {STATUSES.map((s) => {
          const active = status === s.slug;
          return (
            <button
              key={s.slug}
              type="button"
              onClick={() => setStatus(s.slug)}
              className={active ? styles.filterBtnActive : styles.filterBtn}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <Card>
        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!data || data.rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle={`No return checks ${status ? `with status ${status}` : "yet"}.`}
        />
        {data && data.rows.length > 0 && <Table rows={data.rows} />}
      </Card>
    </PageShell>
  );
}

function Table({ rows }: { rows: ReturnCheckRow[] }) {
  const navigate = useNavigate();
  return (
    <KitTable>
        <thead>
          <tr>
            <th style={thStyle}>Bounced</th>
            <th style={thStyle}>Customer</th>
            <th style={thStyle}>Check #</th>
            <th style={thStyle}>Bank</th>
            <th style={{ ...thStyle, textAlign: "right" }}>Amount</th>
            <th style={{ ...thStyle, textAlign: "right" }}>Recovered</th>
            <th style={thStyle}>Status</th>
            <th style={{ ...thStyle, textAlign: "right" }}></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            // Whole-row click navigates to edit so a cashier can
            // tap any cell. The explicit Edit button on the right
            // is the discoverable affordance; this just makes the
            // rest of the row not feel inert.
            const open = () => navigate(`/return-checks/${r.id}/edit`);
            return (
              <tr
                key={r.id}
                style={{
                  transition: "background 120ms ease",
                  cursor: "pointer",
                }}
                onClick={open}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = tokens.surface;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <td style={tdStyle}>
                  <span className={styles.monoMuted}>{r.bounced_on}</span>
                </td>
                <td style={tdStyle}>{r.customer_name}</td>
                <td style={tdStyle}>
                  <span className={styles.mono}>{r.check_number || "—"}</span>
                </td>
                <td style={tdStyle}>{r.payer_bank || "—"}</td>
                <td style={{ ...tdStyle, textAlign: "right" }}>
                  <span className={styles.mono}>${r.amount.toFixed(2)}</span>
                </td>
                <td style={{ ...tdStyle, textAlign: "right" }}>
                  <span className={r.recovered_total >= r.amount ? styles.recoveredFull : styles.mono}>
                    ${r.recovered_total.toFixed(2)}
                  </span>
                  {r.payment_count > 0 && (
                    <span className={styles.paymentCount}>
                      ({r.payment_count})
                    </span>
                  )}
                </td>
                <td style={tdStyle}>
                  <StatusPill status={r.status} />
                </td>
                <td
                  style={{ ...tdStyle, textAlign: "right" }}
                  // Stop the row-click from firing when the user
                  // taps the explicit button — otherwise we
                  // navigate twice and React-Router warns.
                  onClick={(e) => e.stopPropagation()}
                >
                  <Link
                    to={`/return-checks/${r.id}/edit`}
                    style={{ textDecoration: "none" }}
                  >
                    <Button tone="secondary" size="sm">
                      Edit / Record payment
                    </Button>
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
    </KitTable>
  );
}

function StatusPill({ status }: { status: string }) {
  // Maps return-check status → shared Pill tone so the badge
  // palette stays in lock-step with every other tone surface in
  // the SPA (Alert / ErrorState / audit-log badges / plan pills).
  const toneByStatus: Record<string, PillTone> = {
    pending:   "warning",
    recovered: "success",
    loss:      "negative",
    fraud:     "negative",
  };
  const tone: PillTone = toneByStatus[status] ?? "neutral";
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return <Pill tone={tone}>{label}</Pill>;
}

