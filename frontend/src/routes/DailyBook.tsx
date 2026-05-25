import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useDailyPeriod, type DailyReportRow } from "../api/dailybook";
import {
  Breadcrumbs,
  Button, Card, ErrorState, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
} from "../components/ui";
import styles from "./DailyBook.module.css";

// /app/daily — the Daily Book landing page. A calendar of the
// chosen month + a monthly summary strip. Each day cell is a link
// to /app/daily/edit?date=YYYY-MM-DD where the per-day editor
// lives. Mirrors the legacy Jinja `/daily` UX: pick the day from
// the calendar, then enter that day's book.

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function pad2(n: number): string {
  return n.toString().padStart(2, "0");
}

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function firstOfMonthIso(year: number, monthZeroIdx: number): string {
  return `${year}-${pad2(monthZeroIdx + 1)}-01`;
}

function lastOfMonthIso(year: number, monthZeroIdx: number): string {
  const lastDay = new Date(year, monthZeroIdx + 1, 0).getDate();
  return `${year}-${pad2(monthZeroIdx + 1)}-${pad2(lastDay)}`;
}

function fmtMoney(n: number | undefined | null): string {
  if (n == null || !isFinite(n)) return "$0";
  return n.toLocaleString(undefined, {
    style: "currency", currency: "USD",
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  });
}

function fmtMoney2(n: number | undefined | null): string {
  if (n == null || !isFinite(n)) return "$0.00";
  return n.toLocaleString(undefined, {
    style: "currency", currency: "USD",
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}

export default function DailyBook() {
  const [params, setParams] = useSearchParams();

  // Read year+month from the URL. Default to current month so the
  // page is shareable + bookmarkable per month.
  const now = useMemo(() => new Date(), []);
  const yearParam = parseInt(params.get("year") || "", 10);
  const monthParam = parseInt(params.get("month") || "", 10);
  const year = Number.isFinite(yearParam) && yearParam > 1970
    ? yearParam
    : now.getFullYear();
  const month = Number.isFinite(monthParam) && monthParam >= 1 && monthParam <= 12
    ? monthParam - 1
    : now.getMonth();

  const from = firstOfMonthIso(year, month);
  const to = lastOfMonthIso(year, month);

  const { data, isLoading, isError, error, refetch } = useDailyPeriod(
    from, to,
  );

  const reportByDate = useMemo(() => {
    const m = new Map<string, DailyReportRow>();
    for (const row of data?.rows ?? []) m.set(row.report_date, row);
    return m;
  }, [data]);

  function navMonth(delta: number) {
    const next = new Date(year, month + delta, 1);
    const ny = next.getFullYear();
    const nm = next.getMonth() + 1;
    const p = new URLSearchParams(params);
    p.set("year", String(ny));
    p.set("month", String(nm));
    setParams(p, { replace: true });
  }

  const today = todayIso();

  return (
    <PageShell maxWidth="68rem" gap="1.5rem">

      <Breadcrumbs crumbs={[{ label: "Daily" }]} />

      <PageHeader
        title="Daily Book"
        subtitle={`${MONTH_NAMES[month]} ${year}`}
        actions={(
          <div className={styles.navRow}>
            <Button
              tone="secondary" size="sm"
              onClick={() => navMonth(-1)}
              aria-label="Previous month"
            >
              ←
            </Button>
            <Button
              tone="secondary" size="sm"
              onClick={() => navMonth(0)}
              title="Jump to current month"
            >
              Today
            </Button>
            <Button
              tone="secondary" size="sm"
              onClick={() => navMonth(1)}
              aria-label="Next month"
            >
              →
            </Button>
          </div>
        )}
      />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load month."}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <KpiGrid minWidth="180px">
          <KpiCard
            label="Days logged"
            value={`${data.days_logged} / ${daysInMonth(year, month)}`}
          />
          <KpiCard
            label="Total in"
            value={fmtMoney(data.total_receipts)}
            tone="positive"
          />
          <KpiCard
            label="Total out"
            value={fmtMoney(data.total_disbursements)}
          />
          <KpiCard
            label="Net"
            value={fmtMoney(data.net)}
            tone={data.net >= 0 ? "positive" : "negative"}
          />
        </KpiGrid>
      )}

      {data && (
        <Card padding="clamp(0.5rem, 2.5vw, 1.25rem)">
          <Calendar
            year={year}
            month={month}
            today={today}
            reportByDate={reportByDate}
          />
          <Legend />
        </Card>
      )}
    </PageShell>
  );
}


