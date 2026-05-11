import { Link, useParams } from "react-router-dom";

import { useTransfer } from "../api/transfers";
import { getCurrentIdentity } from "../lib/auth";
import { ErrorState, Loading } from "../components/ui";

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
      <main style={pageStyle}>
        <BackLink />
        <p style={emptyStyle}>Invalid transfer ID.</p>
      </main>
    );
  }

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <BackLink />
        <p style={emptyStyle}>
          Sign in as a store admin to view transfer details.
        </p>
      </main>
    );
  }

  if (isLoading) {
    return (
      <main style={pageStyle}>
        <BackLink />
        <Loading />
      </main>
    );
  }

  if (isError) {
    return (
      <main style={pageStyle}>
        <BackLink />
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load transfer"}
          onRetry={() => { void refetch(); }}
        />
      </main>
    );
  }

  if (!data) return null;
  const t = data.transfer;

  return (
    <main style={pageStyle}>
      <BackLink />

      <header
        style={{
          marginBottom: "1.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <div>
          <h1 style={titleStyle}>Transfer #{t.id}</h1>
          <p
            style={{
              margin: "0.35rem 0 0",
              color: "var(--db-text-muted, #a3a3a3)",
              fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
            }}
          >
            {t.send_date} · {t.company} · {t.service_type}
          </p>
        </div>
        <Link
          to={`/transfers/${t.id}/edit`}
          style={{
            background: "transparent",
            color: "var(--db-text, #f5f5f5)",
            border: "1px solid var(--db-border, #262626)",
            borderRadius: "0.5rem",
            padding: "0.5rem 1rem",
            textDecoration: "none",
            fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
            fontSize: "0.9rem",
          }}
        >
          Edit
        </Link>
      </header>

      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Sender</h2>
        <DetailRow label="Name" value={t.sender_name || "—"} />
      </section>

      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Recipient</h2>
        <DetailRow label="Name" value={t.recipient_name || "—"} />
        <DetailRow label="Country" value={t.country || "—"} />
      </section>

      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Amounts</h2>
        <DetailRow label="Send amount" value={fmtCurrency(t.send_amount)} mono />
        <DetailRow label="Fee"         value={fmtCurrency(t.fee)} mono />
        <DetailRow label="Federal tax" value={fmtCurrency(t.federal_tax)} mono />
        <DetailRow
          label="Total collected"
          value={fmtCurrency(t.total_collected)}
          mono
          emphasis
        />
      </section>

      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Status & references</h2>
        <DetailRow label="Status" value={t.status} />
        <DetailRow label="Confirm #" value={t.confirm_number || "—"} mono />
        <DetailRow label="Batch ID"  value={t.batch_id || "—"} mono />
        <DetailRow label="Employee"  value={t.employee_name || "—"} />
      </section>
    </main>
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
        borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
      }}
    >
      <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>{label}</span>
      <span
        style={{
          fontFamily: mono
            ? "var(--db-font-mono, 'JetBrains Mono', monospace)"
            : undefined,
          fontWeight: emphasis ? 600 : 400,
          color: emphasis
            ? "var(--db-accent, #3fff00)"
            : "var(--db-text, #f5f5f5)",
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
        color: "var(--db-text-muted, #a3a3a3)",
        textDecoration: "none",
        fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
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

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2.5rem 1.5rem",
  maxWidth: "52rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
  gap: "1rem",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  fontWeight: 500,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--db-text-muted, #a3a3a3)",
  margin: "0 0 0.75rem",
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
