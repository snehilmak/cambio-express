import { Link } from "react-router-dom";

import { useOwnerLocations } from "../api/owner";
import { useProfile } from "../api/account";
import {
  Breadcrumbs, Card, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
  Pill, SectionTitle,
} from "../components/ui";
import styles from "./OwnerSettings.module.css";

export default function OwnerSettings() {
  const { data: profile } = useProfile();
  const { data: locations } = useOwnerLocations("month");

  const storeCount = locations?.rows.length ?? 0;

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[{ label: "Owner settings" }]} />
      <PageHeader
        title="Owner Settings"
        subtitle="Your umbrella profile and linked stores"
      />

      <KpiGrid>
        <KpiCard label="Linked stores" value={storeCount} />
        <KpiCard label="Account" value={profile?.full_name || profile?.username || "—"} />
        <KpiCard label="Role" value="Owner" />
      </KpiGrid>

      <Card>
        <SectionTitle>Profile</SectionTitle>
        <div className={styles.profileGrid}>
          <span className={styles.muted}>Username</span>
          <span>{profile?.username ?? "—"}</span>
          <span className={styles.muted}>Full name</span>
          <span>{profile?.full_name || "—"}</span>
          <span className={styles.muted}>Email</span>
          <span>{profile?.email || "—"}</span>
          <span className={styles.muted}>Phone</span>
          <span>{profile?.phone || "—"}</span>
        </div>
        <div className={styles.editRow}>
          <Link to="/settings/profile" className={styles.editLink}>
            Edit profile →
          </Link>
        </div>
      </Card>

      <Card>
        <SectionTitle>Quick actions</SectionTitle>
        <div className={styles.quickGrid}>
          <QuickLink to="/owner/locations" title="Locations" desc="View all linked stores" />
          <QuickLink to="/owner/connect" title="Connect stores" desc="Generate or manage invite codes" />
          <QuickLink to="/owner/users" title="Team users" desc="Users across your umbrella" />
          <QuickLink to="/owner/bulk-add-user" title="Bulk add user" desc="Create an employee at multiple stores" />
          <QuickLink to="/owner/cross-store-defaults" title="Cross-store defaults" desc="Push settings to all stores" />
          <QuickLink to="/owner/activity" title="Activity stream" desc="Recent actions across all stores" />
          <QuickLink to="/owner/bulk-permissions" title="Bulk permissions" desc="Set permissions across stores" />
          <QuickLink to="/account/notifications" title="Notifications" desc="Configure email digests" />
        </div>
      </Card>

      {locations && (
        <Card>
          <SectionTitle>Linked stores</SectionTitle>
          <div className={styles.storeList}>
            {locations.rows.map((s) => (
              <Link
                key={s.store_id}
                to={`/owner/store/${s.store_id}`}
                className={styles.storeRow}
              >
                <span className={styles.storeName}>{s.store_name}</span>
                <Pill tone="accent">{s.transfer_count} transfers</Pill>
              </Link>
            ))}
            {storeCount === 0 && (
              <p className={styles.emptyNote}>
                No stores linked yet. <Link to="/owner/connect" className={styles.emptyLink}>Generate a connect code</Link> to get started.
              </p>
            )}
          </div>
        </Card>
      )}

      {!locations && <Loading />}
    </PageShell>
  );
}

function QuickLink({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} className={styles.quickLink}>
      <div className={styles.quickTitle}>{title}</div>
      <div className={styles.quickDesc}>{desc}</div>
    </Link>
  );
}
