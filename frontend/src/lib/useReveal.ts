import { useEffect, useRef, useState, type RefObject } from "react";

/** Marketing-page scroll reveal.
 *
 *  Returns a `ref` to attach to the element you want to animate
 *  in, and a `revealed` boolean that flips to `true` once the
 *  element is at least partly in the viewport.  Pair with a CSS
 *  rule that transitions from a "hidden" state (opacity 0 +
 *  translateY) to a "shown" state when the element gets a class
 *  like `.is-revealed`.
 *
 *  Usage:
 *
 *  ```tsx
 *  const { ref, revealed } = useReveal<HTMLDivElement>();
 *  return (
 *    <div ref={ref} className={`reveal ${revealed ? "is-revealed" : ""}`}>
 *      ...content...
 *    </div>
 *  );
 *  ```
 *
 *  Honors `prefers-reduced-motion: reduce` — for those users we
 *  flip `revealed` to true immediately so they see the static
 *  content with no transition.
 *
 *  One-shot: the observer disconnects after first reveal so we
 *  don't pay the cost of watching every element forever.
 */
export type RevealVariant =
  | "fade-up"      // opacity + translateY (default)
  | "from-left"    // opacity + translateX(-)
  | "from-right"   // opacity + translateX(+)
  | "scale-up"     // opacity + scale
  | "blur";        // opacity + filter blur


export function useReveal<T extends HTMLElement = HTMLDivElement>(
  options?: { threshold?: number; rootMargin?: string },
): { ref: RefObject<T | null>; revealed: boolean } {
  const ref = useRef<T | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    if (revealed) return;
    const el = ref.current;
    if (!el) return;

    // Reduced-motion users get the final state immediately —
    // no transition, no surprise.
    if (
      typeof window !== "undefined"
      && window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reduced-motion users get the final state with no transition; that's the entire purpose
      setRevealed(true);
      return;
    }

    // SSR / very old browser fallback: just show.
    if (typeof IntersectionObserver === "undefined") {
      setRevealed(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setRevealed(true);
            observer.disconnect();
            break;
          }
        }
      },
      {
        threshold: options?.threshold ?? 0.15,
        // Trigger when the element is 10% above the viewport
        // bottom — animation finishes by the time the user looks
        // at it (less obvious "popping in" feel).
        rootMargin: options?.rootMargin ?? "0px 0px -10% 0px",
      },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [revealed, options?.threshold, options?.rootMargin]);

  return { ref, revealed };
}
