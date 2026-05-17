// Shared chart.js option presets so every Line/Bar in the SPA picks
// up the same dark tooltip + axis treatment without each route
// re-declaring it. Built around the design-system tokens (matching
// `var(--db-*)` hex values inline because chart.js renders to
// canvas — it can't read CSS variables at runtime).
//
// Two presets:
//   moneyChartOptions(label)  — $-prefixed Y-axis ticks + tooltip
//                                values. Use on revenue / volume /
//                                fees charts (OwnerDashboard,
//                                OwnerStoreDetail volume, etc.).
//   countChartOptions(label)  — plain integer-formatted ticks.
//                                Use on transfer-count charts,
//                                signup funnels, DAU/MAU, etc.
//
// Both presets return a fresh object on every call so a per-route
// override (`{ ...moneyChartOptions("Volume"), plugins: {...} }`)
// doesn't mutate other charts.

import type { ChartOptions, ChartType, TooltipItem } from "chart.js";

// All Line + Bar charts in the SPA share these options. The
// chart.js type system makes a strict `ChartOptions<"line">` vs.
// `ChartOptions<"bar">` distinction that doesn't matter for these
// presets (the option shape is identical), so the helpers are
// generic over the chart type and consumers pick the variant
// that fits their `<Line>` or `<Bar>` call site.

// chart.js renders into <canvas> so we can't pass ``var(--db-*)``
// directly. Instead, resolve the design-system variables off the
// document at call time. This means a Bar/Line built right after
// the theme flips automatically picks up the new palette; an
// existing chart re-renders on the next state change. The
// fallback hex values match the dark-mode resolved tokens so
// pre-mount or SSR contexts (no ``document``) still look right.
function _resolveToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

function _tokens() {
  return {
    textMuted:    _resolveToken("--db-text-muted", "#a3a3a3"),
    borderSubtle: _resolveToken("--db-border-subtle", "#1f1f1f"),
    surface2:     _resolveToken("--db-surface-2", "#141414"),
    border:       _resolveToken("--db-border", "#262626"),
    text:         _resolveToken("--db-text", "#f5f5f5"),
  };
}


/** Resolved theme tokens for inline chart options that can't use
 *  ``moneyChartOptions`` / ``countChartOptions`` directly (e.g.
 *  dual-axis charts). Returns the same palette ``baseOptions``
 *  uses so routes mixing the two stay visually consistent. */
export function chartTokens() {
  return _tokens();
}


// Shared base — extracted so the two presets only differ in their
// tick formatter + the tooltip label.
function baseOptions<T extends ChartType = "line">(
  label: string,
  format: (v: number) => string,
): ChartOptions<T> {
  const t = _tokens();
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      // Index mode means a hover anywhere on the X axis lights up
      // every dataset at that index. Better for trend charts than
      // the default "nearest" mode which can leave one dataset
      // unhighlighted when points overlap.
      mode: "index",
      intersect: false,
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: "index",
        intersect: false,
        backgroundColor: t.surface2,
        titleColor: t.text,
        bodyColor: t.text,
        borderColor: t.border,
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
        displayColors: false,
        titleFont: { size: 12, weight: 600 },
        bodyFont: { size: 12 },
        callbacks: {
          label: (ctx: TooltipItem<ChartType>) => {
            const y = (ctx.parsed as { y?: number | null }).y ?? 0;
            return `${label}: ${format(y)}`;
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          color: t.textMuted,
          callback: (v: string | number) =>
            format(typeof v === "number" ? v : Number(v)),
        },
        grid: { color: t.borderSubtle },
      },
      x: {
        ticks: {
          color: t.textMuted,
          maxRotation: 0,
          autoSkip: true,
          autoSkipPadding: 12,
        },
        grid: { color: t.borderSubtle },
      },
    },
  } as unknown as ChartOptions<T>;
}


/** Chart options preset for monetary series. Y-axis ticks + tooltip
 *  values are `$N,NNN`. `label` is the tooltip series label
 *  (e.g. `"Volume"`, `"Fees"`). */
export function moneyChartOptions<T extends ChartType = "line">(
  label: string,
): ChartOptions<T> {
  return baseOptions<T>(
    label,
    (v) => `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
  );
}


/** Chart options preset for count series. Y-axis ticks + tooltip
 *  values are comma-grouped integers (`12,345`). */
export function countChartOptions<T extends ChartType = "line">(
  label: string,
): ChartOptions<T> {
  return baseOptions<T>(
    label,
    (v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 }),
  );
}
