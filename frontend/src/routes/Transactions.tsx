import { useState } from "react";
import { Link } from "react-router-dom";

import { useTransactions } from "../api/posimport";
import {
  Breadcrumbs, Card, Checkbox, EmptyState, ErrorState, Field, InfoTip,
  Input, KpiCard, KpiGrid, Loading, PageHeader, PageShell, Pager, Pill,
  Section, Select, Table, tdStyle, thStyle, tokens,
} from "../components/ui";
import { useUrlFilterState } from "../lib/useUrlFilterState";
import { fmtMoney2 } from "../lib/formatters";
import { formatTimestamp } from "../lib/datetime";
import styles from "./Transactions.module.css";

// /app/transactions (G-6) — every register ticket, searchable.
//
// The register has always sent this detail; until now it was rolled
// into day totals and the ticket itself was unreachable. An owner
// asking "what sold on this transaction?" or "which tickets had an
// item voided?" gets answered here.
//
// A voided ticket is FLAGGED, not hidden: the whole reason to open
// this screen is to see the void. Its money is already excluded
// server-side, so the totals below never include one.

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toLocaleDateString("en-CA");
}

const KINDS = [
  { value: "", label: "All kinds" },
  { value: "sale", label: "Sales" },
  { value: "refund", label: "Refunds" },
  { value: "void", label: "Voided tickets" },
  { value: "financial", label: "Financial" },
  { value: "other", label: "Other" },
];

export default function Transactions() {
  const [defaults] = useState(() => ({ start: daysAgo(6), end: daysAgo(0) }));
  const filters = useUrlFilterState({
    q: "", kind: "", voided: "",
    start: defaults.start, end: defaults.end,
  });
  const list = useTransactions({
    start: filters.params.start,
    end: filters.params.end,
    q: filters.params.q,
    kind: filters.params.kind,
    voidedOnly: filters.params.voided === "1",
    page: filters.page,
  });
  const data = list.data;

  return (
    <PageShell maxWidth="76rem">
      <Breadcrumbs crumbs={[{ label: "Transactions" }]} />
      <PageHeader
        title={
          <>
            Transactions
            <InfoTip text="Every ticket your register rang, with what was on it. Tickets appear as business days are booked from the register's journal files. A ticket with a voided item is flagged — the void is shown on the ticket, and never counted in any total." />
          </>
        }
        subtitle="Search a ticket, or find the ones with a void."
      />

      <div className={styles.filters}>
        <Field label="From">
          <Input
            type="date"
            value={filters.params.start}
            onChange={(e) => filters.setParam("start", e.target.value)}
          />
        </Field>
        <Field label="To">
          <Input
            type="date"
            value={filters.params.end}
            onChange={(e) => filters.setParam("end", e.target.value)}
          />
        </Field>
        <Field label="Kind">
          <Select
            value={filters.params.kind}
            onChange={(e) => filters.setParam("kind", e.target.value)}
          >
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </Select>
        </Field>
        <div className={styles.searchField}>
          <Field label="Search">
            <Input
              type="search"
              placeholder="Ticket number, cashier, or item…"
              value={filters.draft.q ?? filters.params.q}
              onChange={(e) => filters.debounced("q", e.target.value)}
            />
          </Field>
        </div>
        <div className={styles.voidedToggle}>
          <Checkbox
            checked={filters.params.voided === "1"}
            onChange={(checked) =>
              filters.setParam("voided", checked ? "1" : "")}
          >
            Voided items only
          </Checkbox>
        </div>
      </div>

      {list.isLoading && <Loading />}
      {list.isError && (
        <ErrorState
          message="Could not load transactions."
          onRetry={() => { void list.refetch(); }}
        />
      )}

      {data && (
        <>
          <KpiGrid>
            <KpiCard
              label="Tickets"
              value={data.total.toLocaleString()}
              sub={`${filters.params.start} → ${filters.params.end}`}
            />
            <KpiCard
              label="Total rung"
              value={fmtMoney2(data.total_grand)}
              tone="positive"
            />
            <KpiCard
              label="With a voided item"
              value={data.voided_count.toLocaleString()}
              tone={data.voided_count > 0 ? "warning" : "positive"}
            />
          </KpiGrid>

          {data.rows.length === 0 ? (
            <EmptyState
              title="No transactions in this range"
              body="Tickets appear as business days are booked from your register journals. Check the range, or set up the site agent under Register import."
            />
          ) : (
            <Section title="Tickets">
              <Card>
                <Table>
                  <thead>
                    <tr>
                      {["Time", "Ticket", "Register", "Cashier", "Items",
                        "Tax", "Total", ""].map((h) => (
                        <th key={h} style={thStyle}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((t) => (
                      <tr key={t.id}>
                        <td style={tdStyle}>
                          {t.receipt_at
                            ? formatTimestamp(t.receipt_at)
                            : t.business_date}
                        </td>
                        <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                          <Link to={`/transactions/${t.id}`} className="ds-link">
                            {t.transaction_no || `#${t.id}`}
                          </Link>
                        </td>
                        <td style={tdStyle}>{t.register_id || "—"}</td>
                        <td style={tdStyle}>{t.cashier_id || "—"}</td>
                        <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                          {t.item_count}
                        </td>
                        <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                          {fmtMoney2(t.tax)}
                        </td>
                        <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                          {fmtMoney2(t.grand_total)}
                        </td>
                        <td style={tdStyle}>
                          <div className={styles.flags}>
                            {t.kind && t.kind !== "sale" && (
                              <Pill tone="neutral">{t.kind}</Pill>
                            )}
                            {t.has_voided_line && (
                              <Pill tone="warning">voided item</Pill>
                            )}
                            {t.training_mode && (
                              <Pill tone="neutral">training</Pill>
                            )}
                            {t.offline && <Pill tone="warning">offline</Pill>}
                            {t.suspended && (
                              <Pill tone="warning">suspended</Pill>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                <Pager
                  page={data.page}
                  totalPages={data.total_pages}
                  onPage={(p) => filters.setPage(p)}
                />
              </Card>
            </Section>
          )}
        </>
      )}
    </PageShell>
  );
}
