import { useParams } from "react-router-dom";

import { useTransfer } from "../api/transfers";
import { fmtMoney2 } from "../lib/formatters";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  ButtonLink, Card, Empty, ErrorState, Loading, PageHeader, PageShell,
  Section, tokens,
} from "../components/ui";
import styles from "./TransferDetail.module.css";

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
        <Empty>Invalid transfer ID.</Empty>
      </PageShell>
    );
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="52rem" gap="1rem">
        <Empty>Sign in as a store admin to view transfer details.</Empty>
      </PageShell>
    );
  }

  if (isLoading) {
    return (
      <PageShell maxWidth="52rem" gap="1rem">
        <Loading />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell maxWidth="52rem" gap="1rem">
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
      <Breadcrumbs crumbs={[{ label: "Transfers", to: "/transfers" }, { label: `Transfer #${id}` }]} />


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
          <DetailRow label="Send amount" value={fmtMoney2(t.send_amount)} mono />
          <DetailRow label="Fee"         value={fmtMoney2(t.fee)} mono />
          <DetailRow label="Federal tax" value={fmtMoney2(t.federal_tax)} mono />
          <DetailRow
            label="Total collected"
            value={fmtMoney2(t.total_collected)}
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
  const valueClass = emphasis
    ? styles.rowValueEmphasis
    : mono
      ? styles.rowValueMono
      : styles.rowValue;
  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}


