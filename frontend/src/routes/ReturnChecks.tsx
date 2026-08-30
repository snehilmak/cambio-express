import { useNavigate, useSearchParams } from "react-router-dom";

import { useReturnChecks, type ReturnCheckRow } from "../api/returnChecks";
import { getCurrentIdentity } from "../lib/auth";
import { fmtMoney2 } from "../lib/formatters";
import {
  ButtonLink, Card, Empty, PageHeader,
  PageShell, Pill, Table as KitTable, TableStates, tdStyle,
  thStyle, type PillTone,
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
        <PageHeader title="Returned checks" />
        <Empty>Sign in as a store admin to view return checks.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell>

      <PageHeader
        title="Returned checks"
        subtitle={data
          ? `${data.rows.length.toLocaleString()} ${
              status || "total"
            } check${data.rows.length === 1 ? "" : "s"}`
          : "—"}
        actions={(
          <ButtonLink href="/return-checks/new" tone="primary" size="sm">
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
        <div style={{ overflowX: "auto" }}>
        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!data || data.rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle={`No return checks ${status ? `with status ${status}` : "yet"}.`}
        />
        {data && data.rows.length > 0 && <Table rows={data.rows} />}
        </div>
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
            // is the discoverable, keyboard-reachable affordance;
            // this just makes the rest of the row not feel inert.
            // Hover is a CSS class (honors prefers-reduced-motion)
            // rather than JS style mutation.
            const open = () => navigate(`/return-checks/${r.id}/edit`);
            return (
              <tr
                key={r.id}
                className={styles.row}
                onClick={open}
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
                  <span className={styles.mono}>{fmtMoney2(r.amount)}</span>
                </td>
                <td style={{ ...tdStyle, textAlign: "right" }}>
                  <span className={r.recovered_total >= r.amount + r.return_check_fee ? styles.recoveredFull : styles.mono}>
                    {fmtMoney2(r.recovered_total)}
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
                  <ButtonLink
                    to={`/return-checks/${r.id}/edit`}
                    tone="secondary"
                    size="sm"
                  >
                    Edit / Record payment
                  </ButtonLink>
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

