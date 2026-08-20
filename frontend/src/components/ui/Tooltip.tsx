import {
  useEffect, useId, useRef, useState, type CSSProperties, type ReactElement, type ReactNode,
} from "react";

import { tokens } from "./tokens";

/** Hover/focus tooltip with a short delay before showing.
 *
 *  Wraps a single child element and renders a small tip
 *  positioned beneath it.  The wrapper element gets
 *  `aria-describedby` pointing at the tip so screen readers
 *  announce the description alongside the trigger.
 *
 *  Use this instead of the native `title=` attribute when:
 *  - the description is longer than 4-5 words
 *  - you want consistent visual treatment with the design system
 *  - you want the tip to appear on keyboard focus, not just hover
 *
 *  Set `placement="top"` (default) or `"bottom"` to control where
 *  the tip sits.  For more sophisticated positioning (collision
 *  avoidance, arrow points, etc.) reach for a real floating-ui
 *  library — this is the lightweight kit version.
 *
 *  The visibility delay (default 250ms) prevents flickering when
 *  the user is just sweeping their cursor past the trigger.
 */
export function Tooltip({
  label, children, placement = "top", delayMs = 250, multiline = false,
}: {
  /** Description text.  Pass a plain string; use the global
   *  Toast primitive instead if you need a multi-line callout
   *  with actions. */
  label: string;
  /** A single focusable element (button, link, icon-button).
   *  The wrapper attaches hover + focus listeners to it. */
  children: ReactElement;
  placement?: "top" | "bottom";
  delayMs?: number;
  /** Wrap long descriptions instead of forcing one line. Use for
   *  sentence-length tips (e.g. the InfoTip primitive); keep the
   *  default single-line treatment for short action hints. */
  multiline?: boolean;
}) {
  const tipId = useId();
  const [open, setOpen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function show() {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setOpen(true), delayMs);
  }
  function hide() {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setOpen(false);
  }

  // Clean up the show-delay timer on unmount so we don't pop a
  // tooltip after the trigger has been removed.
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      // Clone-via-prop-spread would be cleaner but adds churn at
      // every call site — wrap in a relative span instead and
      // hang aria-describedby off the trigger via React's
      // children-as-element pattern.
    >
      <ChildWithDescribedBy id={tipId}>{children}</ChildWithDescribedBy>
      {open && (
        <span
          id={tipId}
          role="tooltip"
          style={tipStyle(placement, multiline)}
        >
          {label}
        </span>
      )}
    </span>
  );
}

// Wraps the single trigger child + adds aria-describedby to it.
// We don't clone with React.cloneElement because TS strictness
// around its props type is a pain; instead we just re-emit the
// child with the extra attribute via a tiny prop merge.
function ChildWithDescribedBy({
  id, children,
}: { id: string; children: ReactElement }): ReactNode {
  const child = children as ReactElement<{ "aria-describedby"?: string }>;
  const existing = child.props["aria-describedby"];
  const merged = existing ? `${existing} ${id}` : id;
  // React 19 supports the new spread; falling back to the
  // explicit children pattern keeps it dependency-free.
  return {
    ...child,
    props: { ...child.props, "aria-describedby": merged },
  } as unknown as ReactNode;
}

function tipStyle(
  placement: "top" | "bottom", multiline = false,
): CSSProperties {
  // Small offset for the slide-from-direction effect — the tip
  // starts shifted toward the trigger then settles into place,
  // matching the shadcn / sonner motion vocabulary.
  const slideFrom = placement === "top" ? "4px" : "-4px";
  return {
    position: "absolute",
    left: "50%",
    [placement === "top" ? "bottom" : "top"]: "calc(100% + 6px)",
    background: tokens.surface3,
    color: tokens.text,
    border: `1px solid ${tokens.border}`,
    borderRadius: "0.4rem",
    padding: "0.35rem 0.55rem",
    fontSize: "0.78rem",
    lineHeight: 1.35,
    ...(multiline
      ? { whiteSpace: "normal" as const, width: "max-content", maxWidth: "16rem" }
      : { whiteSpace: "nowrap" as const }),
    boxShadow: "0 8px 20px rgba(0, 0, 0, 0.35)",
    pointerEvents: "none",
    zIndex: 200,
    // Smooth fade + tiny slide-in.  Sub-150ms keeps it responsive.
    // CSS animations are stripped by the global prefers-reduced-
    // motion rule for opt-in users.
    animation: "db-tooltip-in 140ms ease-out",
    // The keyframe defines the FROM state; the static `transform`
    // here is the TO state (final resting position).
    transform: "translateX(-50%) translateY(0)",
    // Internal animation variable — deliberately NOT prefixed with
    // `--db-` since it's a component-internal slide-from offset, not
    // a design-system token (the theme-token CI test treats every
    // `--db-*` reference as a DS token that must be declared in
    // static/design-tokens.css).
    ["--tooltip-slide-from" as string]: slideFrom,
  };
}

// Inject the keyframe once on first mount.  Living in a module
// scoped <style> tag inside the Tooltip would re-mount per-tooltip;
// global injection is simpler and dedups via the id check.
if (typeof document !== "undefined") {
  const id = "db-tooltip-keyframes";
  if (!document.getElementById(id)) {
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
@keyframes db-tooltip-in {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(var(--tooltip-slide-from, 4px));
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}`;
    document.head.appendChild(style);
  }
}