function daysInMonth(year: number, monthZeroIdx: number): number {
  return new Date(year, monthZeroIdx + 1, 0).getDate();
}


// ── Calendar grid ────────────────────────────────────────────

function Calendar({
  year, month, today, reportByDate,
}: {
  year: number;
  month: number;
  today: string;
  reportByDate: Map<string, DailyReportRow>;
}) {
  const firstWeekday = new Date(year, month, 1).getDay(); // 0 = Sun
  const total = daysInMonth(year, month);

  // Build a flat list of cells: leading blanks + the days + trailing
  // blanks (to round to a 6-row grid for layout stability).
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= total; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div>
      <div className={styles.weekHeaderRow}>
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
          <div key={d} className={styles.weekHeaderCell}>{d}</div>
        ))}
      </div>
      <div className={styles.grid}>
        {cells.map((day, i) => {
          if (day == null) {
            return <div key={`b${i}`} className={styles.emptyCell} />;
          }
          const iso = `${year}-${pad2(month + 1)}-${pad2(day)}`;
          const report = reportByDate.get(iso);
          const isToday = iso === today;
          const hasReport = report != null;
          const locked = Boolean(report?.locked);
          return (
            <CalendarCell
              key={iso}
              iso={iso}
              day={day}
              isToday={isToday}
              hasReport={hasReport}
              locked={locked}
              report={report}
            />
          );
        })}
      </div>
    </div>
  );
}


function CalendarCell({
  iso, day, isToday, hasReport, locked, report,
}: {
  iso: string;
  day: number;
  isToday: boolean;
  hasReport: boolean;
  locked: boolean;
  report: DailyReportRow | undefined;
}) {
  const total = report
    ? (report.total_receipts ?? 0) - (report.total_disbursements ?? 0)
    : 0;
  const over = (report?.over_short ?? 0);
  const hasVariance = Math.abs(over) >= 0.005;

  const cls = [
    styles.cell,
    hasReport ? styles.cellHasReport : "",
    isToday   ? styles.cellToday    : "",
    locked    ? styles.cellLocked   : "",
    "ds-card--interactive",
  ].filter(Boolean).join(" ");

  return (
    <Link
      to={`/daily/edit?date=${iso}`}
      className={cls}
      aria-label={`Open daily book for ${iso}`}
    >
      <div className={styles.cellHeader}>
        <span className={styles.cellDay}>{day}</span>
        {locked && (
          <svg
            width="12" height="12" viewBox="0 0 24 24"
            stroke="currentColor" fill="none" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round"
            className={styles.lockIcon}
            aria-label="Locked"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        )}
      </div>

      {hasReport && (
        <div className={styles.dots} aria-hidden="true">
          <span className={`${styles.dot} ${styles.dotEntry}`} />
          {hasVariance && (
            <span
              className={`${styles.dot} ${over > 0 ? styles.dotOverPos : styles.dotOverNeg}`}
            />
          )}
          {locked && <span className={`${styles.dot} ${styles.dotLocked}`} />}
        </div>
      )}

      {hasReport && (
        <div className={styles.cellMoneyWrap}>
          <div className={styles.cellMoney}>{fmtMoney(total)}</div>
          {hasVariance && (
            <span
              className={`${styles.overPill} ${over > 0 ? styles.overPos : styles.overNeg}`}
              title={`Over/short: ${fmtMoney2(over)}`}
            >
              {over > 0 ? "+" : ""}{fmtMoney2(over)}
            </span>
          )}
        </div>
      )}
    </Link>
  );
}


function Legend() {
  return (
    <div className={styles.legend}>
      <span className={styles.legendItem}>
        <span className={`${styles.swatch} ${styles.cellToday}`} />
        Today
      </span>
      <span className={styles.legendItem}>
        <span className={`${styles.swatch} ${styles.cellHasReport}`} />
        Has entry
      </span>
      <span className={styles.legendItem}>
        <span className={`${styles.swatch} ${styles.cellLocked}`} />
        Locked
      </span>
      <span className={styles.legendItem}>
        <span className={styles.swatch} />
        No entry yet
      </span>
    </div>
  );
}
