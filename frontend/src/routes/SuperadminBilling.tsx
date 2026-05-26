import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs, Card, EmptyState, ErrorState, KpiCard, KpiGrid,
  Loading, PageHeader, PageShell, Pill, Section,
} from "../components/ui";
import styles from "./SuperadminBilling.module.css";

interface StoreRow {
  store_id: number;
  name: string;
  slug: string;
  plan: string;
  email: string;
  trial_ends_at?: string;
  grace_ends_at?: string;
  canceled_at?: string;
  data_retention_until?: string;
  days_left?: number;
}

interface BillingData {
  expiring_soon: StoreRow[];
  in_grace: StoreRow[];
  retention_queue: StoreRow[];
  recent_cancels: StoreRow[];
  webhook_stats: Record<string, number>;
}

function useBillingOverview() {
  const identity = getCurrentIdentity();
  return useQuery<BillingData>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "billing-overview"],
    queryFn: () => api<BillingData>("/api/v2/superadmin/billing-overview"),
  });
}

export default function SuperadminBilling() {
  const { data, isLoading, isError, error, refetch } = useBillingOverview();

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Billing" }]} />
      <PageHeader
        title="Billing Overview"
        subtitle="Trial expirations, cancellations, and retention queue"
      />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load billing data"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <KpiGrid>
            <KpiCard
              label="Expiring soon"
              value={data.expiring_soon.length}
              tone={data.expiring_soon.length > 0 ? "warning" : "neutral"}
            />
            <KpiCard
              label="In grace period"
              value={data.in_grace.length}
              tone={data.in_grace.length > 0 ? "warning" : "neutral"}
            />
            <KpiCard
              label="Retention queue"
              value={data.retention_queue.length}
              tone={data.retention_queue.length > 0 ? "negative" : "neutral"}
            />
            <KpiCard
              label="Cancels (30d)"
              value={data.recent_cancels.length}
              tone={data.recent_cancels.length > 0 ? "negative" : "positive"}
            />
          </KpiGrid>

          <div className={styles.grid}>
            <Section title="Trials expiring soon">
              <Card>
                {data.expiring_soon.length === 0 ? (
                  <EmptyState title="No trials expiring soon." />
                ) : (
                  data.expiring_soon.map((s) => (
                    <div key={s.store_id} className={styles.storeRow}>
                      <div>
                        <div className={styles.storeName}>{s.name}</div>
                        <div className={styles.storeMeta}>{s.slug} · {s.email}</div>
                      </div>
                      <div className={styles.badge}>
                        <Pill tone="warning">
                          Ends {s.trial_ends_at?.slice(0, 10)}
                        </Pill>
                      </div>
                    </div>
                  ))
                )}
              </Card>
            </Section>

            <Section title="In grace period">
              <Card>
                {data.in_grace.length === 0 ? (
                  <EmptyState title="No stores in grace period." />
                ) : (
                  data.in_grace.map((s) => (
                    <div key={s.store_id} className={styles.storeRow}>
                      <div>
                        <div className={styles.storeName}>{s.name}</div>
                        <div className={styles.storeMeta}>{s.slug}</div>
                      </div>
                      <div className={styles.badge}>
                        <Pill tone="warning">
                          Grace ends {s.grace_ends_at?.slice(0, 10)}
                        </Pill>
                      </div>
                    </div>
                  ))
                )}
              </Card>
            </Section>
          </div>

          <div className={styles.grid}>
            <Section title="Retention queue (pending purge)">
              <Card>
                {data.retention_queue.length === 0 ? (
                  <EmptyState title="No stores pending data purge." />
                ) : (
                  data.retention_queue.map((s) => (
                    <div key={s.store_id} className={styles.storeRow}>
                      <div>
                        <div className={styles.storeName}>{s.name}</div>
                        <div className={styles.storeMeta}>{s.slug}</div>
                      </div>
                      <div className={styles.badge}>
                        <Pill tone="negative">
                          {s.days_left} days left
                        </Pill>
                      </div>
                    </div>
                  ))
                )}
              </Card>
            </Section>

            <Section title="Recent cancellations (30d)">
              <Card>
                {data.recent_cancels.length === 0 ? (
                  <EmptyState title="No cancellations in the last 30 days." />
                ) : (
                  data.recent_cancels.map((s) => (
                    <div key={s.store_id} className={styles.storeRow}>
                      <div>
                        <div className={styles.storeName}>{s.name}</div>
                        <div className={styles.storeMeta}>{s.slug} · {s.plan}</div>
                      </div>
                      <span className={styles.monoMuted}>
                        {s.canceled_at?.slice(0, 10)}
                      </span>
                    </div>
                  ))
                )}
              </Card>
            </Section>
          </div>

          {Object.keys(data.webhook_stats).length > 0 && (
            <Section title="Stripe webhook health (7d)">
              <Card>
                <KpiGrid minWidth="120px">
                  {Object.entries(data.webhook_stats).map(([status, count]) => (
                    <KpiCard
                      key={status}
                      label={status}
                      value={count}
                      tone={status === "ok" ? "positive" : "negative"}
                    />
                  ))}
                </KpiGrid>
              </Card>
            </Section>
          )}
        </>
      )}
    </PageShell>
  );
}
