import { Link } from "react-router-dom";

import { useOwnerLocations } from "../api/owner";
import { useProfile } from "../api/account";
import {
  Breadcrumbs, Card, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
  Pill, SectionTitle,
} from "../components/ui";

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
        <div style={{ display: "grid", gridTemplateColumns: "8rem 1fr", gap: "0.5rem 1rem", fontSize: "0.9rem" }}>
          <span style={{ color: "var(--db-text-muted)" }}>Username</span>
          <span>{profile?.username ?? "—"}</span>
          <span style={{ color: "var(--db-text-muted)" }}>Full name</span>
          <span>{profile?.full_name || "—"}</span>
          <span style={{ color: "var(--db-text-muted)" }}>Email</span>
          <span>{profile?.email || "—"}</span>
          <span style={{ color: "var(--db-text-muted)" }}>Phone</span>
          <span>{profile?.phone || "—"}</span>
        </div>
        <div style={{ marginTop: "0.75rem" }}>
          <Link to="/settings/profile" style={{ color: "var(--db-accent)", fontSize: "0.85rem" }}>
            Edit profile →
          </Link>
        </div>
      </Card>

      <Card>
        <SectionTitle>Quick actions</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(14rem, 1fr))", gap: "0.75rem" }}>
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
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {locations.rows.map((s) => (
              <Link
                key={s.store_id}
                to={`/owner/store/${s.store_id}`}
                style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "0.5rem 0.75rem", borderRadius: "0.375rem",
                  border: "1px solid var(--db-border)", color: "var(--db-text)",
                  textDecoration: "none", transition: "border-color 150ms",
                }}
              >
                <span style={{ fontWeight: 500 }}>{s.store_name}</span>
                <Pill tone="accent">{s.transfer_count} transfers</Pill>
              </Link>
            ))}
            {storeCount === 0 && (
              <p style={{ color: "var(--db-text-muted)", fontSize: "0.85rem" }}>
                No stores linked yet. <Link to="/owner/connect" style={{ color: "var(--db-accent)" }}>Generate a connect code</Link> to get started.
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
    <Link
      to={to}
      style={{
        display: "block", padding: "0.75rem", borderRadius: "0.5rem",
        border: "1px solid var(--db-border)", textDecoration: "none",
        color: "var(--db-text)", transition: "border-color 150ms, transform 150ms",
      }}
    >
      <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{title}</div>
      <div style={{ fontSize: "0.8rem", color: "var(--db-text-muted)", marginTop: "0.15rem" }}>{desc}</div>
    </Link>
  );
}
