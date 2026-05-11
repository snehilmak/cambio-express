import { Link, useParams } from "react-router-dom";

import { useTransfer } from "../api/transfers";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, ErrorState, Loading, PageHeader, PageShell,
  Section, tokens,
} from "../components/ui";

// Single-transfer detail page. Backed by /api/v2/transfers/{id}
// — same shape as a row in the list, so the read-only detail
// view here is mostly a labeled flat layout. The legacy
// /transfers/<id>/edit Jinja page handles edits today;
// editing migrates in SPA-N (write-side).
export default function TransferDetail() {
  const params = useParams<{ id: string }>();
  const id = params.id ? Number(params.id) : undefined;
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useTransfer(id);

  if (Number.isNaN(id)) {
    return (
      <PageShell maxWidth="52rem" gap="1rem">
        <BackLink />
        <Empty>Invalid transfer ID.</Empty>
      </PageShell>
    );
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="52rem" gap="1rem">
        <BackLink />
        <Empty>Sign in as a store admin to view transfer details.</Empty>
      </PageShell>
    );
  }

  if (isLoading) {
    return (
      <PageShell maxWidth="52rem" gap="1rem">
        <BackLink />
        <Loading />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell maxWidth="52rem" gap="1rem">
        <BackLink />
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load transfer"}
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  if (!data) return null;
  const t = data.transfer;

  return (
    <PageShell maxWidth="52rem" gap="1rem">
      <BackLink />

      <PageHeader
        title={`Transfer #${t.id}`}
        subtitle={(
          <span style={{ fontFamily: tokens.fontMono }}>
            {t.send_date} · {t.company} · {t.service_type}
          </span>
        )}
        actions={(
          <ButtonLink href={`/transfers/${t.id}/edit`} tone="secondary" size="sm">
            Edit
          </ButtonLink>
        )}
      />

      <Section title="Sender">
        <Card padding="1.25rem 1.5rem">
          <DetailRow label="Name" value={t.sender_name || "—"} />
        </Card>
      </Section>

      <Section title="Recipient">
        <Card padding="1.25rem 1.5rem">
          <DetailRow label="Name" value={t.recipient_name || "—"} />
          <DetailRow label="Country" value={t.country || "—"} />
        </Card>
      </Section>

      <Section title="Amounts">
        <Card padding="1.25rem 1.5rem">
          <DetailRow label="Send amount" value={fmtCurrency(t.send_amount)} mono />
          <DetailRow label="Fee"         value={fmtCurrency(t.fee)} mono />
          <DetailRow label="Federal tax" value={fmtCurrency(t.federal_tax)} mono />
          <DetailRow
            label="Total collected"
            value={fmtCurrency(t.total_collected)}
            mono
            emphasis
          />
        </Card>
      </Section>

      <Section title="Status & references">
        <Card padding="1.25rem 1.5rem">
          <DetailRow label="Status" value={t.status} />
          <DetailRow label="Confirm #" value={t.confirm_number || "—"} mono />
          <DetailRow label="Batch ID"  value={t.batch_id || "—"} mono />
          <DetailRow label="Employee"  value={t.employee_name || "—"} />
        </Card>
      </Section>
    </PageShell>
  );
}

function DetailRow({
  label, value, mono, emphasis,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  emphasis?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: "1rem",
        padding: "0.6rem 0",
        borderBottom: `1px solid ${tokens.borderSubtle}`,
      }}
    >
      <span style={{ color: tokens.textMuted }}>{label}</span>
      <span
        style={{
          fontFamily: mono ? tokens.fontMono : undefined,
          fontWeight: emphasis ? 600 : 400,
          color: emphasis ? tokens.accent : tokens.text,
        }}
      >
        {value}
      </span>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to="/transfers"
      style={{
        display: "inline-block",
        marginBottom: "1rem",
        color: tokens.textMuted,
        textDecoration: "none",
        fontFamily: tokens.fontMono,
        fontSize: "0.9rem",
      }}
    >
      ← All transfers
    </Link>
  );
}

function fmtCurrency(n: number): string {
  return `$${n.toFixed(2)}`;
}
