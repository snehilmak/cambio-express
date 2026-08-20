import { type CSSProperties, type ReactElement } from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

import { tokens } from "./tokens";

/** Hover/focus tooltip — Radix Tooltip under the hood, same API.
 *
 *  Wraps a single child element and renders a small tip beside
 *  it. Radix supplies what the hand-rolled version lacked:
 *  Escape dismisses the tip, collision detection flips it away
 *  from viewport edges, and the trigger gets `aria-describedby`
 *  wired to the tip for screen readers.
 *
 *  Use this instead of the native `title=` attribute when:
 *  - the description is longer than 4-5 words
 *  - you want consistent visual treatment with the design system
 *  - you want the tip to appear on keyboard focus, not just hover
 *
 *  Set `placement="top"` (default) or `"bottom"` for the
 *  preferred side — Radix flips automatically when there's no
 *  room. The visibility delay (default 250ms) prevents
 *  flickering when the user is just sweeping their cursor past
 *  the trigger; keyboard focus shows the tip immediately.
 *
 *  The child must be a single focusable element (button, link,
 *  icon-button) — Radix attaches its listeners via `asChild`.
 */
export function Tooltip({
  label, children, placement = "top", delayMs = 250, multiline = false,
}: {
  /** Description text.  Pass a plain string; use the global
   *  Toast primitive instead if you need a multi-line callout
   *  with actions. */
  label: string;
  /** A single focusable element (button, link, icon-button). */
  children: ReactElement;
  placement?: "top" | "bottom";
  delayMs?: number;
  /** Wrap long descriptions instead of forcing one line. Use for
   *  sentence-length tips (e.g. the InfoTip primitive); keep the
   *  default single-line treatment for short action hints. */
  multiline?: boolean;
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={delayMs} skipDelayDuration={300}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          {children}
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={placement}
            sideOffset={6}
            collisionPadding={8}
            style={tipStyle(placement, multiline)}
          >
            {label}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}

function tipStyle(
  placement: "top" | "bottom", multiline = false,
): CSSProperties {
  // Small offset for the slide-from-direction effect — the tip
  // starts shifted toward the trigger then settles into place,
  // matching the shadcn / sonner motion vocabulary. Radix's
  // popper wrapper owns the positioning transform, so the
  // keyframe below only animates the content node itself.
  const slideFrom = placement === "top" ? "4px" : "-4px";
  return {
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
    transform: translateY(var(--tooltip-slide-from, 4px));
  }
  to {
    opacity: 1;
    transform: none;
  }
}`;
    document.head.appendChild(style);
  }
}
