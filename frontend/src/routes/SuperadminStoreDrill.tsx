import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs, ButtonLink, Card, EmptyState, ErrorState,
  KpiCard, KpiGrid, Loading, PageHeader, PageShell, Pill,
  Section, Table, tdStyle, thStyle,
} from "../components/ui";
import styles from "./SuperadminStoreDrill.module.css";

interface StoreInfo {
  id: number; name: string; slug: string; email: string;
  phone: string; address: string; plan: string;
  billing_cycle: string; is_active: boolean;
  trial_status: string; created_at: string;
  trial_ends_at: string; canceled_at: string;
  stripe_customer_id: string;
}

interface TeamMember {
  id: number; username: string; full_name: string;
  role: string; email: string; is_active: boolean;
  has_2fa: boolean; last_login_at: string;
}

interface TransferRow {
  id: number; send_date: string; sender_name: string;
  recipient_name: string; company: string;
  send_amount: number; fee: number; total_collected: number;
  status: string; created_at: string;
}

interface DrillData {
  store: StoreInfo;
  team: TeamMember[];
  roster: Array<{ id: number; name: string; is_active: boolean }>;
  recent_transfers: TransferRow[];
  stats_30d: { transfer_count: number; volume: number; fees: number };
}

function useStoreDrill(storeId: number | undefined) {
  const identity = getCurrentIdentity();
  return useQuery<DrillData>({
    enabled: identity?.role === "superadmin" && storeId != null,
    queryKey: ["superadmin", "store-drill", storeId],
    queryFn: () => api<DrillData>(`/api/v2/superadmin/stores/${storeId}/drill`),
  });
}

function fmtMoney(n: number): string {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function SuperadminStoreDrill() {
  const params = useParams<{ id: string }>();
  const storeId = params.id ? Number(params.id) : undefined;
  const { data, isLoading, isError, error, refetch } = useStoreDrill(storeId);

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[
        { label: "Stores", to: "/superadmin/stores" },
        { label: data?.store.name || `Store #${storeId}` },
      ]} />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load store"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <PageHeader
            title={data.store.name}
            subtitle={data.store.slug}
            actions={(
              <div className={styles.actions}>
                <ButtonLink
                  href={`/superadmin/stores/${data.store.id}/edit`}
                  tone="secondary" size="sm"
                >
                  Edit store
                </ButtonLink>
              </div>
            )}
          />

          <KpiGrid>
            <KpiCard label="Plan" value={data.store.plan} tone={
              data.store.plan === "pro" ? "neon"
              : data.store.plan === "basic" ? "positive"
              : data.store.plan === "trial" ? "warning"
              : "negative"
            } />
            <KpiCard label="Status" value={data.store.is_active ? "Active" : "Disabled"} tone={data.store.is_active ? "positive" : "negative"} />
            <KpiCard label="Transfers (30d)" value={data.stats_30d.transfer_count.toLocaleString()} />
            <KpiCard label="Volume (30d)" value={fmtMoney(data.stats_30d.volume)} tone="positive" />
            <KpiCard label="Fees (30d)" value={fmtMoney(data.stats_30d.fees)} />
            <KpiCard label="Team" value={data.team.length} />
          </KpiGrid>

          <div className={styles.grid}>
            <Section title="Store info">
              <Card>
                <InfoRow label="Email" value={data.store.email || "—"} />
                <InfoRow label="Phone" value={data.store.phone || "—"} />
                <InfoRow label="Address" value={data.store.address || "—"} />
                <InfoRow label="Billing cycle" value={data.store.billing_cycle || "—"} />
                <InfoRow label="Trial status" value={data.store.trial_status} />
                <InfoRow label="Created" value={data.store.created_at.slice(0, 10)} />
                {data.store.trial_ends_at && (
                  <InfoRow label="Trial ends" value={data.store.trial_ends_at.slice(0, 10)} />
                )}
                {data.store.canceled_at && (
                  <InfoRow label="Canceled" value={data.store.canceled_at.slice(0, 10)} />
                )}
                {data.store.stripe_customer_id && (
                  <InfoRow label="Stripe customer" value={data.store.stripe_customer_id} />
                )}
              </Card>
            </Section>

            <Section title={`Team (${data.team.length})`}>
              <Card>
                {data.team.length === 0 ? (
                  <EmptyState title="No team members." />
                ) : (
                  data.team.map((u) => (
                    <div key={u.id} className={styles.teamRow}>
                      <div>
                        <div className={styles.teamName}>{u.full_name || u.username}</div>
                        <div className={styles.teamMeta}>
                          {u.username} · {u.email || "no email"}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
                        <Pill tone={
                          u.role === "admin" ? "accent"
                          : u.role === "owner" ? "info"
                          : "neutral"
                        }>{u.role}</Pill>
                        {!u.is_active && <Pill tone="negative">disabled</Pill>}
                      </div>
                    </div>
                  ))
                )}
              </Card>
            </Section>
          </div>

          {data.roster.length > 0 && (
            <Section title={`Employee roster (${data.roster.length})`}>
              <Card>
                <KpiGrid minWidth="120px">
                  {data.roster.map((e) => (
                    <KpiCard
                      key={e.id}
                      label={e.is_active ? "Active" : "Inactive"}
                      value={e.name}
                      tone={e.is_active ? "neutral" : "muted"}
                    />
                  ))}
                </KpiGrid>
              </Card>
            </Section>
          )}

          <Section title={`Recent transfers (${data.recent_transfers.length})`}>
            <Card>
              {data.recent_transfers.length === 0 ? (
                <EmptyState title="No transfers yet." />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <th style={thStyle}>Date</th>
                      <th style={thStyle}>Sender</th>
                      <th style={thStyle}>Recipient</th>
                      <th style={thStyle}>Company</th>
                      <th style={{ ...thStyle, textAlign: "right" }}>Amount</th>
                      <th style={thStyle}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_transfers.map((t) => (
                      <tr key={t.id}>
                        <td style={tdStyle}>
                          <span className={styles.monoMuted}>{t.send_date}</span>
                        </td>
                        <td style={tdStyle}>{t.sender_name || "—"}</td>
                        <td style={tdStyle}>{t.recipient_name || "—"}</td>
                        <td style={tdStyle}>{t.company || "—"}</td>
                        <td style={{ ...tdStyle, textAlign: "right" }}>
                          <span className={styles.mono}>{fmtMoney(t.send_amount)}</span>
                        </td>
                        <td style={tdStyle}>
                          <Pill tone={t.status === "Completed" ? "success" : t.status === "Canceled" ? "negative" : "neutral"}>
                            {t.status}
                          </Pill>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>
          </Section>
        </>
      )}
    </PageShell>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.infoRow}>
      <span className={styles.infoLabel}>{label}</span>
      <span className={styles.infoValue}>{value}</span>
    </div>
  );
}
