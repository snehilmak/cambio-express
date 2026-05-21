import { useEffect, useState } from "react";

/** Animate a number from `start` to `end` over `durationMs`.
 *
 *  Returns the current value, re-rendering every animation
 *  frame.  Use to make stat-strip numbers count up when the
 *  user scrolls them into view — pair with `useReveal()` to
 *  drive the `trigger` flag.
 *
 *  Ease-out cubic so the number decelerates as it approaches
 *  the target — feels more polished than linear.
 *
 *  Reduced-motion users skip the animation and see the final
 *  value immediately.
 *
 *  Usage:
 *
 *  ```tsx
 *  const { ref, revealed } = useReveal();
 *  const shops = useCountUp(2400, { trigger: revealed });
 *  return <div ref={ref}>{Math.round(shops)}+ MSB shops</div>;
 *  ```
 */
export function useCountUp(
  end: number,
  options?: {
    /** Animation length in milliseconds.  Default 1500ms. */
    duration?: number;
    /** Value to count up FROM. Default 0. */
    start?: number;
    /** Hold at `start` until this flips to true.  Default true
     *  (animate immediately on mount). */
    trigger?: boolean;
  },
): number {
  const { duration = 1500, start = 0, trigger = true } = options ?? {};
  const [value, setValue] = useState(start);

  useEffect(() => {
    if (!trigger) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset to `start` when trigger flips false so re-arming the counter restarts from zero
      setValue(start);
      return;
    }
    if (
      typeof window !== "undefined"
      && window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setValue(end);
      return;
    }

    const startTime =
      typeof performance !== "undefined" ? performance.now() : Date.now();
    let rafId: number | null = null;

    const tick = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic — feels faster at first then settles.
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(start + (end - start) * eased);
      if (progress < 1) {
        rafId = requestAnimationFrame(tick);
      }
    };

    rafId = requestAnimationFrame(tick);
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, [end, duration, start, trigger]);

  return value;
}
