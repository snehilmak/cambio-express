import { useState } from "react";

import { useItemMovement } from "../api/posimport";
import {
  Breadcrumbs, Card, EmptyState, ErrorState, Field, InfoTip, Input,
  KpiCard, KpiGrid, Loading, PageHeader, PageShell, Pager, Pill,
  Section, Table, tdStyle, thStyle, tokens,
} from "../components/ui";
import { useUrlFilterState } from "../lib/useUrlFilterState";
import { fmtMoney2 } from "../lib/formatters";

// /app/store-reports/item-movement (G-2) — per-item quantity +
// dollars over a date range from the booked Gilbarco journal
// data. Top sellers first. Populates as business days book
// (automatically once the site agent + mapping are in place).

function _daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function ItemMovement() {
  const [defaults] = useState(() => ({
    start: _daysAgo(6), end: _daysAgo(0),
  }));
  const filters = useUrlFilterState({
    q: "", start: defaults.start, end: defaults.end,
  });
  const movement = useItemMovement({
    start: filters.params.start,
    end: filters.params.end,
    q: filters.params.q,
    page: filters.page,
  });
  const data = movement.data;

  return (
    <PageShell maxWidth="72rem">
      <Breadcrumbs crumbs={[
        { label: "Store Reports", to: "/store-reports" },
        { label: "Item Movement" },
      ]} />
      <PageHeader
        title={
          <>
            Item movement
            <InfoTip text="What actually sold, item by item, from your register's journal data. Rows appear as business days are booked — automatic once the site agent is pushing and your merchandise codes are mapped." />
          </>
        }
        subtitle="Per-item quantity and dollars — top sellers first."
      />

      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
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
        <div style={{ flex: 1, minWidth: "14rem" }}>
          <Field label="Search">
            <Input
              type="search"
              placeholder="Description or scan code…"
              value={filters.draft.q ?? filters.params.q}
              onChange={(e) => filters.debounced("q", e.target.value)}
            />
          </Field>
        </div>
      </div>

      {movement.isLoading && <Loading />}
      {movement.isError && (
        <ErrorState
          message="Could not load item movement."
          onRetry={() => { void movement.refetch(); }}
        />
      )}

      {data && (
        <>
          <KpiGrid>
            <KpiCard
              label="Items sold"
              value={data.total.toLocaleString()}
              sub={`${data.start} → ${data.end}`}
            />
            <KpiCard
              label="Units"
              value={data.total_quantity.toLocaleString()}
            />
            <KpiCard
              label="Dollars"
              value={fmtMoney2(data.total_amount)}
              tone="positive"
            />
          </KpiGrid>

          {data.rows.length === 0 ? (
            <EmptyState
              title="No movement in this range"
              body="Data appears here as business days are booked from your register journals. Check the range, or set up the site agent under POS import."
            />
          ) : (
            <Section title="Items">
              <Card>
                <div style={{ overflowX: "auto" }}>
                  <Table>
                    <thead>
                      <tr>
                        {["Scan code", "Item", "Qty", "Dollars",
                          "Avg price", ""].map((h) => (
                          <th key={h} style={thStyle}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.rows.map((r) => (
                        <tr key={r.pos_code}>
                          <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                            {r.pos_code}
                          </td>
                          <td style={tdStyle}>{r.description || "—"}</td>
                          <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                            {r.quantity.toLocaleString()}
                          </td>
                          <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                            {fmtMoney2(r.amount)}
                          </td>
                          <td style={{ ...tdStyle, fontFamily: tokens.fontMono }}>
                            {fmtMoney2(r.avg_price)}
                          </td>
                          <td style={tdStyle}>
                            {!r.in_price_book && (
                              <Pill tone="warning">not in price book</Pill>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
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
