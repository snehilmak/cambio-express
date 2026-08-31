import { useSearchParams, Link } from "react-router-dom";

import { useStoreBookMonth } from "../api/storebook";
import {
  Breadcrumbs, Button, Card, ErrorState, KpiCard, KpiGrid, Loading,
  PageHeader, PageShell, Select,
} from "../components/ui";
import { fmtMoney2 } from "../lib/formatters";
import styles from "./StoreBookMonth.module.css";

// /app/store-book — the month calendar. One cell per day with its
// sales total and lock state; click through to the day sheet.

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
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

  // Leading blanks so the 1st lands on its weekday.
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const total = daysInMonth(year, month);
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= total; d++) cells.push(d);

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
          <div className={styles.weekdays}>
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
              <div key={d} className={styles.weekday}>{d}</div>
            ))}
          </div>
          <div className={styles.grid}>
            {cells.map((d, i) => {
              if (d == null) {
                return <div key={`b${i}`} className={styles.blank} />;
              }
              const iso = `${year}-${pad2(month)}-${pad2(d)}`;
              const row = byDate.get(iso);
              return (
                <Link
                  key={iso}
                  to={`/store-book/day?date=${iso}`}
                  className={[
                    styles.cell,
                    row ? styles.hasEntry : "",
                    row?.is_locked ? styles.locked : "",
                  ].filter(Boolean).join(" ")}
                  aria-label={`Open the daily book for ${iso}`}
                >
                  <div className={styles.cellHead}>
                    <span className={styles.cellDay}>{d}</span>
                    {row?.is_locked && (
                      <span
                        className={styles.lockMark}
                        aria-label="Locked"
                      >
                        🔒
                      </span>
                    )}
                  </div>
                  {row && (
                    <div className={styles.cellBody}>
                      <div className={styles.cellTotal}>
                        {fmtMoney2(row.sales_cents / 100)}
                      </div>
                      {row.over_short_cents !== 0 && (
                        <span
                          className={[
                            styles.variance,
                            row.over_short_cents > 0
                              ? styles.over : styles.short,
                          ].join(" ")}
                        >
                          {row.over_short_cents > 0 ? "+" : "−"}
                          {fmtMoney2(
                            Math.abs(row.over_short_cents) / 100,
                          )}
                        </span>
                      )}
                    </div>
                  )}
                </Link>
              );
            })}
          </div>
        </Card>
      )}
    </PageShell>
  );
}
