import { useNavigate, useParams } from "react-router-dom";

import { useTransaction } from "../api/posimport";
import {
  Alert, Breadcrumbs, Button, Card, ErrorState, KpiCard, KpiGrid,
  Loading, PageHeader, PageShell, Pill, Section, Table,
  tdStyle, thStyle, tokens,
} from "../components/ui";
import { fmtMoney2 } from "../lib/formatters";
import { formatTimestamp } from "../lib/datetime";
import styles from "./TransactionDetail.module.css";

// /app/transactions/:id (G-6) — one ticket, as the register rang it.
//
// Voided lines are SHOWN, struck through and flagged. That is the
// point of this page: an owner looking for what a cashier voided
// mid-sale finds it here. The ticket's own totals exclude them
// already (server-side), so the line total and the ticket total
// will not agree when there is a void — which is correct, and the
// page says so rather than leaving the reader to wonder.

export default function TransactionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const numericId = Number(id);
  const query = useTransaction(Number.isFinite(numericId) ? numericId : null);

  if (query.isLoading) {
    return (
      <PageShell>
        <PageHeader title="Transaction" />
        <Loading />
      </PageShell>
    );
  }
  if (query.isError || !query.data) {
    return (
      <PageShell>
        <PageHeader title="Transaction" />
        <ErrorState
          message="Couldn't load this transaction."
          onRetry={() => { void query.refetch(); }}
        />
      </PageShell>
    );
  }

  const t = query.data.transaction;
  const voidedLines = t.lines.filter((l) => l.status === "cancel");
  const soldTotal = t.lines
    .filter((l) => l.status !== "cancel")
    .reduce((sum, l) => sum + l.amount, 0);

  return (
    <PageShell maxWidth="60rem">
      <Breadcrumbs crumbs={[
        { label: "Transactions", to: "/transactions" },
        { label: t.transaction_no || `#${t.id}` },
      ]} />
      <PageHeader
        title={`Ticket ${t.transaction_no || `#${t.id}`}`}
        subtitle={
          t.receipt_at ? formatTimestamp(t.receipt_at) : t.business_date
        }
        actions={
          <div className={styles.flags}>
            {t.kind && t.kind !== "sale" && (
              <Pill tone="neutral">{t.kind}</Pill>
            )}
            {t.has_voided_line && <Pill tone="warning">voided item</Pill>}
            {t.training_mode && <Pill tone="neutral">training</Pill>}
            {t.offline && <Pill tone="warning">offline</Pill>}
            {t.suspended && <Pill tone="warning">suspended</Pill>}
            {t.outside && <Pill tone="neutral">pay at pump</Pill>}
          </div>
        }
      />

      {voidedLines.length > 0 && (
        <Alert tone="warning">
          {voidedLines.length === 1
            ? "One item was voided on this ticket."
            : `${voidedLines.length} items were voided on this ticket.`}
          {" "}They are listed below for reference and are not included
          in any total.
        </Alert>
      )}

      <KpiGrid>
        <KpiCard label="Items" value={fmtMoney2(soldTotal)} />
        <KpiCard label="Tax" value={fmtMoney2(t.tax)} />
        <KpiCard
          label="Total"
          value={fmtMoney2(t.grand_total)}
          tone="positive"
        />
      </KpiGrid>

      <Section title="Items">
        <Card>
          <Table>
            <thead>
              <tr>
                {["#", "Item", "Scan code", "Qty", "Price", "Amount", ""]
                  .map((h) => <th key={h} style={thStyle}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {t.lines.map((line) => {
                const cancelled = line.status === "cancel";
                return (
                  <tr
                    key={`${line.line_seq}-${line.pos_code}`}
                    className={cancelled ? styles.cancelledRow : ""}
                  >
                    <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                      {line.line_seq}
                    </td>
                    <td style={tdStyle}>
                      {line.description || "—"}
                      {line.is_fuel && line.fuel_position && (
                        <span className={styles.sub}>
                          {" "}pump {line.fuel_position}
                        </span>
                      )}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                      {line.pos_code || "—"}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                      {line.is_fuel && line.gallons
                        ? `${line.gallons.toFixed(3)} gal`
                        : line.quantity.toLocaleString()}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                      {line.actual_price
                        ? fmtMoney2(line.actual_price) : "—"}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                      {fmtMoney2(line.amount)}
                    </td>
                    <td style={tdStyle}>
                      {cancelled && <Pill tone="warning">voided</Pill>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Card>
      </Section>

      {t.tenders.length > 0 && (
        <Section title="Payment">
          <Card>
            <Table>
              <thead>
                <tr>
                  {["Tender", "Type", "Amount"].map((h) => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {t.tenders.map((tender, i) => (
                  <tr key={`${tender.code}-${i}`}>
                    <td style={tdStyle}>
                      {tender.code || "—"}
                      {tender.is_change && (
                        <span className={styles.sub}> (change)</span>
                      )}
                    </td>
                    <td style={tdStyle}>{tender.sub_code || "—"}</td>
                    <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                      {fmtMoney2(tender.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </Section>
      )}

      {/* Register provenance. Useful when reconciling against a
          paper Z-report or chasing a specific till. */}
      <Section title="Register">
        <Card>
          <dl className={styles.meta}>
            <MetaRow label="Business date" value={t.business_date} />
            <MetaRow label="Register" value={t.register_id || "—"} />
            <MetaRow label="Cashier" value={t.cashier_id || "—"} />
            <MetaRow label="Till" value={t.till_id || "—"} />
            <MetaRow
              label="Started"
              value={t.started_at ? formatTimestamp(t.started_at) : "—"}
            />
            <MetaRow
              label="Ended"
              value={t.ended_at ? formatTimestamp(t.ended_at) : "—"}
            />
            <MetaRow label="Journal file" value={t.source_file || "—"} mono />
          </dl>
        </Card>
      </Section>

      <div className={styles.footerRow}>
        <Button tone="secondary" onClick={() => navigate("/transactions")}>
          Back to transactions
        </Button>
      </div>
    </PageShell>
  );
}

function MetaRow({
  label, value, mono = false,
}: { label: string; value: string; mono?: boolean }) {
  return (
    <div className={styles.metaRow}>
      <dt className={styles.metaLabel}>{label}</dt>
      <dd
        className={styles.metaValue}
        style={mono ? { fontFamily: tokens.fontMono } : undefined}
      >
        {value}
      </dd>
    </div>
  );
}
