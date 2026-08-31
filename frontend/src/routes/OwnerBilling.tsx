import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useOwnerBilling, type OwnerBillingRow } from "../api/owner";
import { switchStore } from "../api/switchStore";
import {
  Breadcrumbs, Button, Card, Empty, KpiCard, KpiGrid, monoStyle,
  PageHeader, PageShell, Pill, Section, Table, TableStates, tdStyle,
  thStyle, useToast, type PillTone,
} from "../components/ui";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { fmtMoney2 } from "../lib/formatters";
import styles from "./OwnerBilling.module.css";

// /app/owner/billing — every store's subscription state in one
// place (B-1).
//
// Subscriptions are per-store, which is fine for Stripe but left a
// multi-store owner with no way to answer "what am I paying in
// total, and is anything about to lapse?" without switching into
// each store in turn. This page answers both, and the per-row
// action does that switch for them: hop into the store and land on
// its subscription page, where its Stripe customer actually lives.

// Attention slugs from the API, mapped to wording + a pill tone.
// Tones follow UI-STANDARDS section 3: negative = failed/urgent,
// warning = pending action, neutral = nothing to do.
const ATTENTION: Record<string, { label: string; tone: PillTone }> = {
  retention:     { label: "Purging soon",  tone: "negative" },
  trial_expired: { label: "Trial expired", tone: "negative" },
  inactive:      { label: "Inactive",      tone: "negative" },
  trial_ending:  { label: "Trial ending",  tone: "warning" },
};

function statusFor(row: OwnerBillingRow): { label: string; tone: PillTone } {
  const flagged = ATTENTION[row.attention];
  if (flagged) return flagged;
  if (row.has_paid_plan) return { label: "Active", tone: "accent" };
  if (row.plan === "trial") return { label: "Trial", tone: "info" };
  return { label: "Inactive", tone: "neutral" };
}

/** The detail line under a store's status — why it needs attention,
 *  or when its trial runs out. Empty for a healthy paid store. */
function detailFor(row: OwnerBillingRow): string {
  if (row.retention_days_left != null) {
    return row.retention_days_left === 0
      ? "Data purges today"
      : `Data purges in ${row.retention_days_left} days`;
  }
  if (row.plan === "trial" && row.trial_days_left != null) {
    return row.trial_days_left === 0
      ? "Trial ends today"
      : `${row.trial_days_left} days left`;
  }
  if (row.plan === "inactive") return "No active subscription";
  return "";
}

export default function OwnerBilling() {
  const identity = getCurrentIdentity();
  const navigate = useNavigate();
  const toast = useToast();
  const [busyId, setBusyId] = useState<number | null>(null);
  const { data, isLoading, isError, error, refetch } = useOwnerBilling();

  const isOwner =
    identity?.role === "owner" || identity?.role === "superadmin";
  // Superadmin can READ the rollup (support / debug), but
  // /auth/switch-store is owner-only by design — offering them a
  // button that can only 403 is worse than not offering it. They
  // reach a store through the superadmin store drill-down instead.
  const canSwitch = identity?.role === "owner";

  async function manageStore(row: OwnerBillingRow) {
    setBusyId(row.store_id);
    try {
      await switchStore(row.store_id);
      // Land on the page that can actually act: a store with no
      // paid plan needs the plan picker, one with a plan needs the
      // Stripe portal on its subscription page.
      navigate(row.has_paid_plan ? "/admin/subscription" : "/subscribe");
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message
          : "Could not open that store's billing.",
        tone: "error",
      });
      setBusyId(null);
    }
  }

  if (!isOwner) {
    return (
      <PageShell>
        <PageHeader title="Billing" />
        <Empty>Sign in as an owner to view billing across stores.</Empty>
      </PageShell>
    );
  }

  const totals = data?.totals;
  const rows = data?.rows ?? [];

  return (
    <PageShell>
      <Breadcrumbs crumbs={[{ label: "Owner" }, { label: "Billing" }]} />
      <PageHeader
        title="Billing"
        subtitle="Subscription state for every store in your umbrella."
      />

      {totals && (
        <KpiGrid>
          <KpiCard
            label="Monthly total"
            value={fmtMoney2(totals.monthly_cost + totals.addon_monthly_cost)}
            sub={
              totals.addon_monthly_cost > 0
                ? `${fmtMoney2(totals.monthly_cost)} plans + ` +
                  `${fmtMoney2(totals.addon_monthly_cost)} add-ons`
                : "Yearly plans shown per month"
            }
          />
          <KpiCard
            label="Paid stores"
            value={String(totals.paid_stores)}
            sub={`of ${totals.stores} total`}
          />
          <KpiCard
            label="On trial"
            value={String(totals.trial_stores)}
          />
          <KpiCard
            label="Needs attention"
            value={String(totals.attention_count)}
            tone={totals.attention_count > 0 ? "negative" : "neutral"}
          />
        </KpiGrid>
      )}

      <Card>
        <Section title="Stores">
          <TableStates
            isLoading={isLoading} isError={isError} error={error}
            isEmpty={rows.length === 0}
            onRetry={() => { void refetch(); }}
            emptyTitle="No stores connected"
            emptyBody="Connect a store to see its subscription here."
          />
          {rows.length > 0 && (
            <div className={styles.tableWrap}>
              <Table>
                <thead>
                  <tr>
                    <th style={thStyle}>Store</th>
                    <th style={thStyle}>Status</th>
                    <th style={thStyle}>Plan</th>
                    <th style={{ ...thStyle, textAlign: "right" }}>
                      Per month
                    </th>
                    <th style={thStyle}>Add-ons</th>
                    <th style={thStyle} />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const status = statusFor(r);
                    const detail = detailFor(r);
                    return (
                      <tr key={r.store_id}>
                        <td style={tdStyle}>{r.store_name}</td>
                        <td style={tdStyle}>
                          <Pill tone={status.tone}>{status.label}</Pill>
                          {detail && (
                            <div className={styles.detail}>{detail}</div>
                          )}
                        </td>
                        <td style={tdStyle}>
                          {r.plan_label}
                          {r.plan_price_label && (
                            <div className={styles.detail}>
                              {r.plan_price_label}
                            </div>
                          )}
                        </td>
                        <td style={{ ...tdStyle, ...monoStyle, textAlign: "right" }}>
                          {r.monthly_cost > 0 ? fmtMoney2(r.monthly_cost) : "—"}
                        </td>
                        <td style={tdStyle}>
                          {r.addon_count > 0
                            ? `${r.addon_count} · ${fmtMoney2(r.addon_monthly_cost)}`
                            : "—"}
                        </td>
                        <td style={tdStyle}>
                          {canSwitch && (
                            <Button
                              tone="secondary" size="sm"
                              busy={busyId === r.store_id}
                              disabled={busyId != null}
                              onClick={() => { void manageStore(r); }}
                            >
                              {busyId === r.store_id
                                ? "Opening…"
                                : r.has_paid_plan ? "Manage" : "Subscribe"}
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </div>
          )}
        </Section>
        <p className={styles.footnote}>
          Each store is billed on its own subscription, so managing
          one takes you into that store. Yearly plans are shown as
          their monthly equivalent so the totals add up.
        </p>
      </Card>
    </PageShell>
  );
}
