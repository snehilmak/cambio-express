import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useDailyPeriod, type DailyReportRow } from "../api/dailybook";
import { fmtMoney, fmtMoney2 } from "../lib/formatters";
import {
  Button, ButtonLink, Card, ErrorState, KpiCard, KpiGrid, Loading,
  MonthCalendar, MonthCalendarLegend, PageHeader, PageShell,
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
    <PageShell gap="1.5rem">

      <PageHeader
        title="MSB Daily book"
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
            <ButtonLink
              to={`/daily/edit?date=${today}`}
              tone="secondary" size="sm"
              title="Open today's daily book"
            >
              Today
            </ButtonLink>
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
          <MonthCalendarLegend />
        </Card>
      )}
    </PageShell>
  );
}


function daysInMonth(year: number, monthZeroIdx: number): number {
  return new Date(year, monthZeroIdx + 1, 0).getDate();
}


// The month grid itself is the shared kit component — the store
// daily book renders the same one. This page only says what a day
// CONTAINS; how a day looks lives in MonthCalendar.

function Calendar({
  year, month, today, reportByDate,
}: {
  year: number;
  /** 0-11, as JS Date gives it. */
  month: number;
  today: string;
  reportByDate: Map<string, DailyReportRow>;
}) {
  return (
    <MonthCalendar
      year={year}
      month={month + 1}
      today={today}
      hrefFor={(iso) => `/daily/edit?date=${iso}`}
      ariaLabelFor={(iso) => `Open daily book for ${iso}`}
      dayFor={(iso) => {
        const report = reportByDate.get(iso);
        if (!report) return undefined;
        const total =
          (report.total_receipts ?? 0) - (report.total_disbursements ?? 0);
        const over = report.over_short ?? 0;
        return {
          hasData: true,
          locked: Boolean(report.locked),
          primary: fmtMoney(total),
          variance: over,
          varianceTitle: `Over/short: ${fmtMoney2(over)}`,
        };
      }}
    />
  );
}


