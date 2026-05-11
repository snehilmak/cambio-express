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

// Design-token mirror. Keep in sync with static/design-tokens.css.
// chart.js renders into <canvas> so we can't pass `var(--db-*)`
// directly — these literal values are what the design system
// resolves to in dark mode.
const TOKEN = {
  textMuted: "#a3a3a3",
  borderSubtle: "#1f1f1f",
  surface2: "#141414",
  border: "#262626",
  text: "#f5f5f5",
} as const;


// Shared base — extracted so the two presets only differ in their
// tick formatter + the tooltip label.
function baseOptions<T extends ChartType = "line">(
  label: string,
  format: (v: number) => string,
): ChartOptions<T> {
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
        backgroundColor: TOKEN.surface2,
        titleColor: TOKEN.text,
        bodyColor: TOKEN.text,
        borderColor: TOKEN.border,
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
          color: TOKEN.textMuted,
          callback: (v: string | number) =>
            format(typeof v === "number" ? v : Number(v)),
        },
        grid: { color: TOKEN.borderSubtle },
      },
      x: {
        ticks: {
          color: TOKEN.textMuted,
          maxRotation: 0,
          autoSkip: true,
          autoSkipPadding: 12,
        },
        grid: { color: TOKEN.borderSubtle },
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
