import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useDailyPeriod, type DailyReportRow } from "../api/dailybook";
import {
  Card, ErrorState, KpiCard, KpiGrid, Loading, PageHeader, PageShell,
  tokens,
} from "../components/ui";

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
      <PageHeader
        title="Daily Book"
        subtitle={`${MONTH_NAMES[month]} ${year}`}
        actions={(
          <div style={navRow}>
            <button
              type="button"
              onClick={() => navMonth(-1)}
              style={navBtnStyle}
              aria-label="Previous month"
            >
              ←
            </button>
            <button
              type="button"
              onClick={() => navMonth(0)}
              style={navBtnStyle}
              title="Jump to current month"
            >
              Today
            </button>
            <button
              type="button"
              onClick={() => navMonth(1)}
              style={navBtnStyle}
              aria-label="Next month"
            >
              →
            </button>
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
            label="Total receipts"
            value={fmtMoney(data.total_receipts)}
            tone="positive"
          />
          <KpiCard
            label="Total disbursements"
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
        <Card padding="1.25rem">
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
      <div style={weekHeaderRow}>
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
          <div key={d} style={weekHeaderCell}>{d}</div>
        ))}
      </div>
      <div style={gridStyle}>
        {cells.map((day, i) => {
          if (day == null) {
            return <div key={`b${i}`} style={emptyCellStyle} />;
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

  const styles: React.CSSProperties = {
    ...cellBaseStyle,
    ...(hasReport ? cellHasReportStyle : {}),
    ...(isToday ? cellTodayStyle : {}),
    ...(locked ? cellLockedStyle : {}),
  };

  return (
    <Link
      to={`/daily/edit?date=${iso}`}
      style={styles}
      aria-label={`Open daily book for ${iso}`}
      className="ds-card--interactive"
    >
      <div style={cellHeaderStyle}>
        <span style={cellDayStyle}>{day}</span>
        {locked && (
          <svg
            width="14" height="14" viewBox="0 0 24 24"
            stroke="currentColor" fill="none" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round"
            style={{ color: tokens.warning }}
            aria-label="Locked"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        )}
      </div>
      {hasReport ? (
        <>
          <div style={cellMoneyStyle}>{fmtMoney(total)}</div>
          {Math.abs(over) >= 0.005 && (
            <span
              style={{
                ...overPillStyle,
                color: over > 0 ? tokens.accent : tokens.negative,
                borderColor: over > 0 ? tokens.accent : tokens.negative,
              }}
              title={`Over/short: ${fmtMoney2(over)}`}
            >
              {over > 0 ? "+" : ""}{fmtMoney2(over)}
            </span>
          )}
        </>
      ) : (
        <div style={cellEmptyHintStyle}>—</div>
      )}
    </Link>
  );
}


function Legend() {
  return (
    <div style={legendStyle}>
      <span style={legendItem}>
        <span style={{ ...swatchStyle, ...cellTodayStyle }} />
        Today
      </span>
      <span style={legendItem}>
        <span style={{ ...swatchStyle, ...cellHasReportStyle }} />
        Has entry
      </span>
      <span style={legendItem}>
        <span
          style={{ ...swatchStyle, ...cellLockedStyle }}
        />
        Locked
      </span>
      <span style={legendItem}>
        <span style={{ ...swatchStyle }} />
        No entry yet
      </span>
    </div>
  );
}


// ── Styles ───────────────────────────────────────────────────

const navRow: React.CSSProperties = {
  display: "inline-flex",
  gap: "0.4rem",
  alignItems: "center",
};

const navBtnStyle: React.CSSProperties = {
  background: tokens.surface,
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.5rem 0.9rem",
  fontFamily: tokens.fontBody,
  fontSize: "0.9rem",
  fontWeight: 500,
  cursor: "pointer",
  minWidth: "2.5rem",
};

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(7, 1fr)",
  gap: "0.5rem",
};

const weekHeaderRow: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(7, 1fr)",
  gap: "0.5rem",
  marginBottom: "0.5rem",
};

const weekHeaderCell: React.CSSProperties = {
  fontSize: "0.7rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: tokens.textMuted,
  textAlign: "center",
  padding: "0.4rem 0",
  fontWeight: 600,
};

const cellBaseStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.25rem",
  padding: "0.7rem 0.65rem",
  borderRadius: "0.65rem",
  border: `1px solid ${tokens.border}`,
  background: tokens.surface2,
  textDecoration: "none",
  color: tokens.text,
  minHeight: "5.25rem",
};

const cellHasReportStyle: React.CSSProperties = {
  background: tokens.surface,
  borderColor: "rgba(63, 255, 0, 0.25)",
};

const cellTodayStyle: React.CSSProperties = {
  borderColor: tokens.accent,
  boxShadow: "0 0 0 1px rgba(63, 255, 0, 0.35) inset",
};

const cellLockedStyle: React.CSSProperties = {
  borderStyle: "dashed",
  opacity: 0.94,
};

const emptyCellStyle: React.CSSProperties = {
  background: "transparent",
  minHeight: "5.25rem",
};

const cellHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  fontFamily: tokens.fontDisplay,
};

const cellDayStyle: React.CSSProperties = {
  fontSize: "1rem",
  fontWeight: 700,
};

const cellMoneyStyle: React.CSSProperties = {
  fontFamily: tokens.fontMono,
  fontSize: "0.85rem",
  fontWeight: 600,
  color: tokens.text,
};

const cellEmptyHintStyle: React.CSSProperties = {
  fontSize: "0.85rem",
  color: tokens.textMuted,
};

const overPillStyle: React.CSSProperties = {
  display: "inline-block",
  alignSelf: "flex-start",
  fontFamily: tokens.fontMono,
  fontSize: "0.65rem",
  fontWeight: 600,
  padding: "0.1rem 0.35rem",
  borderRadius: "0.3rem",
  border: "1px solid transparent",
};

const legendStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "1rem",
  marginTop: "1rem",
  paddingTop: "0.75rem",
  borderTop: `1px solid ${tokens.border}`,
  fontSize: "0.75rem",
  color: tokens.textMuted,
};

const legendItem: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.45rem",
};

const swatchStyle: React.CSSProperties = {
  display: "inline-block",
  width: "1.25rem",
  height: "0.9rem",
  borderRadius: "0.25rem",
};
