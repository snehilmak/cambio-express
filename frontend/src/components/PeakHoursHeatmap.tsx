import { Fragment, useMemo } from "react";

import { usePeakHours } from "../api/dashboard";
import { useStoreInfo } from "../api/account";
import { Card, ErrorState, Loading } from "./ui";
import styles from "./PeakHoursHeatmap.module.css";

// Dashboard card: 7×24 heatmap showing transfer activity by
// weekday × hour-of-day in the store's local timezone. Cells
// outside the configured ``store_hours`` window get a dashed
// amber outline so the operator can spot off-hours work.

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function PeakHoursHeatmap({ days = 30 }: { days?: number }) {
  const { data, isLoading, isError, refetch } = usePeakHours(days);
  const { data: storeInfo } = useStoreInfo();

  const outOfHoursMask = useMemo(() => {
    // 7×24 bool grid: true means the cell is outside the
    // store's configured open window (or the day is marked
    // closed). Null when the store hasn't configured hours
    // — we skip the overlay entirely in that state.
    const hours = storeInfo?.store?.store_hours;
    if (!Array.isArray(hours) || hours.length !== 7) return null;
    const mask: boolean[][] = [];
    for (let dow = 0; dow < 7; dow++) {
      const row: boolean[] = [];
      const entry = hours.find((h) => h.day === dow);
      if (!entry || entry.closed) {
        for (let h = 0; h < 24; h++) row.push(true);
      } else {
        const openMin  = _toMinutes(entry.open);
        const closeMin = _toMinutes(entry.close);
        for (let h = 0; h < 24; h++) {
          const hourStart = h * 60;
          const hourEnd   = hourStart + 60;
          // Cell is "out of hours" when no minute of the hour
          // falls inside [open, close).
          const inside = openMin != null && closeMin != null
            && hourEnd > openMin
            && hourStart < closeMin;
          row.push(!inside);
        }
      }
      mask.push(row);
    }
    return mask;
  }, [storeInfo]);

  if (isLoading) {
    return (
      <Card>
        <h2 className={styles.title}>Peak hours</h2>
        <Loading />
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <h2 className={styles.title}>Peak hours</h2>
        <ErrorState
          message="Couldn't load the heatmap."
          onRetry={() => { void refetch(); }}
        />
      </Card>
    );
  }

  const busiestLabel = data.busiest.day_of_week == null
    ? "—"
    : `${DAY_LABELS[data.busiest.day_of_week]} ${
        String(data.busiest.hour).padStart(2, "0")}:00`;

  return (
    <Card>
      <div className={styles.card}>
        <div className={styles.headerRow}>
          <h2 className={styles.title}>Peak hours</h2>
          <span className={styles.meta}>
            {data.from_date} → {data.to_date}
            {data.timezone && data.timezone !== "UTC"
              ? ` · ${data.timezone}` : ""}
          </span>
        </div>

        <div className={styles.kpiRow}>
          <div className={styles.kpi}>
            <span className={styles.kpiLabel}>Total transfers</span>
            <span className={styles.kpiValue}>{data.total_transfers}</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiLabel}>Busiest cell</span>
            <span className={styles.kpiValue}>{busiestLabel}</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiLabel}>Peak count</span>
            <span className={styles.kpiValue}>{data.max_count}</span>
          </div>
        </div>

        <div className={styles.gridWrap}>
          <div className={styles.grid}>
            {/* Top-left empty cell + 24 column headers */}
            <span />
            {Array.from({ length: 24 }, (_, h) => (
              <span key={`h-${h}`} className={styles.colHeader}>
                {h % 3 === 0 ? String(h).padStart(2, "0") : ""}
              </span>
            ))}
            {/* 7 rows × (label + 24 cells) */}
            {DAY_LABELS.map((label, dow) => (
              <Fragment key={`row-${dow}`}>
                <span className={styles.rowHeader}>{label}</span>
                {Array.from({ length: 24 }, (_, h) => {
                  const count = data.grid[dow]?.[h] ?? 0;
                  const bg = _intensityColor(count, data.max_count);
                  const oof = outOfHoursMask?.[dow]?.[h] ?? false;
                  return (
                    <span
                      key={`c-${dow}-${h}`}
                      className={`${styles.cell}${oof ? " " + styles.cellOutOfHours : ""}`}
                      style={{ background: bg }}
                      title={`${label} ${String(h).padStart(2, "0")}:00 — ${count} transfer${count === 1 ? "" : "s"}`}
                    >
                      {count > 0 && (
                        <span className={styles.cellTip}>{count}</span>
                      )}
                    </span>
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>

        <div className={styles.legendRow}>
          <span>Less</span>
          <div className={styles.legendBar}>
            {[0, 0.2, 0.4, 0.6, 0.8, 1].map((t) => (
              <span
                key={t}
                className={styles.legendCell}
                style={{ background: _intensityColor(t * data.max_count, data.max_count) }}
              />
            ))}
          </div>
          <span>More</span>
          {outOfHoursMask && (
            <span>
              · dashed border = outside configured business hours
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}


function _toMinutes(value: string): number | null {
  const m = /^([0-2]\d):([0-5]\d)$/.exec(value);
  if (!m) return null;
  const hh = Number(m[1]);
  if (hh > 23) return null;
  return hh * 60 + Number(m[2]);
}


function _intensityColor(count: number, max: number): string {
  if (max <= 0 || count <= 0) {
    return "var(--db-fill-neutral, rgba(255,255,255,0.04))";
  }
  // Neon-green gradient ramping from 0.10 → 0.85 opacity.
  const t = Math.min(1, count / max);
  const alpha = (0.10 + t * 0.75).toFixed(3);
  return `rgba(63, 255, 0, ${alpha})`;
}
