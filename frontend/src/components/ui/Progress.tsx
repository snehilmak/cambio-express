import type { CSSProperties } from "react";

import { tokens } from "./tokens";

/** Linear progress bar.  Pass `value` (0-100) for a determinate
 *  bar, omit it for an indeterminate "working" pulse.
 *
 *  Use for genuine progress (uploads, multi-step exports) where
 *  the user benefits from a percentage.  For "we're loading"
 *  states without a known progress, `<Loading>` is the better
 *  primitive — its spinner reads as work-in-progress without
 *  implying a measurable percentage.
 */
export function Progress({
  value, label, style,
}: {
  /** Percent complete, 0-100.  Clamped + rounded internally.
   *  Omit for indeterminate mode (steady pulse). */
  value?: number;
  /** Optional accessible label.  When omitted, the bar gets
   *  a default "Progress" aria-label so it's not anonymous. */
  label?: string;
  style?: CSSProperties;
}) {
  const indeterminate = value == null;
  const pct = indeterminate
    ? null
    : Math.max(0, Math.min(100, Math.round(value)));

  return (
    <div
      role="progressbar"
      aria-label={label ?? "Progress"}
      aria-valuenow={pct ?? undefined}
      aria-valuemin={pct == null ? undefined : 0}
      aria-valuemax={pct == null ? undefined : 100}
      style={{
        position: "relative",
        width: "100%",
        height: 6,
        background: tokens.surface3,
        borderRadius: 999,
        overflow: "hidden",
        ...style,
      }}
    >
      <div
        style={{
          position: indeterminate ? "absolute" : "relative",
          height: "100%",
          width: indeterminate ? "30%" : `${pct}%`,
          background: tokens.accent,
          borderRadius: 999,
          transition: indeterminate
            ? undefined
            : "width 180ms ease-out",
          ...(indeterminate
            ? { animation: "db-progress-indeterminate 1.6s ease-in-out infinite" }
            : {}),
        }}
      />
      {indeterminate && (
        <style>{indeterminateKeyframes}</style>
      )}
    </div>
  );
}

// Keyframe injected inline so callers don't have to register
// anything globally.  Lives in a <style> child of the
// progressbar — duplicate rules across multiple <Progress>
// instances are harmless (the browser collapses them).
const indeterminateKeyframes = `
@keyframes db-progress-indeterminate {
  0%   { left: -30%; }
  100% { left: 100%; }
}
`;
