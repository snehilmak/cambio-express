import { Link } from "react-router-dom";

import styles from "./MonthCalendar.module.css";

/** A month grid of days, each linking to that day's page.
 *
 *  Both daily books render one of these — the MSB cash ledger and
 *  the store daily book — so the grid math, the containment rules
 *  and the today / locked / has-data styling live here once
 *  instead of being reimplemented per page.
 *
 *  Callers supply only what a day CONTAINS, via `dayFor`; the
 *  calendar owns how a day looks.
 *
 *  The containment is load-bearing, not incidental. A seven-column
 *  grid makes each cell far narrower than any `vw`-based guess, so
 *  cells are inline-size containers and the money text sizes
 *  against the CELL. Without that (plus `min-width: 0` so flex
 *  children can shrink at all, and an explicit `box-sizing` on the
 *  variance pill — the app shell has no global border-box reset) a
 *  six-figure day paints straight through the cell border into the
 *  next one. That was a real reported bug; the fix belongs here so
 *  the next calendar inherits it.
 */
export interface MonthCalendarDay {
  /** Primary figure, already formatted (e.g. "$1,296"). */
  primary?: string;
  /** Variance in DOLLARS. A non-zero value renders the +/- pill,
   *  tinted by sign. Pass 0 or omit for no pill. */
  variance?: number;
  /** Renders the lock mark and a dashed border. */
  locked?: boolean;
  /** Tints the cell as "this day has something in it". */
  hasData?: boolean;
  /** Tooltip for the variance pill. */
  varianceTitle?: string;
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];


/** Key to the calendar's cell states. Lives here rather than on a
 *  page because it describes MonthCalendar's own visual language —
 *  if a cell state changes, the legend that explains it is right
 *  next to it. */
export function MonthCalendarLegend() {
  return (
    <div className={styles.legend}>
      <span className={styles.legendItem}>
        <span className={`${styles.swatch} ${styles.isToday}`} />
        Today
      </span>
      <span className={styles.legendItem}>
        <span className={`${styles.swatch} ${styles.hasData}`} />
        Has entry
      </span>
      <span className={styles.legendItem}>
        <span className={`${styles.swatch} ${styles.isLocked}`} />
        Locked
      </span>
      <span className={styles.legendItem}>
        <span className={styles.swatch} />
        No entry yet
      </span>
    </div>
  );
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}

export function MonthCalendar({
  year, month, today, dayFor, hrefFor, ariaLabelFor,
}: {
  year: number;
  /** 1-12. Callers work in human months; the Date maths is here. */
  month: number;
  /** ISO date to highlight as today, if it falls in this month. */
  today?: string;
  dayFor: (iso: string) => MonthCalendarDay | undefined;
  hrefFor: (iso: string) => string;
  ariaLabelFor?: (iso: string) => string;
}) {
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const total = daysInMonth(year, month);

  // Leading blanks so the 1st lands on its weekday, then trailing
  // blanks to complete the final week — a ragged last row makes the
  // grid look broken rather than finished.
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= total; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div>
      <div className={styles.weekHeader}>
        {WEEKDAYS.map((d) => (
          <div key={d} className={styles.weekHeaderCell}>{d}</div>
        ))}
      </div>
      <div className={styles.grid}>
        {cells.map((day, i) => {
          if (day == null) {
            return <div key={`b${i}`} className={styles.emptyCell} />;
          }
          const iso = `${year}-${pad2(month)}-${pad2(day)}`;
          const info = dayFor(iso);
          const variance = info?.variance ?? 0;
          const hasVariance = Math.abs(variance) >= 0.005;
          const cls = [
            styles.cell,
            info?.hasData ? styles.hasData : "",
            today === iso ? styles.isToday : "",
            info?.locked ? styles.isLocked : "",
            "ds-card--interactive",
          ].filter(Boolean).join(" ");

          return (
            <Link
              key={iso}
              to={hrefFor(iso)}
              className={cls}
              aria-label={ariaLabelFor?.(iso) ?? `Open ${iso}`}
            >
              <div className={styles.cellHeader}>
                <span className={styles.cellDay}>{day}</span>
                {info?.locked && (
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

              {/* Below 36rem the money is hidden and the day's state
                  shows as dots instead — a phone cell has no room
                  for figures, but "there's an entry, and it was
                  off" still fits. */}
              {info?.hasData && (
                <div className={styles.dots} aria-hidden="true">
                  <span className={`${styles.dot} ${styles.dotEntry}`} />
                  {hasVariance && (
                    <span
                      className={`${styles.dot} ${
                        variance > 0 ? styles.dotOverPos : styles.dotOverNeg
                      }`}
                    />
                  )}
                  {info.locked && (
                    <span className={`${styles.dot} ${styles.dotLocked}`} />
                  )}
                </div>
              )}

              {info?.primary != null && (
                <div className={styles.moneyWrap}>
                  <div className={styles.money}>{info.primary}</div>
                  {hasVariance && (
                    <span
                      className={`${styles.pill} ${
                        variance > 0 ? styles.pillOver : styles.pillShort
                      }`}
                      title={info.varianceTitle}
                    >
                      {variance > 0 ? "+" : "−"}
                      {Math.abs(variance).toLocaleString(undefined, {
                        style: "currency", currency: "USD",
                      })}
                    </span>
                  )}
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
