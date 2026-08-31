import { useSearchParams } from "react-router-dom";

import { useStoreBookMonth } from "../api/storebook";
import {
  Breadcrumbs, Button, Card, ErrorState, KpiCard, KpiGrid, Loading,
  MonthCalendar, PageHeader, PageShell, Select,
} from "../components/ui";
import { fmtMoney2 } from "../lib/formatters";
import styles from "./StoreBookMonth.module.css";

// /app/store-book — the month calendar. One cell per day with its
// sales total and lock state; click through to the day sheet.

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export default function StoreBookMonth() {
  const [sp, setSP] = useSearchParams();
  const now = new Date();
  const year = Number(sp.get("year") ?? now.getFullYear());
  const month = Number(sp.get("month") ?? now.getMonth() + 1);

  const { data, isLoading, isError, refetch } =
    useStoreBookMonth(year, month);

  function shift(delta: number) {
    let y = year;
    let m = month + delta;
    while (m > 12) { y += 1; m -= 12; }
    while (m < 1) { y -= 1; m += 12; }
    const next = new URLSearchParams(sp);
    next.set("year", String(y));
    next.set("month", String(m));
    setSP(next, { replace: true });
  }

  const byDate = new Map(
    (data?.rows ?? []).map((r) => [r.entry_date, r]),
  );

  return (
    <PageShell>
      <Breadcrumbs crumbs={[{ label: "Daily book" }]} />
      <PageHeader
        title="Daily book"
        subtitle={`${MONTHS[month - 1]} ${year}`}
        actions={
          <div className={styles.nav}>
            <Button
              tone="secondary" size="sm"
              onClick={() => shift(-1)} aria-label="Previous month"
            >
              ←
            </Button>
            <Select
              value={month}
              onChange={(e) => {
                const next = new URLSearchParams(sp);
                next.set("month", e.target.value);
                next.set("year", String(year));
                setSP(next, { replace: true });
              }}
              style={{ width: "auto" }}
            >
              {MONTHS.map((label, i) => (
                <option key={i + 1} value={i + 1}>{label}</option>
              ))}
            </Select>
            <Button
              tone="secondary" size="sm"
              onClick={() => shift(1)} aria-label="Next month"
            >
              →
            </Button>
          </div>
        }
      />

      {data && (
        <KpiGrid>
          <KpiCard
            label="Total sales"
            value={fmtMoney2(data.total_sales_cents / 100)}
          />
          <KpiCard
            label="Total gallons"
            value={data.total_fuel_gallons.toLocaleString()}
          />
          <KpiCard
            label="Total fuel"
            value={fmtMoney2(data.total_fuel_cents / 100)}
          />
        </KpiGrid>
      )}

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Couldn't load this month."
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <Card>
          <MonthCalendar
            year={year}
            month={month}
            today={todayIso()}
            hrefFor={(iso) => `/store-book/day?date=${iso}`}
            ariaLabelFor={(iso) => `Open the daily book for ${iso}`}
            dayFor={(iso) => {
              const row = byDate.get(iso);
              if (!row) return undefined;
              return {
                hasData: true,
                locked: row.is_locked,
                primary: fmtMoney2(row.sales_cents / 100),
                variance: row.over_short_cents / 100,
                varianceTitle: "Over/short for the day",
              };
            }}
          />
        </Card>
      )}

    </PageShell>
  );
}
